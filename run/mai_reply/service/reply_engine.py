""" reply_engine.py 核心回复引擎 ——
将所有子模块串联起来，完成一次完整的拟人化回复流程 """

import asyncio
import traceback
import random
import uuid
import time

import aiohttp
from typing import Optional

from developTools.event.events import GroupMessageEvent, PrivateMessageEvent
from developTools.message.message_components import Record
from framework_common.database_util.User import get_user
from framework_common.utils.system_logger import get_logger
from run.mai_reply.service.audit_censor import AuditSystem

from run.mai_reply.service.context_manager import ContextManager
from run.mai_reply.service.emotion_system import EmotionSystem
from run.mai_reply.service.llm_client import LLMClient
from run.mai_reply.service.prompt_builder import PromptBuilder
from run.mai_reply.service.reply_processor import ReplyProcessor
from run.mai_reply.service.impression_updater import ImpressionUpdater
from run.mai_reply.service.concurrency import ConcurrencyController

logger = get_logger(__name__)


class ReplyEngine:
    _instance = None
    _initialized = False

    def __new__(cls, config=None, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ReplyEngine, cls).__new__(cls)
        return cls._instance

    # --------------------------------------------------

    def __init__(self, config=None):
        if self._initialized:
            return

        if config is None:
            raise ValueError("首次实例化 ReplyEngine 时必须传入 config 参数！")
        self.cfg = config
        self.llm = LLMClient(config)
        self.emotion = EmotionSystem(config)
        self.context = ContextManager(config)
        self.prompt_builder = PromptBuilder(config, self.emotion)
        self.processor = ReplyProcessor(config, self.context)
        self.impression_updater = ImpressionUpdater(self.llm, self.context)
        self.concurrency = ConcurrencyController(config)
        self.audit_system = AuditSystem(self.llm, self.context, config)

        # ---- 名称缓存 ----
        # 结构: { cache_key: (name, expire_monotonic_time) }
        self._name_cache: dict[str, tuple[str, float]] = {}

        self._tools = self._load_tools()
        self.emotion.random_drift()

    # --------------------------------------------------
    # 名称缓存辅助方法
    # --------------------------------------------------

    def _cache_get(self, key: str) -> Optional[str]:
        """从缓存取名称，过期或不存在返回 None。"""
        entry = self._name_cache.get(key)
        if entry and time.monotonic() < entry[1]:
            return entry[0]
        return None

    def _cache_set(self, key: str, value: str) -> None:
        """写入缓存，TTL 从配置读取，默认 300 秒。"""
        ttl = self.cfg.mai_reply.config.get("concurrency", {}).get("name_cache_ttl", 300)
        now = time.monotonic()
        # 懒清理：缓存条目过多时顺手淘汰过期项，避免无限增长
        if len(self._name_cache) > 5000:
            self._name_cache = {k: v for k, v in self._name_cache.items() if v[1] > now}
        self._name_cache[key] = (value, now + ttl)

    # --------------------------------------------------

    def _load_tools(self):
        try:
            if self.cfg.mai_reply.config.get("llm", {}).get("func_calling", False):
                from framework_common.framework_util.func_map_loader import build_tool_map
                tools = build_tool_map()
                logger.info(f"[MaiReply] 已加载函数调用工具: {list(tools.keys())}")
                return tools
        except Exception as e:
            traceback.print_exc()
            pass
        return None

    async def handle(self, bot, event, clean_text: str, multimodal_content=None) -> None:
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

        user_name = await self._get_user_name(bot, event, user_id, group_id)
        bot_name = await self._get_bot_name(bot)

        # ---------- 消息合并窗口
        session_key = self.context.session_key_for(group_id, user_id)
        if isinstance(multimodal_content, list):
            final_text = clean_text
        else:
            final_text = await self.concurrency.merge_or_process(session_key, clean_text)
            if final_text is None:
                return
            multimodal_content = final_text

        await self.concurrency.acquire_global()
        lock_acquired = False
        try:
            lock_timeout = self.cfg.mai_reply.config.get("concurrency", {}).get("lock_timeout", 30)
            lock_acquired = await self.context.acquire_lock(session_key, lock_timeout)
            if not lock_acquired:
                return

            if is_group:
                self.context.push_group_window(group_id, user_name, final_text)

            history = self.context.get_session_history(group_id, user_id)
            group_context = ""
            if is_group:
                group_context = self.context.build_group_context_snippet(group_id, bot_name)
            user_impression = self.context.get_impression(user_id)

            group_name = await self._get_group_name(bot, group_id) if is_group else "私聊"
            system_prompt = self.prompt_builder.build_system_prompt(
                bot_name=bot_name,
                user_name=user_name,
                group_name=group_name,
                group_context_snippet=group_context,
                user_impression=user_impression,
            )

            messages = list(history)
            user_content = multimodal_content if multimodal_content is not None else clean_text
            messages.append({"role": "user", "content": user_content})

            raw_reply = await self.llm.chat(
                messages=messages,
                system_prompt=system_prompt,
                tools=self._tools,
                bot=bot,
                event=event,
                retries=10
            )

            if not raw_reply:
                bot.logger.warning("[MaiReply] LLM 返回空回复")
                return

            segments = self.processor.process(raw_reply)
            if not segments:
                return

            msg_id = getattr(event, "message_id", None)

            # 1. 先按计划发送切分后的文本（带打字延迟）
            await self.processor.send_with_delay(bot, event, segments, quote_message_id=msg_id)

            # =================================================================
            # 触发语音回复（后台异步，完全等同于子线程避免阻塞）
            # =================================================================
            voice_cfg = self.cfg.mai_reply.config["tts"]
            voice_prob = int(voice_cfg.get("voice_reply_probability", 0))
            translate_api_key = self.cfg.mai_reply.config["trigger_llm"]["api_key"]
            voice_cfg["translate_api_key"] = translate_api_key
            if voice_prob > 0 and random.randint(1, 100) <= voice_prob:
                # 把切分好的 segments 还原成一整句 (使用逗号间隔以便 TTS 有自然的停顿)
                combined_text = ".".join(segments)
                # 使用 create_task 放入后台执行，不会阻塞后续的历史更新与心情刷新
                asyncio.create_task(self._async_tts_and_send(bot, event, combined_text, voice_cfg))

            # ---------- 更新历史
            if isinstance(multimodal_content, list):
                history_user_text = clean_text + " [含图片]" if clean_text else "[图片]"
            else:
                history_user_text = clean_text
            self.context.append_to_session(group_id, user_id, history_user_text, raw_reply)

            if is_group:
                self.context.push_group_window(group_id, bot_name, raw_reply)

            self.impression_updater.tick(user_id, group_id, user_name, bot_name)
            self.audit_system.tick(user_id, group_id, user_name, bot_name, bot)

            # 控制台打印机器人的当前心理状态
            current_score = self.emotion.get_score()
            current_mood = self.emotion.get_mood()
            current_imp = user_impression or "暂无，还不熟"

            panel = (
                f"\n┌──────── MaiReply 机器人状态监控 ────────┐\n"
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

    # =================================================================
    # 后台处理语音：翻译 -> TTS 合成 -> 发送
    # =================================================================
    async def _async_tts_and_send(self, bot, event, text: str, voice_cfg: dict):
        """
        后台异步执行：自动翻译 -> 调用TTS -> 组装并发送音频文件。
        该方法被 create_task 调用，完全脱离主消息流，实现真正意义上的不阻塞。
        """

        lang_type = voice_cfg.get("lang_type", "JP")
        speaker = voice_cfg.get("speaker", "MoriCalliope")
        api_key = voice_cfg.get("translate_api_key", "")

        translated_text = text

        # 1. 翻译逻辑 (使用 aiohttp 异步请求防止网络卡顿阻塞线程)
        if api_key and lang_type.upper() in ["JP", "JA", "EN"]:
            direction = "zh2ja" if lang_type.upper() in ["JP", "JA"] else "zh2en"
            headers = {"Authorization": f"Bearer {api_key}"}
            payload = {
                "text": text,
                "direction": direction
            }
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "http://api.apollodorus.xyz/translate",
                        json=payload,
                        headers=headers,
                        timeout=15
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            translated_text = data.get("translation", text)
                        else:
                            bot.logger.warning(f"[MaiReply] 翻译接口异常, HTTP状态码: {resp.status}")
            except Exception as e:
                bot.logger.error(f"[MaiReply] 翻译API请求失败: {e}")

        # 2. TTS 合成发送逻辑
        try:
            from run.mai_reply.service.HoliveTTS import HoliveTTS
            tts = HoliveTTS()
            bot.logger.info(f"[MaiReply] 正在后台合成语音 | 角色: {speaker} | 文本: {translated_text}")
            save_path = f"data/voice/cache/{uuid.uuid4()}.wav"
            # synthesize 方法内部也是异步的，耗时处理均不阻塞主进程
            audio_bytes = await tts.synthesize_to_file(
                text=translated_text,
                speaker=speaker,
                language=lang_type.upper(),
                save_as=save_path
            )

            await bot.send(event, Record(file=save_path))
            bot.logger.info("[MaiReply] 后台语音发送完成！")
        except Exception as e:
            bot.logger.error(f"[MaiReply] TTS合成或发送发生异常: {e}")
            traceback.print_exc()

    # ------------------------------------------------------------------
    # 辅助：获取用户名（带缓存）
    # ------------------------------------------------------------------
    async def _get_user_name(self, bot, event, user_id: int, group_id: Optional[int]) -> str:
        cache_key = f"user:{group_id}:{user_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            if group_id:
                info = await bot.get_group_member_info(group_id=group_id, user_id=user_id)
                name = info["data"]["nickname"]
            else:
                info = await bot.get_stranger_info(user_id=user_id)
                name = info["data"]["nickname"]
            name = name.strip() or str(user_id)
        except Exception:
            name = str(user_id)

        self._cache_set(cache_key, name)
        return name

    # ------------------------------------------------------------------
    # 辅助：获取 Bot 名称（固定读配置，无需缓存）
    # ------------------------------------------------------------------
    async def _get_bot_name(self, bot) -> str:
        from framework_common.framework_util.yamlLoader import YAMLManager
        globconfig = YAMLManager.get_instance()
        bot_name = globconfig.common_config.basic_config["bot"]
        return bot_name
        try:
            info = await bot.get_login_info()
            name = (info or {}).get("nickname", "")
            name = name.strip()
        except Exception:
            name = ""
        # 人设名优先
        override = self.prompt_builder.get_bot_name(name)
        return override or name or "Bot"

    # ------------------------------------------------------------------
    # 辅助：获取群名称（带缓存）
    # ------------------------------------------------------------------
    async def _get_group_name(self, bot, group_id: int) -> str:
        cache_key = f"group:{group_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            info = await bot.get_group_info(group_id=group_id)
            name = info["data"]["group_name"]
            name = name.strip() or str(group_id)
        except Exception:
            name = str(group_id)

        self._cache_set(cache_key, name)
        return name