"""
reply_engine.py
核心回复引擎 —— 将所有子模块串联起来，完成一次完整的拟人化回复流程

流程：
  1. 获取/构建上下文
  2. 构建 system prompt（含情绪、时间、群旁观上下文、用户印象）
  3. 调用 LLM（含函数调用自动执行）
  4. 后处理（清理 markdown、分割、错字）
  5. 模拟打字延迟分批发送
  6. 更新上下文历史
  7. 更新情绪
  8. （异步）更新用户印象
"""

import asyncio
import traceback
from typing import Optional

from developTools.event.events import GroupMessageEvent, PrivateMessageEvent
from framework_common.database_util.User import get_user
from framework_common.utils.system_logger import get_logger

from run.mai_reply.service.context_manager import ContextManager
from run.mai_reply.service.emotion_system import EmotionSystem
from run.mai_reply.service.llm_client import LLMClient
from run.mai_reply.service.prompt_builder import PromptBuilder
from run.mai_reply.service.reply_processor import ReplyProcessor
from run.mai_reply.service.impression_updater import ImpressionUpdater
from run.mai_reply.service.concurrency import ConcurrencyController

logger=get_logger(__name__)

class ReplyEngine:

    def __init__(self, config):
        self.cfg = config
        self.llm = LLMClient(config)
        self.emotion = EmotionSystem(config)
        self.context = ContextManager(config)
        self.prompt_builder = PromptBuilder(config, self.emotion)
        self.processor = ReplyProcessor(config, self.context)
        self.impression_updater = ImpressionUpdater(self.llm, self.context)
        self.concurrency = ConcurrencyController(config)

        # 函数调用工具映射（None = 不启用）
        self._tools = self._load_tools()

        # 初始随机漂移情绪
        self.emotion.random_drift()

    def _load_tools(self):
        """按配置决定是否加载函数调用工具表"""
        try:
            if self.cfg.mai_reply.config.get("llm", {}).get("func_calling", False):
                from framework_common.framework_util.func_map_loader import build_tool_map
                tools = build_tool_map()
                logger.info(f"[MaiReply] 已加载函数调用工具: {list(tools.keys())}")
                return tools
        except Exception as e:
            traceback.print_exc()
            # func_calling 未启用或加载失败时静默降级
            pass
        return None

    async def handle(self, bot, event, clean_text: str) -> None:
        """
        处理一条已判定需要回复的消息。
        clean_text: 已去除触发前缀的用户文本
        """
        is_group = isinstance(event, GroupMessageEvent)
        group_id: Optional[int] = getattr(event, "group_id", None) if is_group else None
        user_id: int = event.user_id

        # ---------- 权限检查
        perm_cfg = self.cfg.mai_reply.config.get("permission", {})
        required_level = perm_cfg.get("group_reply_level" if is_group else "private_reply_level", 0)
        if required_level > 0:
            user_info = await get_user(user_id)
            if user_info.permission < required_level:
                return

        # ---------- 获取用户昵称
        user_name = await self._get_user_name(bot, event, user_id, group_id)
        bot_name = await self._get_bot_name(bot)

        # ---------- 消息合并窗口
        session_key = self.context.session_key_for(group_id, user_id)
        final_text = await self.concurrency.merge_or_process(session_key, clean_text)
        if final_text is None:
            return  # 被后来的消息合并掉，不处理

        # ---------- 并发控制
        await self.concurrency.acquire_global()
        lock_acquired = False
        try:
            # ---------- 会话锁（避免同一会话并发回复）
            lock_timeout = self.cfg.mai_reply.config.get("concurrency", {}).get("lock_timeout", 30)
            lock_acquired = await self.context.acquire_lock(session_key, lock_timeout)
            if not lock_acquired:
                return

            # ---------- 更新群旁观窗口
            if is_group:
                self.context.push_group_window(group_id, user_name, final_text)

            # ---------- 情绪更新
            #self.emotion.update_from_message(final_text)

            # ---------- 构建上下文
            history = self.context.get_session_history(group_id, user_id)
            group_context = ""
            if is_group:
                group_context = self.context.build_group_context_snippet(group_id, bot_name)
            user_impression = self.context.get_impression(user_id)

            # ---------- 构建 system prompt
            group_name = await self._get_group_name(bot, group_id) if is_group else "私聊"
            system_prompt = self.prompt_builder.build_system_prompt(
                bot_name=bot_name,
                user_name=user_name,
                group_name=group_name,
                group_context_snippet=group_context,
                user_impression=user_impression,
            )

            # ---------- 构建消息列表（对话历史 + 本次）
            messages = list(history)
            messages.append({"role": "user", "content": final_text})

            # ---------- 调用 LLM（工具调用在 llm_client 内部自动处理）
            #logger.info(f"[MaiReply] {messages}")
            #logger.info(f"[MaiReply] {system_prompt}")
            #logger.info(self._tools)

            raw_reply = await self.llm.chat(
                messages=messages,
                system_prompt=system_prompt,
                tools=self._tools,
                bot=bot,  # 【新增这一行】
                event=event,  # 【新增这一行】
                retries=10
            )

            if not raw_reply:
                bot.logger.warning("[MaiReply] LLM 返回空回复")
                return

            # ---------- 后处理
            segments = self.processor.process(raw_reply)
            if not segments:
                return

            # ---------- 获取消息ID用于引用
            msg_id = getattr(event, "message_id", None)

            # ---------- 发送（带打字延迟）
            await self.processor.send_with_delay(bot, event, segments, quote_message_id=msg_id)

            # ---------- 更新历史（存储完整原始回复，不存分割后的）
            self.context.append_to_session(group_id, user_id, final_text, raw_reply)

            if is_group:
                self.context.push_group_window(group_id, bot_name, raw_reply)

            # ---------- 触发印象更新（异步，不阻塞）
            self.impression_updater.tick(user_id, group_id, user_name, bot_name)

            # =================================================================
            # 【新增】状态显示：在控制台打印机器人的当前心理状态
            # =================================================================
            current_score = self.emotion.get_score()
            current_mood = self.emotion.get_mood()
            current_imp = user_impression or "暂无，还不熟"

            panel = (
                f"\n┌──────── MaiReply 机器人生理状态监控 ────────┐\n"
                f"│ 👤 交互对象: {user_name} ({user_id})\n"
                f"│ 💬 最终回复: {raw_reply}\n"
                f"│ 📊 全局心情: {current_score}分 ({current_mood})\n"
                f"│ 🧠 对TA印象: {current_imp}\n"
                f"└─────────────────────────────────────────────┘"
            )
            bot.logger.info(panel)

        except Exception as e:
            bot.logger.error(f"[MaiReply] 回复出错: {e}", exc_info=True)
            traceback.print_exc()
        finally:
            if lock_acquired:
                self.context.release_lock(session_key)
            self.concurrency.release_global()

    # ------------------------------------------------------------------ 辅助
    async def _get_user_name(self, bot, event, user_id: int, group_id: Optional[int]) -> str:
        try:
            if group_id:
                info = await bot.get_group_member_info(group_id=group_id, user_id=user_id)
                name = (info or {}).get("card") or (info or {}).get("nickname", "")
            else:
                info = await bot.get_stranger_info(user_id=user_id)
                name = (info or {}).get("nickname", "")
            return name.strip() or str(user_id)
        except Exception:
            return str(user_id)

    async def _get_bot_name(self, bot) -> str:
        try:
            info = await bot.get_login_info()
            name = (info or {}).get("nickname", "")
            name = name.strip()
        except Exception:
            name = ""
        # 人设名优先
        override = self.prompt_builder.get_bot_name(name)
        return override or name or "Bot"

    async def _get_group_name(self, bot, group_id: int) -> str:
        try:
            info = await bot.get_group_info(group_id=group_id)
            return (info or {}).get("group_name", str(group_id))
        except Exception:
            return str(group_id)