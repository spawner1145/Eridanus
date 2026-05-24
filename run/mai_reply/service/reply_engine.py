"""
reply_engine.py 核心回复引擎 ——
将所有子模块串联起来，完成一次完整的拟人化回复流程

新增：
- 群聊气氛印象（group_impression）的读取与注入
- 最近发言者印象批量读取并注入 prompt
- triggered_by_llm 标记，群内 trigger_llm 触发时限制回复长度/句数
"""

import asyncio
import re
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
from run.tts_v2.service.GPT_SoVits import AsyncGPTSoVITSClient

logger = get_logger(__name__)
gpt_sovits_client = AsyncGPTSoVITSClient()

class ReplyEngine:
    _instance = None
    _initialized = False

    def __new__(cls, config=None, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ReplyEngine, cls).__new__(cls)
        return cls._instance

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

        self._name_cache: dict[str, tuple[str, float]] = {}

        self._tools = self._load_tools()
        self.emotion.random_drift()

    # --------------------------------------------------
    # 名称缓存辅助
    # --------------------------------------------------

    def _cache_get(self, key: str) -> Optional[str]:
        entry = self._name_cache.get(key)
        if entry and time.monotonic() < entry[1]:
            return entry[0]
        return None

    def _cache_set(self, key: str, value: str) -> None:
        ttl = self.cfg.mai_reply.config.get("concurrency", {}).get("name_cache_ttl", 300)
        now = time.monotonic()
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
        return None

    async def handle(
        self,
        bot,
        event,
        clean_text: str,
        multimodal_content=None,
        triggered_by_llm: bool = False,  # ← 新增：是否由 trigger_llm 触发
    ) -> None:
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
                # 传入 user_id 以便发言者追踪
                self.context.push_group_window(group_id, user_name, final_text, user_id=user_id)

            history = self.context.get_session_history(group_id, user_id)
            group_context = ""
            if is_group:
                group_context = self.context.build_group_context_snippet(group_id, bot_name)

            user_impression = self.context.get_impression(user_id)

            # ---- 群聊专属：气氛印象 + 最近发言者印象 ----
            group_impression = ""
            recent_speaker_impressions = []
            if is_group and group_id:
                group_impression = self.context.get_group_impression(group_id)
                recent_speaker_impressions = self.context.get_recent_speaker_impressions(group_id)

            group_name = await self._get_group_name(bot, group_id) if is_group else "私聊"
            system_prompt = self.prompt_builder.build_system_prompt(
                bot_name=bot_name,
                user_name=user_name,
                group_name=group_name,
                group_context_snippet=group_context,
                user_impression=user_impression,
                is_group=is_group,
                triggered_by_llm=triggered_by_llm,
                group_impression=group_impression,
                recent_speaker_impressions=recent_speaker_impressions,
            )

            max_turns = self.cfg.mai_reply.config.get("context", {}).get("max_turns", 20)
            max_history_msgs = max_turns * 2
            trimmed_history = history[-max_history_msgs:] if len(history) > max_history_msgs else list(history)

            messages = trimmed_history
            user_content = multimodal_content if multimodal_content is not None else clean_text
            messages.append({"role": "user", "content": user_content})

            raw_reply = await self.llm.chat(
                messages=messages,
                system_prompt=system_prompt,
                tools=self._tools,
                bot=bot,
                event=event,
                retries=3
            )

            if not raw_reply:
                bot.logger.warning("[MaiReply] LLM 返回空回复，清理上下文后重试一次")
                retry_messages = [{"role": "user", "content": user_content}]
                raw_reply = await self.llm.chat(
                    messages=retry_messages,
                    system_prompt=system_prompt,
                    tools=self._tools,
                    bot=bot,
                    event=event,
                    retries=2
                )
                if not raw_reply:
                    bot.logger.warning("[MaiReply] 重试后仍为空，放弃本次回复")
                    return

            segments = self.processor.process(raw_reply)
            if not segments:
                return

            # trigger_llm 触发时在处理层也做一次硬截断保险
            if triggered_by_llm and is_group:
                segments = self._hard_truncate_segments(segments)

            msg_id = getattr(event, "message_id", None)
            await self.processor.send_with_delay(bot, event, segments, quote_message_id=msg_id)

            # TTS
            voice_cfg = self.cfg.mai_reply.config["tts"]
            voice_prob = int(voice_cfg.get("voice_reply_probability", 0))
            translate_api_key = self.cfg.mai_reply.config["trigger_llm"]["api_key"]
            voice_cfg["translate_api_key"] = translate_api_key
            if voice_prob > 0 and random.randint(1, 100) <= voice_prob:
                combined_text = ".".join(segments)
                asyncio.create_task(self._async_tts_and_send(bot, event, combined_text, voice_cfg))

            # 更新历史
            if isinstance(multimodal_content, list):
                history_user_text = clean_text + " [含图片]" if clean_text else "[图片]"
            else:
                history_user_text = clean_text
            self.context.append_to_session(group_id, user_id, history_user_text, raw_reply)

            if is_group:
                self.context.push_group_window(group_id, bot_name, raw_reply)

            self.impression_updater.tick(user_id, group_id, user_name, bot_name)
            self.audit_system.tick(user_id, group_id, user_name, bot_name, bot)

            # 群印象更新 tick（有群 ID 时触发）
            if is_group and group_id:
                self.impression_updater.tick_group(group_id, group_name, bot_name)

            current_score = self.emotion.get_score()
            current_mood = self.emotion.get_mood()
            current_imp = user_impression or "暂无，还不熟"

            panel = (
                f"\n┌──────── MaiReply 机器人状态监控 ────────┐\n"
                f"│ 👤 交互对象: {user_name} ({user_id})\n"
                f"│ 💬 最终回复: {raw_reply}\n"
                f"│ 📊 全局心情: {current_score}分 ({current_mood})\n"
                f"│ 🧠 对TA印象: {current_imp}\n"
                f"│ 🌐 trigger_llm: {triggered_by_llm}\n"
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

    def _hard_truncate_segments(self, segments: list) -> list:
        """
        trigger_llm 触发时的处理层硬截断保险。
        防止 LLM 无视 prompt 约束产生过长回复。
        """
        max_segs = self.prompt_builder.trigger_max_segments
        max_chars = self.prompt_builder.trigger_max_chars

        # 截断段数
        segments = segments[:max_segs]

        # 每段字数截断
        result = []
        total = 0
        for seg in segments:
            remaining = max_chars - total
            if remaining <= 0:
                break
            if len(seg) > remaining:
                seg = seg[:remaining].rstrip()
            result.append(seg)
            total += len(seg)

        return result

    # =================================================================
    # 后台处理语音：翻译 -> TTS 合成 -> 发送
    # =================================================================
    async def _async_tts_and_send(self, bot, event, text: str, voice_cfg: dict):
        lang_type = voice_cfg.get("lang_type", "JP")
        speaker = voice_cfg.get("speaker", "MoriCalliope")
        api_key = voice_cfg.get("translate_api_key", "")

        def remove_parentheses_text(text: str) -> str:
            """去除文本中括号（含内容）的部分，支持全角和半角括号"""
            # 去除全角括号 （...） 和半角括号 (...)
            text = re.sub(r'[（(][^）)]*[）)]', '', text)
            return text.strip()
        text=remove_parentheses_text(text)
        translated_text = text

        if speaker in gpt_sovits_client.speakers:
            audio_path=await gpt_sovits_client.generate_tts(text)
            await bot.send(event, Record(file=audio_path))
            bot.logger.info("[MaiReply] 后台语音发送完成！")
            return

        if api_key and lang_type.upper() in ["JP", "JA", "EN"]:
            direction = "zh2ja" if lang_type.upper() in ["JP", "JA"] else "zh2en"
            headers = {"Authorization": f"Bearer {api_key}"}
            payload = {"text": text, "direction": direction}
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

        try:
            from run.mai_reply.service.HoliveTTS import HoliveTTS
            tts = HoliveTTS()
            bot.logger.info(f"[MaiReply] 正在后台合成语音 | 角色: {speaker} | 文本: {translated_text}")
            save_path = f"data/voice/cache/{uuid.uuid4()}.wav"
            audio_path = await tts.synthesize_to_file(
                text=translated_text,
                speaker=speaker,
                language=lang_type.upper(),
                save_as=save_path
            )
            await bot.send(event, Record(file=audio_path))
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
    # 辅助：获取 Bot 名称
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