"""
impression_updater.py
用户印象更新器 —— 定期用 LLM 对历史对话做增量摘要，形成跨会话的压缩记忆
- 每 N 轮触发一次，融合旧印象与新对话生成新印象
- 印象超过字数上限时自动压缩，避免无限膨胀
"""

import asyncio
from typing import List, Dict

from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.utils.system_logger import get_logger
from run.mai_reply.service.simple_chat import simplified_chat

logger = get_logger(__name__)

SUMMARY_TRIGGER_TURNS = 3   # 每聊3轮触发一次印象更新
IMPRESSION_MAX_CHARS = 300  # 超过此字数触发压缩

# 增量更新：融合旧印象与新对话
SUMMARY_PROMPT_TEMPLATE = """你（{bot_name}）和 {user_name} 的最新对话：

{history_text}

---
你对TA的旧印象（可能为空）：
{old_impression}

请用不超过150字更新你对 {user_name} 的印象记忆。要求：
- 第一人称（"我"），带主观感情色彩
- 融合旧印象与新对话，重点记录：TA的性格/口癖/喜好、你们聊过的重要话题、你对TA的情感态度
- 如果旧印象和新对话矛盾，以新对话为准
- 直接输出印象文字，不要任何前缀或解释"""

# 压缩：印象过长时精简
COMPRESS_PROMPT_TEMPLATE = """以下是你（{bot_name}）对 {user_name} 积累的印象记忆（当前{char_count}字，需要压缩）：

{old_impression}

请压缩到200字以内，保留最重要的性格特征、你们的关系状态和你的情感态度。直接输出压缩后的文字，不要任何前缀。"""


class ImpressionUpdater:

    def __init__(self, llm_client, context_manager):
        self._llm = llm_client
        self._ctx = context_manager
        # 计数器：counter_key -> turn_count
        self._counters: Dict[str, int] = {}
        cfg = YAMLManager.get_instance()
        self.model = cfg.mai_reply.config["context"]["impression_model"] if cfg.mai_reply.config["context"]["impression_model"] else cfg.mai_reply.config["trigger_llm"]["model"]
        self.api_key = cfg.mai_reply.config["trigger_llm"]["api_key"]
        self.base_url = cfg.mai_reply.config["trigger_llm"]["base_url"]

    def _counter_key(self, user_id: int, group_id) -> str:
        return f"{group_id or 'priv'}:{user_id}"

    async def _call_llm(self, prompt: str) -> str:
        """统一的LLM调用入口"""
        if not self.base_url:
            return await self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="你是一个情感记忆提取器，帮助机器人记住并压缩对他人的印象。输出简洁，不加任何前缀。",
                model=self.model,
            )
        else:
            return await simplified_chat(
                self.base_url,
                [{"role": "user", "content": prompt}],
                self.model,
                self.api_key,
                system_prompt="你是一个情感记忆提取器，帮助机器人记住并压缩对他人的印象。输出简洁，不加任何前缀。"
            )

    def tick(self, user_id: int, group_id, user_name: str, bot_name: str) -> None:
        """每次对话完成后调用，达到触发轮数时异步更新印象"""
        key = self._counter_key(user_id, group_id)
        self._counters[key] = self._counters.get(key, 0) + 1
        if self._counters[key] >= SUMMARY_TRIGGER_TURNS:
            self._counters[key] = 0
            asyncio.create_task(
                self._update_impression(user_id, group_id, user_name, bot_name)
            )

    async def _update_impression(
        self, user_id: int, group_id, user_name: str, bot_name: str
    ) -> None:
        try:
            history: List[Dict] = self._ctx.get_session_history(group_id, user_id)
            if not history:
                return

            # 取最近6条（3轮）作为新对话输入
            recent = history[-6:]
            lines = []
            for msg in recent:
                role = user_name if msg["role"] == "user" else bot_name
                # 单条消息过长则截断，避免prompt膨胀
                content = msg["content"]
                if isinstance(content, list):
                    content = next((p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"), "")
                content = str(content)[:200]
                lines.append(f"{role}：{content}")
            history_text = "\n".join(lines)

            # 读取旧印象，作为融合基础
            old_impression = self._ctx.get_impression(user_id) or ""

            # 生成新印象（融合旧印象 + 新对话）
            prompt = SUMMARY_PROMPT_TEMPLATE.format(
                bot_name=bot_name,
                user_name=user_name,
                history_text=history_text,
                old_impression=old_impression or "（暂无，第一次聊）",
            )
            new_impression = await self._call_llm(prompt)
            if not new_impression:
                return

            new_impression = new_impression.strip()

            # 超长则压缩（避免印象无限膨胀）
            if len(new_impression) > IMPRESSION_MAX_CHARS:
                compress_prompt = COMPRESS_PROMPT_TEMPLATE.format(
                    bot_name=bot_name,
                    user_name=user_name,
                    char_count=len(new_impression),
                    old_impression=new_impression,
                )
                compressed = await self._call_llm(compress_prompt)
                if compressed and compressed.strip():
                    new_impression = compressed.strip()

            self._ctx.update_impression(user_id, new_impression)
            logger.info(f"[MaiReply] 已更新对 {user_name}({user_id}) 的印象({len(new_impression)}字): {new_impression}")

        except Exception as e:
            logger.error(f"[MaiReply] 印象更新失败: {e}")