"""
心流主动回复插件 - 基于结构化输出的智能判断系统
完全符合框架插件规范，无需修改主程序
"""
import asyncio
import datetime
import time
from typing import Dict
from dataclasses import dataclass, field

from developTools.event.events import GroupMessageEvent, LifecycleMetaEvent
from framework_common.database_util.Group import get_last_20_and_convert_to_prompt
from framework_common.database_util.User import get_user, update_user
from framework_common.database_util.llmDB import delete_latest2_history
from run.ai_llm.service.aiReplyCore import aiReplyCore, send_text, count_tokens_approximate
from run.ai_llm.service.schemaReplyCore import schemaReplyCore


@dataclass
class JudgeResult:
    """判断结果数据类"""
    relevance: float = 0.0
    willingness: float = 0.0
    social: float = 0.0
    timing: float = 0.0
    continuity: float = 0.0
    reasoning: str = ""
    should_reply: bool = False
    confidence: float = 0.0
    overall_score: float = 0.0


@dataclass
class ChatState:
    """群聊状态数据类"""
    energy: float = 1.0
    last_reply_time: float = 0.0
    last_reset_date: str = ""
    total_messages: int = 0
    total_replies: int = 0
    recent_interactions: Dict[int, float] = field(default_factory=dict)


def main(bot, config):
    """
    此插件代码参考了https://github.com/advent259141/Astrbot_plugin_Heartflow
    """
    """心流插件主函数"""
    # 获取tools配置（从原框架复制）
    tools = None
    if config.ai_llm.config["llm"]["func_calling"]:
        from framework_common.framework_util.func_map_loader import gemini_func_map, openai_func_map
        if config.ai_llm.config["llm"]["model"] == "gemini":
            tools = gemini_func_map()
        else:
            tools = openai_func_map()

    if config.ai_llm.config["llm"]["联网搜索"]:
        if config.ai_llm.config["llm"]["model"] == "gemini":
            if tools is None:
                tools = [{"googleSearch": {}}]
            else:
                tools = [{"googleSearch": {}}, tools]
        else:
            if tools is None:
                tools = [{"type": "function", "function": {"name": "googleSearch"}}]
            else:
                tools = [{"type": "function", "function": {"name": "googleSearch"}}, tools]
    # ============ 配置读取 ============



    # 判断权重配置
    weights = {
        "relevance": config.ai_llm.config["heartflow"]["weight_relevance"],
        "willingness": config.ai_llm.config["heartflow"]["weight_willingness"],
        "social": config.ai_llm.config["heartflow"]["weight_social"],
        "timing": config.ai_llm.config["heartflow"]["weight_timing"],
        "continuity": config.ai_llm.config["heartflow"]["weight_continuity"],
    }

    # 归一化权重
    weight_sum = sum(weights.values())
    if abs(weight_sum - 1.0) > 1e-6:
        bot.logger.warning(f"心流插件：判断权重和不为1 ({weight_sum})，已自动归一化")
        weights = {k: v / weight_sum for k, v in weights.items()}

    # ============ 状态管理 ============
    chat_states: Dict[int, ChatState] = {}
    persona_cache: Dict[str, str] = {}
    user_state = {}  # 用户消息队列状态
    portrait_updating = set()  # 正在更新画像的用户

    # ============ 工具函数 ============

    def get_chat_state(group_id: int) -> ChatState:
        """获取群聊状态"""
        if group_id not in chat_states:
            chat_states[group_id] = ChatState()

        state = chat_states[group_id]
        today = datetime.date.today().isoformat()
        if state.last_reset_date != today:
            state.last_reset_date = today
            state.energy = min(1.0, state.energy + 0.2)
            bot.logger.info(f"心流插件：群 {group_id} 每日重置，精力恢复至 {state.energy:.2f}")

        return state

    def get_minutes_since_last_reply(group_id: int) -> int:
        """获取距离上次回复的分钟数"""
        state = get_chat_state(group_id)
        if state.last_reply_time == 0:
            return 999
        return int((time.time() - state.last_reply_time) / 60)

    def update_active_state(group_id: int, user_id: int):
        """更新主动回复状态"""
        state = get_chat_state(group_id)
        state.last_reply_time = time.time()
        state.total_replies += 1
        state.total_messages += 1
        state.energy = max(0.1, state.energy - config.ai_llm.config["heartflow"]["energy_decay_rate"])
        state.recent_interactions[user_id] = time.time()
        bot.logger.debug(f"心流插件：更新主动状态 | 群:{group_id} | 精力:{state.energy:.2f}")

    def update_passive_state(group_id: int):
        """更新被动状态"""
        state = get_chat_state(group_id)
        state.total_messages += 1
        state.energy = min(1.0, state.energy + config.ai_llm.config["heartflow"]["energy_recovery_rate"])
        bot.logger.debug(f"心流插件：更新被动状态 | 群:{group_id} | 精力:{state.energy:.2f}")

    def check_recent_interaction(group_id: int, user_id: int) -> bool:
        """检查是否有最近的交互记录"""
        state = get_chat_state(group_id)
        if user_id not in state.recent_interactions:
            return False

        last_time = state.recent_interactions[user_id]
        time_diff = time.time() - last_time

        if time_diff > config.ai_llm.config["heartflow"]["interaction_timeout"]:
            del state.recent_interactions[user_id]
            return False

        return True

    async def get_persona_prompt(user_id: int) -> str:
        """获取用户的人格设定"""
        try:
            cache_key = f"persona_{user_id}"
            if cache_key in persona_cache:
                return persona_cache[cache_key]

            user_info = await get_user(user_id)
            chara_file = getattr(user_info, 'chara_file', None)

            if not chara_file or chara_file == "default":
                chara_file = config.ai_llm.config["llm"]["chara_file_name"]

            chara_path = f"./data/system/{chara_file}"
            try:
                with open(chara_path, 'r', encoding='utf-8') as f:
                    persona = f.read().strip()

                if len(persona) > 500:
                    persona = await summarize_persona(persona)

                persona_cache[cache_key] = persona
                return persona
            except FileNotFoundError:
                bot.logger.warning(f"心流插件：未找到角色文件 {chara_path}")
                return "默认智能助手"
        except Exception as e:
            bot.logger.error(f"心流插件：获取人格设定失败 {e}")
            return "默认智能助手"

    async def summarize_persona(original_persona: str) -> str:
        """精简人格设定"""
        try:
            schema = {
                "type": "object",
                "properties": {
                    "summarized_persona": {
                        "type": "string",
                        "description": "精简后的角色设定，保留核心特征和行为方式，100-200字以内"
                    }
                },
                "required": ["summarized_persona"]
            }

            prompt = f"""请将以下机器人角色设定总结为简洁的核心要点。
总结后的内容应该在100-200字以内，突出最重要的角色特点。

原始角色设定：
{original_persona}"""

            result = await schemaReplyCore(
                config, schema, prompt,
                keep_history=False, user_id=0
            )

            summarized = result.get("summarized_persona", "")
            if summarized and len(summarized.strip()) > 10:
                bot.logger.info(f"心流插件：人格精简完成 {len(original_persona)} -> {len(summarized)}")
                return summarized

            return original_persona
        except Exception as e:
            bot.logger.error(f"心流插件：精简人格失败 {e}")
            return original_persona

    async def judge_should_reply(event: GroupMessageEvent) -> JudgeResult:
        """判断是否应该回复"""
        try:
            chat_state = get_chat_state(event.group_id)
            persona = await get_persona_prompt(event.user_id)

            group_messages_bg = await get_last_20_and_convert_to_prompt(
                event.group_id, config.ai_llm.config["heartflow"]["context_messages_count"], "gemini", bot
            )

            schema = {
                "type": "object",
                "properties": {
                    "relevance": {
                        "type": "number",
                        "description": "内容相关度(0-10)：消息是否有趣、有价值、适合回复",
                        "minimum": 0, "maximum": 10
                    },
                    "willingness": {
                        "type": "number",
                        "description": "回复意愿(0-10)：基于当前精力和状态的回复意愿",
                        "minimum": 0, "maximum": 10
                    },
                    "social": {
                        "type": "number",
                        "description": "社交适宜性(0-10)：在当前群聊氛围下回复是否合适",
                        "minimum": 0, "maximum": 10
                    },
                    "timing": {
                        "type": "number",
                        "description": "时机恰当性(0-10)：回复时机是否恰当",
                        "minimum": 0, "maximum": 10
                    },
                    "continuity": {
                        "type": "number",
                        "description": "对话连贯性(0-10)：当前消息与上次回复的关联程度",
                        "minimum": 0, "maximum": 10
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "详细分析原因"
                    }
                },
                "required": ["relevance", "willingness", "social", "timing", "continuity", "reasoning"]
            }

            recent_messages = "\n---\n".join([
                msg.get("text", "") for msg in group_messages_bg[-5:]
                if msg.get("role") in ["user", "model"]
            ]) if group_messages_bg else "暂无对话历史"
            reply_threshold = config.ai_llm.config['heartflow']['reply_threshold']
            prompt = f"""你是群聊机器人的决策系统，判断是否应该主动回复。

                ## 机器人角色设定
                {persona}
                
                ## 当前群聊情况
                - 群聊ID: {event.group_id}
                - 精力水平: {chat_state.energy:.1f}/1.0
                - 上次发言: {get_minutes_since_last_reply(event.group_id)}分钟前
                - 回复率: {(chat_state.total_replies / max(1, chat_state.total_messages) * 100):.1f}%
                
                ## 最近对话
                {recent_messages}
                
                ## 待判断消息
                发送者: {event.sender.nickname}
                内容: {event.pure_text}
                时间: {datetime.datetime.now().strftime('%H:%M:%S')}
                
                回复阈值: {reply_threshold}
                请从5个维度评估（0-10分）。"""

            result = await schemaReplyCore(
                config, schema, prompt,
                keep_history=False, user_id=0,
                group_messages_bg=group_messages_bg
            )

            overall_score = (
                                    result["relevance"] * weights["relevance"] +
                                    result["willingness"] * weights["willingness"] +
                                    result["social"] * weights["social"] +
                                    result["timing"] * weights["timing"] +
                                    result["continuity"] * weights["continuity"]
                            ) / 10.0

            should_reply = overall_score >= reply_threshold

            bot.logger.info(
                f"心流判断 | 群:{event.group_id} | 评分:{overall_score:.2f} | "
                f"回复:{should_reply} | 理由:{result['reasoning'][:30]}..."
            )

            return JudgeResult(
                relevance=result["relevance"],
                willingness=result["willingness"],
                social=result["social"],
                timing=result["timing"],
                continuity=result["continuity"],
                reasoning=result["reasoning"],
                should_reply=should_reply,
                confidence=overall_score,
                overall_score=overall_score
            )
        except Exception as e:
            bot.logger.error(f"心流判断异常: {e}")
            return JudgeResult(should_reply=False, reasoning=f"异常: {str(e)}")

    # ============ 消息处理逻辑（复制自原框架）============

    async def handle_message(event: GroupMessageEvent, user_info=None):
        """处理消息的核心逻辑（从原框架复制）"""
        uid = event.user_id
        if user_info is None:
            user_info = await get_user(event.user_id, event.sender.nickname)

        if uid not in user_state:
            user_state[uid] = {
                "queue": asyncio.Queue(),
                "running": False
            }

        await user_state[uid]["queue"].put(event)

        if user_state[uid]["running"]:
            bot.logger.info(f"用户{uid}正在处理中，已放入队列")
            return

        async def process_user_queue(uid):
            user_state[uid]["running"] = True
            try:
                current_event = await user_state[uid]["queue"].get()
                try:

                    reply_message = await aiReplyCore(
                        current_event.processed_message,
                        current_event.user_id,
                        config,
                        tools=tools,
                        bot=bot,
                        event=current_event,
                        do_not_read_context=True,
                    )

                    if reply_message is None or '' == str(reply_message) or 'Maximum recursion depth' in reply_message:
                        return

                    if "call_send_mface(summary='')" in reply_message:
                        reply_message = reply_message.replace("call_send_mface(summary='')", '')

                    try:
                        tokens_total = count_tokens_approximate(
                            current_event.processed_message[1]['text'],
                            reply_message, user_info.ai_token_record
                        )
                        await update_user(user_id=current_event.user_id, ai_token_record=tokens_total)
                    except:
                        pass

                    await send_text(bot, current_event, config, reply_message.strip())

                except Exception as e:
                    bot.logger.exception(f"用户 {uid} 处理出错: {e}")
                finally:
                    user_state[uid]["queue"].task_done()

                    if not user_state[uid]["queue"].empty():
                        asyncio.create_task(process_user_queue(uid))
            finally:
                user_state[uid]["running"] = False

        asyncio.create_task(process_user_queue(uid))

    # ============ 事件处理器 ============

    @bot.on(GroupMessageEvent)
    async def heartflow_handler(event: GroupMessageEvent):
        """心流主动回复处理"""

        # 跳过命令和bot自己的消息
        if event.pure_text and event.pure_text.startswith("/"):
            return
        if event.user_id == bot.id:
            return
        if not event.pure_text or not event.pure_text.strip():
            return

        # 白名单检查
        if config.ai_llm.config["heartflow"]["whitelist_enabled"]:
            if event.group_id not in config.ai_llm.config["heartflow"]["chat_whitelist"]:
                return

        # 心流判断
        if config.ai_llm.config["heartflow"]["enabled"]:
            try:
                judge_result = await judge_should_reply(event)

                if judge_result.should_reply:
                    bot.logger.info(
                        f"🔥 心流触发 | 群:{event.group_id} | 评分:{judge_result.overall_score:.2f}"
                    )

                    # 权限检查
                    user_info = await get_user(event.user_id, event.sender.nickname)
                    if not user_info.permission >= config.ai_llm.config["core"]["ai_reply_group"]:
                        return

                    if event.group_id in [913122269, 1050663831] and not user_info.permission >= 66:
                        return

                    if not user_info.permission >= config.ai_llm.config["core"]["ai_token_limt"]:
                        if user_info.ai_token_record >= config.ai_llm.config["core"]["ai_token_limt_token"]:
                            return

                    # 更新状态并处理消息
                    update_active_state(event.group_id, event.user_id)
                    await handle_message(event, user_info)
                    return
                else:
                    update_passive_state(event.group_id)

            except Exception as e:
                bot.logger.error(f"心流处理异常: {e}")



    # ============ 管理命令 ============

    @bot.on(GroupMessageEvent)
    async def heartflow_commands(event: GroupMessageEvent):
        """心流管理命令"""
        if not event.pure_text:
            return

        if event.pure_text == "/heartflow":
            reply_threshold = config.ai_llm.config['heartflow']['reply_threshold']
            whitelist_enabled = config.ai_llm.config['heartflow']['whitelist_enabled']
            enabled = config.ai_llm.config['heartflow']['enabled']
            state = get_chat_state(event.group_id)
            status = f"""🔮 心流状态报告

📊 **当前状态**
- 群聊ID: {event.group_id}
- 精力水平: {state.energy:.2f}/1.0 {'🟢' if state.energy > 0.7 else '🟡' if state.energy > 0.3 else '🔴'}
- 上次回复: {get_minutes_since_last_reply(event.group_id)}分钟前

📈 **历史统计**
- 总消息数: {state.total_messages}
- 总回复数: {state.total_replies}
- 回复率: {(state.total_replies / max(1, state.total_messages) * 100):.1f}%
- 活跃用户: {len(state.recent_interactions)}人

⚙️ **配置**
- 回复阈值: {reply_threshold}
- 白名单: {'✅' if whitelist_enabled else '❌'}
- 状态: {'✅ 启用' if enabled else '❌ 禁用'}

🎯 **权重**
- 相关度: {weights['relevance']:.0%}
- 意愿: {weights['willingness']:.0%}
- 社交: {weights['social']:.0%}
- 时机: {weights['timing']:.0%}
- 连贯: {weights['continuity']:.0%}"""
            await bot.send(event, status)

        elif event.pure_text == "/heartflow_reset":
            if event.group_id in chat_states:
                del chat_states[event.group_id]
            await bot.send(event, "✅ 心流状态已重置")

        elif event.pure_text == "/heartflow_cache":
            info = f"🧠 人格缓存: {len(persona_cache)}个\n\n"
            if persona_cache:
                for key, value in list(persona_cache.items())[:5]:
                    info += f"🔑 {key}\n📄 {value[:80]}...\n\n"
            else:
                info += "📭 无缓存"
            await bot.send(event, info)

        elif event.pure_text == "/heartflow_cache_clear":
            count = len(persona_cache)
            persona_cache.clear()
            await bot.send(event, f"✅ 已清除 {count} 个缓存")

    bot.logger.info("心流插件已加载")


