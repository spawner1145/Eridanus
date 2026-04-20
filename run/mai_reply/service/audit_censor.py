"""
audit_system.py
审核系统 —— 定期用 LLM 对历史对话进行多维度安全审查
原理：每 N 轮对话触发一次审查，如果发现敏感内容，通过 bot API 给主人发消息告警
"""

import asyncio
import re
from typing import List, Dict

from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.utils.system_logger import get_logger

logger = get_logger(__name__)

AUDIT_PROMPT_TEMPLATE = """以下是你（{bot_name}）和 {user_name} 的近期对话片段：

{history_text}

请作为一个严格且客观的内容安全审核员，从多维度（包含但不限于：政治敏感、涉黄色情、暴力血腥、严重辱骂、违法犯罪等）分析上述对话是否存在违规或敏感风险。
请务必在回答中包含以下特定格式的判断结果：
如果包含敏感内容，请输出 [SENSITIVE: TRUE] 并在新起一行简要说明原因。
如果不包含敏感内容，请输出 [SENSITIVE: FALSE]。"""



class AuditSystem:
    def __init__(self, llm_client, context_manager, config):
        self._llm = llm_client
        self._ctx = context_manager
        self.cfg = config

        # 计数器：(user_id, group_id) -> turn_count
        self._counters: Dict[str, int] = {}

        # 读取审核配置

        self.enable = config.mai_reply.config["context"]["anti_nsfw"]["enable"]
        if self.enable:
            logger.info("[MaiReply Audit] 内容审查已启用，每 %d 轮对话触发一次审查，使用模型: %s",)
        self.model = config.mai_reply.config["trigger_llm"]["model"]
        self.trigger_turns = config.mai_reply.config["context"]["anti_nsfw"]["trigger_turns"]

    def _counter_key(self, user_id: int, group_id) -> str:
        return f"{group_id or 'priv'}:{user_id}"

    def tick(self, user_id: int, group_id, user_name: str, bot_name: str, bot) -> None:
        """每次对话完成后调用，异步判断是否需要触发内容审查"""
        if not self.enable:
            return

        key = self._counter_key(user_id, group_id)
        self._counters[key] = self._counters.get(key, 0) + 1
        logger.info(f"[MaiReply Audit] 计数器更新 {key} -> {self._counters[key]} (触发阈值: {self.trigger_turns})")
        if self._counters[key] >= self.trigger_turns:
            self._counters[key] = 0
            asyncio.create_task(
                self._run_audit(user_id, group_id, user_name, bot_name, bot)
            )

    async def _run_audit(self, user_id: int, group_id, user_name: str, bot_name: str, bot) -> None:
        try:
            history: List[Dict] = self._ctx.get_session_history(group_id, user_id)
            if not history:
                return

            # 取最近的 trigger_turns 轮对话（一轮2条，故 * 2）
            recent = history[-(self.trigger_turns * 2):]
            lines = []
            for msg in recent:
                role = user_name if msg["role"] == "user" else bot_name
                lines.append(f"{role}：{msg['content']}")
            history_text = "\n".join(lines)

            prompt = AUDIT_PROMPT_TEMPLATE.format(
                bot_name=bot_name, user_name=user_name, history_text=history_text,
            )
            logger.info(f"[MaiReply Audit] 触发审查，用户: {user_name}({user_id}) 群聊: {group_id or '私聊'} 对话轮数: {self.trigger_turns} 审查模型: {self.model}")
            # 调用大模型执行审查
            summary = await self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="你是一个严格的内容安全防御矩阵，只负责客观审查。",
                model=self.model,
            )
            logger.info(f"[MaiReply Audit] 审查结果: {summary}")
            if not summary:
                return

            # 正则匹配是否触发敏感词
            match = re.search(r"\[SENSITIVE:\s*(TRUE|FALSE)\]", summary, re.IGNORECASE)
            if match and match.group(1).upper() == "TRUE":
                logger.warning(f"[MaiReply Audit] 发现敏感对话！用户: {user_name}({user_id})")

                # 提取原因（去除标志位剩下的内容）
                reason = summary.replace(match.group(0), "").strip()

                # 获取主人 QQ 号
                master = self.cfg.common_config.basic_config["master"]["id"]
                # 兼容 master 是列表或单体数字/字符串的情况
                master_id = master[0] if isinstance(master, list) and len(master) > 0 else master

                if master_id:
                    alert_msg = (
                        f"⚠️ [MaiReply 内容审核警告]\n"
                        f"触发用户: {user_name} ({user_id})\n"
                        f"所在群聊: {group_id or '私聊'}\n"
                        f"风险原因: {reason}\n"
                        f"近期片段: \n{history_text[:200]}..."  # 截断一下防止过长
                    )
                    # 发送警告消息给主人
                    await bot.send_friend_message(master_id, alert_msg)
                else:
                    logger.error("[MaiReply Audit] 发现敏感内容，但未配置 master，无法发送告警信息。")

        except Exception as e:
            logger.error(f"[MaiReply Audit] 审查更新失败: {e}", exc_info=True)