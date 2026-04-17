"""
impression_updater.py
用户印象更新器 —— 定期用 LLM 对历史对话做摘要，形成跨会话的用户记忆
原理：每 N 轮对话触发一次摘要，将摘要写入 Redis
"""

import asyncio
from typing import List, Dict

from framework_common.utils.system_logger import get_logger

logger=get_logger(__name__)
SUMMARY_TRIGGER_TURNS = 4   # 【修改】从 10 改为 4，每聊 4 轮就快速更新一次对这个人的印象
SUMMARY_PROMPT_TEMPLATE = """以下是你（{bot_name}）和 {user_name} 的对话片段：

{history_text}

请用2-4句话总结：{user_name} 是个什么样的人？他对你的态度如何？你们聊了什么？
请用第一人称（"我"=你自己）来写，一定要带上主观感情色彩！比如“他很温柔，我挺喜欢和他聊天的”或“这人好烦，总使唤我”。"""


class ImpressionUpdater:

    def __init__(self, llm_client, context_manager):
        self._llm = llm_client
        self._ctx = context_manager
        # 计数器：(user_id, group_id) -> turn_count
        self._counters: Dict[str, int] = {}

    def _counter_key(self, user_id: int, group_id) -> str:
        return f"{group_id or 'priv'}:{user_id}"

    def tick(self, user_id: int, group_id, user_name: str, bot_name: str) -> None:
        """每次对话完成后调用，异步判断是否需要更新印象"""
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

            recent = history[-10:] # 取最近10条即可
            lines = []
            for msg in recent:
                role = user_name if msg["role"] == "user" else bot_name
                lines.append(f"{role}：{msg['content']}")
            history_text = "\n".join(lines)

            prompt = SUMMARY_PROMPT_TEMPLATE.format(
                bot_name=bot_name, user_name=user_name, history_text=history_text,
            )

            summary = await self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="你是一个情感潜意识提取器，帮助机器人记住对别人的印象和喜恶。",
            )
            if summary:
                self._ctx.update_impression(user_id, summary.strip())
                logger.info(f"[MaiReply] 已更新对 {user_name}({user_id}) 的印象: {summary.strip()}")
        except Exception as e:
            logger.error(f"[MaiReply] 印象更新失败: {e}") # 暴露出错原因
