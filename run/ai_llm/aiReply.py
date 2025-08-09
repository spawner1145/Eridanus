import asyncio
import datetime
import random
import traceback

from developTools.event.events import GroupMessageEvent, PrivateMessageEvent, LifecycleMetaEvent
from developTools.message.message_components import Text, At
from framework_common.database_util.Group import clear_group_messages, get_last_20_and_convert_to_prompt
from framework_common.database_util.Group import get_group_messages
from framework_common.database_util.User import get_user, update_user
from framework_common.database_util.llmDB import delete_user_history, clear_all_history, change_folder_chara, \
    get_folder_chara, set_all_users_chara, clear_all_users_chara, clear_user_chara, delete_latest2_history
from framework_common.framework_util.func_map_loader import gemini_func_map, openai_func_map
from framework_common.utils.GeminiKeyManager import GeminiKeyManager
from run.ai_llm.service.aiReplyCore import aiReplyCore, end_chat, judge_trigger, send_text, count_tokens_approximate
from run.ai_llm.service.auto_talk import check_message_similarity
from run.ai_llm.service.schemaReplyCore import schemaReplyCore


def main(bot, config):
    apikey_check = False
    removed_keys=[]

    if config.ai_llm.config["llm"]["func_calling"]:
        if config.ai_llm.config["llm"]["model"] == "gemini":
            tools = gemini_func_map()
        else:
            tools = openai_func_map()

    else:
        tools = None

    if config.ai_llm.config["llm"]["联网搜索"]:
        if config.ai_llm.config["llm"]["model"] == "gemini":
            if tools is None:
                tools = [

                    {"googleSearch": {}},
                ]
            else:
                tools = [
                    {"googleSearch": {}},
                    tools
                ]
        else:
            if tools is None:
                tools = [{"type": "function", "function": {"name": "googleSearch"}}]
            else:
                tools = [
                    {"type": "function", "function": {"name": "googleSearch"}},
                    tools
                ]

    global user_state
    user_state = {}

    @bot.on(GroupMessageEvent)
    async def aiReply(event: GroupMessageEvent):
        await check_commands(event)
        if (event.message_chain.has(At) and event.message_chain.get(At)[0].qq in [bot.id,1000000]) or prefix_check(str(event.pure_text), config.ai_llm.config["llm"]["prefix"]) or await judge_trigger(event.processed_message, event.user_id, config, tools=tools, bot=bot,event=event):  #触发cd判断
            bot.logger.info(f"接受消息{event.processed_message}")

            ## 权限判断
            user_info = await get_user(event.user_id, event.sender.nickname)
            if not user_info.permission >= config.ai_llm.config["core"]["ai_reply_group"]:
                await bot.send(event, "你没有足够的权限使用该功能~")
                return
            if event.group_id == 913122269 and not user_info.permission >= 66:
                #await bot.send(event,"你没有足够的权限使用该功能哦~")
                return
            if not user_info.permission >= config.ai_llm.config["core"]["ai_token_limt"]:
                if user_info.ai_token_record >= config.ai_llm.config["core"]["ai_token_limt_token"]:
                    await bot.send(event, "您的ai对话token已用完，请耐心等待下一次刷新～～")
                    return
            await handle_message(event)

        elif config.ai_llm.config["llm"]["仁济模式"]["随机回复概率"] > 0:  # 仁济模式第一层(随机)
            if random.randint(1, 100) < config.ai_llm.config["llm"]["仁济模式"]["随机回复概率"]:
                bot.logger.info(f"接受消息{event.processed_message}")

                ## 权限判断
                user_info = await get_user(event.user_id, event.sender.nickname)
                if not user_info.permission >= config.ai_llm.config["core"]["ai_reply_group"]:
                    return
                if event.group_id == 913122269 and not user_info.permission >= 66:
                    return
                if not user_info.permission >= config.ai_llm.config["core"]["ai_token_limt"]:
                    if user_info.ai_token_record >= config.ai_llm.config["core"]["ai_token_limt_token"]:
                        return
                await handle_message(event)

        elif config.ai_llm.config["llm"]["仁济模式"]["算法回复"]["enable"]:  # 仁济模式第二层(算法判断)
            sentences = await get_group_messages(event.group_id, config.ai_llm.config["llm"]["可获取的群聊上下文长度"])
            if await check_message_similarity(str(event.pure_text), sentences,
                                              similarity_threshold=config.ai_llm.config["llm"]["仁济模式"]["算法回复"][
                                                  "相似度阈值"],
                                              frequency_threshold=config.ai_llm.config["llm"]["仁济模式"]["算法回复"][
                                                  "频率阈值"],
                                              min_list_size=config.ai_llm.config["llm"]["仁济模式"]["算法回复"][
                                                  "消息列表最小长度"],
                                              entropy_threshold=config.ai_llm.config["llm"]["仁济模式"]["算法回复"][
                                                  "信息熵阈值"]):
                bot.logger.info(f"接受消息{event.processed_message}")

                ## 权限判断
                user_info = await get_user(event.user_id, event.sender.nickname)
                if not user_info.permission >= config.ai_llm.config["core"]["ai_reply_group"]:
                    return
                if event.group_id == 913122269 and not user_info.permission >= 66:
                    return
                if not user_info.permission >= config.ai_llm.config["core"]["ai_token_limt"]:
                    if user_info.ai_token_record >= config.ai_llm.config["core"]["ai_token_limt_token"]:
                        return
                await handle_message(event)

    async def handle_message(event):
        global user_state
        # 锁机制
        uid = event.user_id
        user_info = await get_user(event.user_id)
        # 初始化该用户的状态
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
                    )
                    if reply_message is None or '' == str(
                            reply_message) or 'Maximum recursion depth' in reply_message:
                        return
                    # print(f'reply_message:{reply_message}')
                    if "call_send_mface(summary='')" in reply_message:
                        reply_message = reply_message.replace("call_send_mface(summary='')", '')
                    # print(f"{current_event.processed_message[1]['text']}\n{reply_message}")
                    try:
                        tokens_total = count_tokens_approximate(current_event.processed_message[1]['text'],
                                                                reply_message, user_info.ai_token_record)
                        await update_user(user_id=event.user_id, ai_token_record=tokens_total)
                    except:
                        pass
                    await send_text(bot, event, config, reply_message.strip())
                except Exception as e:
                    bot.logger.exception(f"用户 {uid} 处理出错: {e}")
                finally:
                    user_state[uid]["queue"].task_done()
                    """
                    判断用户是否有继续对话的意图
                    """
                    if config.ai_llm.config["llm"]["自主继续对话"]:
                        schema = {
                            "type": "object",
                            "properties": {
                                "continue_intent": {
                                    "type": "boolean",
                                    "description": "用户是否表现出想要继续交流的意愿（如：提出问题、分享想法、表达情感、寻求建议等）"
                                },
                                "conversation_energy": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                    "description": "当前对话的活跃度：high-热烈讨论中，medium-正常交流，low-话题将结束"
                                },
                                "topic_openness": {
                                    "type": "boolean",
                                    "description": "当前话题是否还有延展空间"
                                }
                            },
                            "required": ["continue_intent", "conversation_energy", "topic_openness"]
                        }
                        if hasattr(event,"group_id"):
                            group_messages_bg = await get_last_20_and_convert_to_prompt(event.group_id,
                                                                                        config.ai_llm.config["llm"][
                                                                                            "可获取的群聊上下文长度"],
                                                                                        "gemini", bot)
                        else:
                            group_messages_bg = []

                        result = await schemaReplyCore(
                            config,
                            schema,
                            "分析用户的对话意图和当前聊天氛围，判断是否适合继续交流",
                            user_id=event.user_id,
                            group_messages_bg=group_messages_bg,
                        )
                        if result["continue_intent"] and result["topic_openness"]:
                            # 根据对话活跃度选择不同的回应风格
                            if result["conversation_energy"] == "high":
                                prompt = """继续参与这个热烈的话题讨论。你可以：
                                    - 分享相关的个人看法或经历
                                    - 提出有趣的相关问题
                                    - 对刚才的观点表达认同或不同意见
                                    - 补充新的信息或角度
                                    保持自然随意的语调，就像朋友间的聊天。"""

                            elif result["conversation_energy"] == "medium":
                                prompt = """以轻松自然的方式延续对话。你可以：
                                - 对刚才的话题表达看法
                                - 分享类似经历或想法
                                - 适当提问了解对方更多想法
                                - 引入相关但新鲜的话题角度
                                避免过于正式，保持聊天的随意感。"""

                            else:
                                prompt = """话题似乎要结束了，你可以：
                                - 简单表达对刚才内容的感受
                                - 温和地转向相关的新话题
                                - 分享一个轻松的相关想法
                                - 或者让对话自然结束
                                不要强行延续，保持自然。"""

                            reply_message = await aiReplyCore(
                                [{'text': f'system: {prompt}'}],
                                current_event.user_id,
                                config,
                                system_instruction="你是群聊/私聊中的一员，以自然、真实的方式参与对话。有自己的观点和情感，不要显得过于完美或机械。可以表达疑惑、好奇、认同或不同意见，就像真正的朋友一样交流。",
                                bot=bot,
                                event=current_event,
                            )
                            await send_text(bot, event, config, reply_message.strip())
                    #print(user_state[uid]["queue"])
                    """
                    总结用户特征，伪长期记忆人格
                    """
                    if config.ai_llm.config["llm"]["长期记忆"]:
                        if user_info.portrait_update_time == "" or (
                                datetime.datetime.now() - datetime.datetime.fromisoformat(
                                user_info.portrait_update_time)).total_seconds() > config.ai_llm.config["llm"][
                            "记忆更新间隔"]:
                            bot.logger.info(f"更新用户 {event.user_id} 设定")
                            reply_message = await aiReplyCore(
                                [{
                                     'text': 'system: 对以上聊天内容做出总结，描绘出当前对话的用户画像，总结出当前用户的人物性格特征以及偏好。不要回复，直接给出结果'}],
                                current_event.user_id,
                                config,
                                system_instruction="请总结上下文",
                                bot=bot,
                                event=current_event,
                            )
                            await update_user(event.user_id, user_portrait=reply_message.strip())
                            await update_user(event.user_id, portrait_update_time=datetime.datetime.now().isoformat())
                            await delete_latest2_history(event.user_id)
                    if not user_state[uid]["queue"].empty():
                        asyncio.create_task(process_user_queue(uid))
            finally:
                user_state[uid]["running"] = False

        asyncio.create_task(process_user_queue(uid))

    async def check_commands(event):
        if event.message_chain.has(Text):
            t = event.message_chain.get(Text)[0].text.strip()
        else:
            t = ""
        user_info = await get_user(event.user_id)
        if event.pure_text == "退出":
            await end_chat(event.user_id)
            await bot.send(event, "退出聊天~")
        elif event.pure_text == "/clear" or t == "/clear":
            await delete_user_history(event.user_id)
            await delete_user_history(int(f"{event.user_id}1024"))
            await clear_group_messages(event.group_id)
            await update_user(event.user_id, user_portrait="默认用户")
            await update_user(event.user_id, portrait_update_time=datetime.datetime.now().isoformat())
            await bot.send(event, "历史记录已清除", True)
        elif event.pure_text == "/clear group":
            await clear_group_messages(event.group_id)
            await bot.send(event, "本群消息已清除", True)
        elif event.pure_text == "/clearall" and event.user_id == config.common_config.basic_config["master"]["id"]:
            await clear_all_history()
            await bot.send(event, "已清理所有用户的对话记录")
        elif event.pure_text.startswith("/clear") and event.user_id == config.common_config.basic_config["master"][
            "id"] and event.get("at"):
            await delete_user_history(event.get("at")[0]["qq"])
            await bot.send(event, [Text("已清理与目标用户的对话记录")])
        elif event.pure_text.startswith("/切人设 ") and user_info.permission >= config.ai_llm.config["core"][
            "ai_change_character"]:
            chara_file = str(event.pure_text).replace("/切人设 ", "")
            if chara_file == "0":
                reply = await change_folder_chara(config.ai_llm.config["llm"]["chara_file_name"], event.user_id)
            else:
                reply = await change_folder_chara(chara_file, event.user_id)
            await bot.send(event, reply, True)
        elif event.pure_text.startswith("/全切人设 ") and event.user_id == config.common_config.basic_config["master"][
            "id"]:
            chara_file = str(event.pure_text).replace("/全切人设 ", "")
            if chara_file == "0":
                reply = await set_all_users_chara(config.ai_llm.config["llm"]["chara_file_name"])
            else:
                config.ai_llm.config["llm"]["chara_file_name"] = chara_file
                config.save_yaml("config", plugin_name="ai_llm")
                reply = await set_all_users_chara(chara_file)
            await bot.send(event, reply, True)
        elif event.pure_text == "/查人设":
            chara_file = str(event.pure_text).replace("/查人设", "")
            all_chara = await get_folder_chara()
            await bot.send(event, all_chara)

    def prefix_check(message: str, prefix: list):
        for p in prefix:
            if message.startswith(p) and p != "":
                bot.logger.info(f"消息{message}匹配到关键词{p}")
                return True
        return False

    @bot.on(PrivateMessageEvent)
    async def aiReply(event):
        # print(event.processed_message)
        # print(event.message_id,type(event.message_id))
        if event.pure_text == "/clear":
            await delete_user_history(event.user_id)
            await bot.send(event, "历史记录已清除", True)
        elif event.pure_text == "/clearall" and event.user_id == config.common_config.basic_config["master"]["id"]:
            await clear_all_history()
            await bot.send(event, "已清理所有用户的对话记录")
        else:

            bot.logger.info(f"私聊接受消息{event.processed_message}")
            user_info = await get_user(event.user_id, event.sender.nickname)
            if not user_info.permission >= config.ai_llm.config["core"]["ai_reply_private"]:
                await bot.send(event, "你没有足够的权限使用该功能哦~")
                return
            # 锁机制
            await handle_message(event)
    @bot.on(LifecycleMetaEvent)
    async def _(event: LifecycleMetaEvent):
        nonlocal apikey_check,removed_keys
        if not apikey_check:
            apikey_check = True
            while True:
                try:
                    initial_keys_from_config = config.ai_llm.config["llm"]["gemini"]["api_keys"]
                    key_manager = GeminiKeyManager(initial_api_keys=initial_keys_from_config,
                                                   check_interval_seconds=60)  # 每60秒检测一次

                    await asyncio.sleep(5)
                    bot.logger.info("\n--- 检查当前 Key 状态 ---")
                    bot.logger.info(f"可用 Key ({len(key_manager._available_keys)}个): {key_manager._available_keys}")
                    bot.logger.info(f"不可用 Key ({len(key_manager._unavailable_keys)}个): {list(key_manager._unavailable_keys.keys())}")

                    for k in list(key_manager._unavailable_keys.keys()):
                        if k not in removed_keys:
                            bot.logger.info(f"已移除不可用 Key {k} 失效理由: {key_manager._unavailable_keys[k]}")
                            await bot.send_friend_message(config.common_config.basic_config["master"]["id"],
                                                          f"已自动移除不可用apikey: {k}")
                            config.ai_llm.config["llm"]["gemini"]["api_keys"].remove(k)
                            removed_keys.append(k)
                    config.save_yaml("config", plugin_name="ai_llm")
                    await asyncio.sleep(5000)
                except Exception as e:
                    bot.logger.exception(f"检查 Key 状态出错: {e}")
                    traceback.print_exc()
                    await asyncio.sleep(60)
