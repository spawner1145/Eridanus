
import asyncio
import base64
import datetime
import io
import os
import re
import time
import traceback
from typing import Dict

import httpx
from PIL import Image
from dataclasses import dataclass, field

from developTools.event.events import GroupMessageEvent, LifecycleMetaEvent
from developTools.message.message_components import At
from framework_common.database_util.Group import get_last_20_and_convert_to_prompt
from framework_common.database_util.User import get_user, update_user
from framework_common.database_util.llmDB import delete_latest2_history, read_chara, use_folder_chara
from run.ai_llm.service.aiReplyCore import aiReplyCore, send_text, count_tokens_approximate
from run.ai_llm.service.heartflow_client import heartflow_request
from run.ai_llm.service.schemaReplyCore import schemaReplyCore

# 用于匹配 base64 数据URI的正则
BASE64_PATTERN = re.compile(r'^data:([^;]+);base64,(.+)$', re.DOTALL)


def is_local_file_path(url: str) -> bool:
    """检查是否是本地文件路径"""
    if url.startswith("file://"):
        return True
    if len(url) >= 2 and url[1] == ':' and url[0].isalpha():
        return True
    if url.startswith("/") and not url.startswith("//"):
        return True
    return False


def get_local_file_path(url: str) -> str:
    """获取本地文件的实际路径"""
    if url.startswith("file://"):
        return url[7:]
    return url


async def _process_image_for_heartflow(url: str, client_type: str) -> dict:
    try:
        img_base64 = None
        base64_match = BASE64_PATTERN.match(url)
        if base64_match:
            img_base64 = base64_match.group(2)
        elif is_local_file_path(url):
            actual_path = get_local_file_path(url)
            if os.path.exists(actual_path):
                image = Image.open(actual_path)
                image = image.convert("RGB")
                img_byte_arr = io.BytesIO()
                quality = 85
                while True:
                    img_byte_arr.seek(0)
                    img_byte_arr.truncate()
                    image.save(img_byte_arr, format='JPEG', quality=quality)
                    if img_byte_arr.tell() / 1024 <= 400 or quality <= 10:
                        break
                    quality -= 5
                img_base64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
                image.close()
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    image = Image.open(io.BytesIO(res.content))
                    image = image.convert("RGB")
                    img_byte_arr = io.BytesIO()
                    quality = 85
                    while True:
                        img_byte_arr.seek(0)
                        img_byte_arr.truncate()
                        image.save(img_byte_arr, format='JPEG', quality=quality)
                        if img_byte_arr.tell() / 1024 <= 400 or quality <= 10:
                            break
                        quality -= 5
                    img_base64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
                    image.close()
        
        if not img_base64:
            return None
        if client_type == "openai":
            return {"input_image": {"image_url": f"data:image/jpeg;base64,{img_base64}", "detail": "auto"}}
        else:
            return {"inlineData": {"mimeType": "image/jpeg", "data": img_base64}}
    
    except Exception as e:
        print(f"处理图片失败: {e}")
        return None


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


async def heartflow_reply(config, prompt, group_messages_bg=None, recursion_times=0, image_parts=None):
    try:
        messages = [{"text": prompt}]
        if image_parts:
            messages.extend(image_parts)
        
        result = await heartflow_request(
            config,
            messages,
            system_instruction=None,
            group_context=group_messages_bg,
        )
        
        if result:
            print(result)
        return result
        
    except Exception as e:
        traceback.print_exc()
        recursion_times += 1
        print(f"Recursion times: {recursion_times}")
        recursion_limit = config.ai_llm.config["llm"].get("retries", 3)
        if recursion_times > recursion_limit:
            return None
        return await heartflow_reply(config, prompt, group_messages_bg, recursion_times, image_parts)
def main(bot, config):
    """
    此插件代码参考了https://github.com/advent259141/Astrbot_plugin_Heartflow
    """
    """心流插件主函数"""
    summarized_chara=None
    # 获取tools配置（从原框架复制）
    tools = None
    if config.ai_llm.config["llm"]["func_calling"]:
        from framework_common.framework_util.func_map_loader import build_tool_map
        tools = build_tool_map()

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

            chara_path = f"./data/system/chara/{chara_file}"
            try:

                persona = await read_chara(user_id, await use_folder_chara(config.ai_llm.config["llm"]["chara_file_name"]))
                persona=persona.replace("{bot_name}",config.common_config.basic_config["bot"])
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
            nonlocal summarized_chara
            if summarized_chara:
                return summarized_chara
            prompt = f"""请将以下机器人角色设定总结为简洁的核心要点。
            总结后的内容应该在100-200字以内，突出最重要的角色特点。
            
            原始角色设定：
            {original_persona}"""

            result = await heartflow_reply(
                config,
                prompt,
                recursion_times=7
            )
            summarized_chara=result
            summarized = result
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

            heartflow_config = config.ai_llm.config.get("heartflow", {})
            client_config = heartflow_config.get("client", {})
            client_type = client_config.get("type", "gemini").strip().lower()
            listen_image = heartflow_config.get("listen_image", False)
            
            if client_type == "openai":
                prompt_format = "new_openai"
            else:
                prompt_format = "gemini"
            
            # 根据 listen_image 配置决定是否在群聊上下文中包含图片
            group_messages_bg = await get_last_20_and_convert_to_prompt(
                event.group_id, config.ai_llm.config["heartflow"]["context_messages_count"], prompt_format, bot,
                include_images=listen_image
            )

            # 处理图片（如果启用了listen_image）
            image_parts = []
            if listen_image and hasattr(event, 'processed_message'):
                for item in event.processed_message:
                    if "image" in item or "mface" in item:
                        try:
                            if "mface" in item:
                                url = item["mface"].get("url") or item["mface"].get("file")
                            else:
                                url = item["image"].get("url") or item["image"].get("file")
                            
                            if url:
                                img_data = await _process_image_for_heartflow(url, client_type)
                                if img_data:
                                    image_parts.append(img_data)
                        except Exception as e:
                            bot.logger.warning(f"心流插件: 处理图片失败: {e}")

            def extract_text_from_message(msg):
                """从Gemini/OpenAI格式的消息中提取文本"""
                role = msg.get("role", "")
                if role not in ["user", "model", "assistant"]:
                    return None
                
                # Gemini 格式: {"role": "user", "parts": [{"text": "..."}, ...]}
                if "parts" in msg:
                    texts = []
                    for part in msg["parts"]:
                        if isinstance(part, dict) and "text" in part:
                            texts.append(part["text"])
                    return "\n".join(texts) if texts else None
                
                # OpenAI 格式: {"role": "user", "content": [{"type": "text", "text": "..."}, ...]}
                if "content" in msg:
                    content = msg["content"]
                    if isinstance(content, str):
                        return content
                    elif isinstance(content, list):
                        texts = []
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                texts.append(item.get("text", ""))
                        return "\n".join(texts) if texts else None
                
                return None
            
            if group_messages_bg:
                recent_texts = []
                for msg in group_messages_bg[-5:]:
                    text = extract_text_from_message(msg)
                    if text:
                        recent_texts.append(text)
                recent_messages = "\n---\n".join(recent_texts) if recent_texts else "暂无对话历史"
            else:
                recent_messages = "暂无对话历史"
            
            reply_threshold = config.ai_llm.config['heartflow']['reply_threshold']
            message_content_desc = event.pure_text if event.pure_text else "(无文字内容)"
            if image_parts:
                message_content_desc += f"\n(附带{len(image_parts)}张图片，见下方)"
            image_prefix_text = ""
            if image_parts and not event.pure_text:
                image_prefix_text = f"以下是用户{event.sender.nickname}发送的图片:\n"
            
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
                内容: {message_content_desc}
                时间: {datetime.datetime.now().strftime('%H:%M:%S')}
                
                回复阈值: {reply_threshold}
                请从5个维度评估（0-10分）。
                
                {image_prefix_text}"""
            prompt += """

            请根据上述信息做出判断，并按以下格式输出：

            相关度: 0-10
            意愿: 0-10
            社交: 0-10
            时机: 0-10
            连贯: 0-10
            理由: 详细说明为什么应或不应回复（结合角色特性）

            ⚠️ 请严格保持该格式，每个分数字只能写一个纯数字。
            """

            result_text = await heartflow_reply(
                config,
                prompt,
                group_messages_bg=group_messages_bg,
                image_parts=image_parts if image_parts else None
            )
            #print(result_text)
            #print(type(result_text))
            # 使用正则解析分数
            import re

            def ext(name):
                m = re.search(rf"(?:{name})\s*[:：]\s*(\d+)", result_text)
                return float(m.group(1)) if m else 0.0

            relevance = ext("相关度|内容相关度|relevance")
            willingness = ext("意愿|回复意愿|willingness")
            social = ext("社交|社交适宜性|social")
            timing = ext("时机|时机恰当性|timing")
            continuity = ext("连贯|对话连贯|continuity")


            # 提取理由
            reasoning_match = re.search(r"(理由|分析|原因)[:：]\s*(.+)", result_text, re.S)
            reasoning = reasoning_match.group(2).strip() if reasoning_match else result_text.strip()

            overall_score = (
                                    relevance * weights["relevance"] +
                                    willingness * weights["willingness"] +
                                    social * weights["social"] +
                                    timing * weights["timing"] +
                                    continuity * weights["continuity"]
                            ) / 10.0

            should_reply = overall_score >= reply_threshold
            #print(should_reply)
            r=JudgeResult(
                relevance=relevance,
                willingness=willingness,
                social=social,
                timing=timing,
                continuity=continuity,
                reasoning=reasoning,
                should_reply=should_reply,
                confidence=overall_score,
                overall_score=overall_score
            )
            print(r)
            return r

        except Exception as e:
            traceback.print_exc()
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
                    current_event.processed_message.append({"text": "(系统提示：你目前正处于群聊环境中，请根据当前上下文做出自然、长度适当的回复以融入聊天。不要让此提示信息出现在回复中。)"})
                    reply_message = await aiReplyCore(
                        current_event.processed_message,
                        current_event.user_id,
                        config,
                        tools=tools,
                        bot=bot,
                        event=current_event
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
        if event.pure_text and (event.pure_text.startswith("/") or event.pure_text.startswith("#")):
            return
        if event.user_id == bot.id:
            return

        listen_image = config.ai_llm.config.get("heartflow", {}).get("listen_image", False)
        has_text = event.pure_text and event.pure_text.strip()
        has_image = False
        if listen_image and hasattr(event, 'processed_message'):
            for item in event.processed_message:
                if "image" in item or "mface" in item:
                    has_image = True
                    break

        if not has_text and not has_image:
            return
        
        if event.message_chain.has(At):
            if event.message_chain.get(At)[0].qq in [bot.id, 1000000]:
                bot.logger.info(f"心流插件：跳过@机器人消息")
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

                    #if event.group_id in [913122269, 1050663831] and not user_info.permission >= 66:
                        #return

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


