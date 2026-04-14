import asyncio
import datetime
import re
import random
import traceback
from typing import Dict

from developTools.event.events import GroupMessageEvent, PrivateMessageEvent
from developTools.message.message_components import At,Record
from run.ai_llm.service.heartflow_client import heartflow_request


async def heartflow_reply(config, prompt, recursion_times=0):
    try:
        result = await heartflow_request(
            config,
            [{"text": prompt}],
            system_instruction=None,
            group_context=None,
        )
        return result
    except Exception as e:
        traceback.print_exc()
        recursion_times += 1
        limit = config.ai_llm.config["llm"].get("retries", 3)
        if recursion_times > limit:
            return None
        return await heartflow_reply(config, prompt, recursion_times)


def main(bot, config):
    """内容审核插件入口"""

    mod_cfg = config.ai_llm.config.get("content_moderation", {})
    enabled: bool = mod_cfg.get("enabled", True)
    batch_size: int = mod_cfg.get("batch_size", 3)
    context_size: int = mod_cfg.get("context_size", 10)
    porn_threshold: float = mod_cfg.get("porn_threshold", 6.0)
    politics_threshold: float = mod_cfg.get("politics_threshold", 5.0)
    violence_threshold: float = mod_cfg.get("violence_threshold", 6.0)
    other_threshold: float = mod_cfg.get("other_threshold", 7.0)
    master_id: int = config.common_config.basic_config["master"]["id"]
    send_gay_audio: bool = mod_cfg.get("send_gay_audio",True)

    # 跨群/私聊统一计数 {user_id: count}
    counters: Dict[int, int] = {}

    # ============ 核心审核函数 ============

    async def run_moderation(user_id: int, user_nickname: str) -> None:
        try:
            from framework_common.database_util.llmDB import get_user_history
            history = await get_user_history(user_id)
            recent = history[-context_size:] if history else []

            lines = []
            for msg in recent:
                role = msg.get("role", "")
                text = extract_text(msg)
                if text.strip():
                    label = "用户" if role == "user" else "助手"
                    lines.append(f"[{label}] {text.strip()}")

            conversation_str = "\n".join(lines) if lines else "（无对话记录）"

            prompt = f"""你是一个内容安全审核系统，请对以下对话进行审核。
判断用户（uid={user_id}，昵称={user_nickname}）是否有色情、政治敏感、暴力仇恨或其他违规意图。

## 对话记录（最近若干轮）
{conversation_str}

请从4个维度评估（0-10分），并说明理由：

色情: 0-10
政治: 0-10
暴力: 0-10
其他: 0-10
理由: 简要说明判断依据

⚠️ 请严格保持该格式，每个分数只写一个纯数字。"""

            result_text = await heartflow_reply(config, prompt)
            #bot.logger.warning(result_text)
            if not result_text:
                return

            def ext(name):
                m = re.search(rf"(?:{name})\s*[:：]\s*(\d+(?:\.\d+)?)", result_text)
                return float(m.group(1)) if m else 0.0

            porn = ext("色情")
            politics = ext("政治|政治敏感")
            violence = ext("暴力")
            other = ext("其他")

            reasoning_match = re.search(r"(理由|原因)[:：]\s*(.+)", result_text, re.S)
            reasoning = reasoning_match.group(2).strip() if reasoning_match else result_text.strip()

            bot.logger.warning(
                f"内容审核结果 | uid={user_id} | "
                f"porn={porn:.1f} politics={politics:.1f} "
                f"violence={violence:.1f} other={other:.1f} | {reasoning}"
            )

            hits = []
            if porn >= porn_threshold:
                hits.append(f"色情({porn:.1f})")
            if politics >= politics_threshold:
                hits.append(f"政治({politics:.1f})")
            if violence >= violence_threshold:
                hits.append(f"暴力({violence:.1f})")
            if other >= other_threshold:
                hits.append(f"其他({other:.1f})")

            if hits:
                category_str = "、".join(hits)
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                alert_msg = (
                    f"[内容审核告警] {timestamp}\n"
                    f"用户：{user_nickname}（uid={user_id}）\n"
                    f"命中类别：{category_str}\n"
                    f"理由：{reasoning}\n"
                    f"---对话记录---\n"
                    #f"{conversation_str}"
                )
                await bot.send_friend_message(master_id, alert_msg)
                bot.logger.warning(
                    f"内容审核触发 | uid={user_id} | 类别:{category_str} | 理由:{reasoning}"
                )
                if send_gay_audio:
                    await bot.send(event,Record(file="data/pictures/gay_audio/"+random.choice(os.listdir("data/pictures/gay_audio"))))

        except Exception as e:
            traceback.print_exc()
            bot.logger.error(f"内容审核异常 | uid={user_id} | {e}")

    def extract_text(msg: dict) -> str:
        if "parts" in msg:
            return "".join(
                p["text"] for p in msg["parts"]
                if isinstance(p, dict) and "text" in p
            )
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                item.get("text", "") for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
        return ""

    def tick(user_id: int, user_nickname: str):
        """计数 +1，达到 batch_size 时异步触发审核。"""
        if not enabled:
            return
        counters[user_id] = counters.get(user_id, 0) + 1
        if counters[user_id] % batch_size == 0:
            bot.logger.warning(f"触发对{user_id}的聊天记录审核")
            asyncio.create_task(run_moderation(user_id, user_nickname))

    # ============ 事件监听 ============

    @bot.on(GroupMessageEvent)
    async def group_moderation_handler(event: GroupMessageEvent):
        if event.user_id == bot.id:
            return
        # 只统计真正触发 AI 回复的消息：@bot
        if not (event.message_chain.has(At)
                and event.message_chain.get(At)[0].qq in [bot.id, 1000000]):
            return
        if not event.pure_text or not event.pure_text.strip():
            return

        nickname = getattr(event.sender, "nickname", str(event.user_id))
        tick(event.user_id, nickname)

    @bot.on(PrivateMessageEvent)
    async def private_moderation_handler(event: PrivateMessageEvent):
        if event.user_id == bot.id:
            return
        if not event.pure_text or not event.pure_text.strip():
            return

        nickname = getattr(event.sender, "nickname", str(event.user_id))
        tick(event.user_id, nickname)

    bot.logger.info(
        f"内容审核插件已加载 | 每{batch_size}次提问审核一次 | "
        f"色情:{porn_threshold} 政治:{politics_threshold} "
        f"暴力:{violence_threshold} 其他:{other_threshold}"
    )
