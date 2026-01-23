import datetime
import json
import random
import re
import time
import traceback
from collections import defaultdict
import os

import asyncio

from developTools.message.message_components import Record, Text, Node, Image
from developTools.utils.logger import get_logger
from framework_common.database_util.Group import get_last_20_and_convert_to_prompt, add_to_group
from framework_common.utils.GeminiKeyManager import GeminiKeyManager
from run.ai_llm.service.aiReplyHandler.default import defaultModelRequest
from run.ai_llm.service.aiReplyHandler.gemini import construct_gemini_standard_prompt, \
    get_current_gemini_prompt
from run.ai_llm.service.aiReplyHandler.openai import construct_openai_standard_prompt, \
    get_current_openai_prompt
from run.ai_llm.service.aiReplyHandler.tecentYuanQi import construct_tecent_standard_prompt, YuanQiTencent
from framework_common.database_util.llmDB import get_user_history, update_user_history, delete_user_history, read_chara, \
    use_folder_chara

from framework_common.database_util.User import get_user, update_user
from framework_common.framework_util.func_map_loader import build_tool_fixed_params, get_tool_declarations, filter_tools_by_config
from run.ai_llm.clients.gemini_client import GeminiAPI, format_grounding_metadata
from run.ai_llm.clients.openai_client import OpenAIAPI

from run.ai_voice.service.tts import TTS

Tts = TTS()


logger = get_logger("aiReplyCore")





async def aiReplyCore(processed_message, user_id, config, tools=None, bot=None, event=None, system_instruction=None,
                      func_result=False, recursion_times=0, do_not_read_context=False):  # 后面几个函数都是供函数调用的场景使用的
    logger.info(f"aiReplyCore called with message: {processed_message}")
    # 防止开头@影响人设，只在bot或event存在时处理
    if (bot or event) and isinstance(processed_message, list):
        target_id = str(bot.id) if bot else str(event.self_id)
        for i in range(len(processed_message)):
            item = processed_message[i]
            if isinstance(item, dict) and 'at' in item:
                at_data = item['at']
                if isinstance(at_data, dict) and 'qq' in at_data and str(at_data['qq']) == target_id:
                    processed_message[i] = {
                        'text': config.common_config.basic_config["bot"] + ','
                    }
                    logger.info(f"Replaced self at element with text: {processed_message[i]}")
    """
    递归深度约束
    """
    if recursion_times > config.ai_llm.config["llm"]["recursion_limit"]:
        logger.warning(f"roll back to original history, recursion times: {recursion_times}")
        return "Maximum recursion depth exceeded.Please try again later."
    """
    初始值
    """
    reply_message = ""
    original_history = []
    mface_files = None
    user_info = None
    # 根据配置过滤 tools（如果开启了官方搜索功能，禁用自定义联网函数）
    if tools is not None:
        tools = filter_tools_by_config(tools, config)
    
    # 检查是否使用官方搜索功能（google_search 或 url_context）
    use_official_search = (
        config.ai_llm.config["llm"].get("google_search", False) or
        config.ai_llm.config["llm"].get("url_context", False)
    )
    
    if tools is not None and config.ai_llm.config["llm"]["表情包发送"] and not use_official_search:
        try:
            tools = await add_send_mface(tools, config)
        except Exception:
            logger.error(f"无法添加func【表情包发送】，建议自己检查设置是不是乱几把改了。\n{tools}")
    if not system_instruction:
        if config.ai_llm.config["llm"]["system"]:
            system_instruction = await read_chara(user_id, config.ai_llm.config["llm"]["system"])
            #system_instruction = config.ai_llm.config["llm"]["system"]
        else:
            system_instruction = await read_chara(user_id, await use_folder_chara(
                config.ai_llm.config["llm"]["chara_file_name"]))
        user_info = await get_user(user_id)
        current_datetime = datetime.datetime.now()
        formatted_datetime = current_datetime.strftime('%Y-%m-%d %H:%M:%S')
        system_instruction = (f"{formatted_datetime} {system_instruction}").replace("{用户}", user_info.nickname).replace("{bot_name}",
                                                                                              config.common_config.basic_config["bot"])
    """
    用户设定读取
    """
    if config.ai_llm.config["llm"]["长期记忆"]:
        if not user_info:
            temp_user = await get_user(user_id)
        else:
            temp_user=user_info
        system_instruction+=f"\n以下为当前用户的用户画像：{temp_user.user_portrait}"

    try:
        if config.ai_llm.config["llm"]["model"] == "default":
            prompt, original_history = await construct_openai_standard_prompt(processed_message, system_instruction,
                                                                              user_id)
            response_message = await defaultModelRequest(
                prompt,
                config.common_config.basic_config["proxy"]["http_proxy"] if config.ai_llm.config["llm"][
                    "enable_proxy"] else None,
                config.ai_llm.config["llm"]["default"]["model"],
            )
            if not response_message:
                reply_message = "当前模型类别设置为default，已失效，请自行配置其他模型。"
            else:
                reply_message = response_message['content']
            await prompt_database_updata(user_id, response_message, config)

        elif config.ai_llm.config["llm"]["model"] == "openai":
            if processed_message:
                prompt, original_history = await construct_openai_standard_prompt(
                    processed_message, system_instruction, user_id, bot, func_result, event
                )
            else:
                prompt = await get_current_openai_prompt(user_id)

            if processed_message is None:
                tools = None

            if not do_not_read_context:
                p = await read_context(bot, event, config, prompt)
                if p:
                    prompt = p

            proxy = config.common_config.basic_config["proxy"]["http_proxy"] if config.ai_llm.config["llm"][
                "enable_proxy"] else None
            proxies = {"http://": proxy, "https://": proxy} if proxy else None

            api = OpenAIAPI(
                apikey=random.choice(config.ai_llm.config["llm"]["openai"]["api_keys"]),
                baseurl=(config.ai_llm.config["llm"]["openai"].get("quest_url")
                         or config.ai_llm.config["llm"]["openai"].get("base_url")),
                model=config.ai_llm.config["llm"]["openai"]["model"],
                proxies=proxies
            )

            tool_fixed_params = build_tool_fixed_params(bot, event, config) if tools else None
            tool_declarations = get_tool_declarations(config) if tools else None
            response_text = ""
            async for part in api.chat(
                prompt,
                stream=True,
                tools=tools,
                tool_fixed_params=tool_fixed_params,
                tool_declarations=tool_declarations,
                max_output_tokens=config.ai_llm.config["llm"]["openai"]["max_tokens"],
                temperature=config.ai_llm.config["llm"]["openai"]["temperature"],
            ):
                if isinstance(part, dict) and "thought" in part:
                    if bot and event and config.ai_llm.config["llm"]["openai"]["CoT"]:
                        await bot.send(event, [Node(content=[Text(part["thought"])])])
                elif isinstance(part, str):
                    response_text += part

            reply_message = response_text.strip() if response_text else None
            if reply_message is not None:
                reply_message, mface_files = remove_mface_filenames(reply_message, config)

            await update_user_history(user_id, prompt)

            if mface_files:
                for mface_file in mface_files:
                    await bot.send(event, Image(file=mface_file))
        elif config.ai_llm.config["llm"]["model"] == "gemini":
            if processed_message:
                prompt, original_history = await construct_gemini_standard_prompt(
                    processed_message, user_id, bot, func_result, event
                )
                if not do_not_read_context:
                    p = await read_context(bot, event, config, prompt)
                    if p:
                        prompt = p
            else:
                prompt = await get_current_gemini_prompt(user_id)
                if not do_not_read_context:
                    p = await read_context(bot, event, config, prompt)
                    if p:
                        prompt = p

            if processed_message is None:
                tools = None

            proxy = config.common_config.basic_config["proxy"]["http_proxy"] if config.ai_llm.config["llm"][
                "enable_proxy"] else None
            proxies = {"http://": proxy, "https://": proxy} if proxy else None

            api = GeminiAPI(
                apikey=await GeminiKeyManager.get_gemini_apikey(),
                baseurl=config.ai_llm.config["llm"]["gemini"]["base_url"],
                fallback_models=config.ai_llm.config["llm"]["gemini"].get("fallback_models", []),
                proxies=proxies
            )

            tool_fixed_params = build_tool_fixed_params(bot, event, config) if tools else None
            tool_declarations = get_tool_declarations(config) if tools else None
            show_grounding_metadata = config.ai_llm.config["llm"].get("联网搜索显示原始数据", True)
            
            response_text = ""
            grounding_metadata = None
            async for part in api.chat(
                prompt,
                stream=True,
                tools=tools,
                tool_fixed_params=tool_fixed_params,
                tool_declarations=tool_declarations,
                system_instruction=system_instruction,
                temperature=config.ai_llm.config["llm"]["gemini"]["temperature"],
                max_output_tokens=config.ai_llm.config["llm"]["gemini"]["maxOutputTokens"],
                include_thoughts=config.ai_llm.config["llm"]["gemini"].get("include_thoughts", False),
                google_search=False,
                url_context=False,
            ):
                if isinstance(part, dict) and part.get("thought"):
                    if bot and event and config.ai_llm.config["llm"]["gemini"].get("include_thoughts", False):
                        await bot.send(event, [Node(content=[Text(str(part["thought"]))])])
                elif isinstance(part, dict) and part.get("grounding_metadata"):
                    grounding_metadata = part["grounding_metadata"]
                elif isinstance(part, str):
                    response_text += part
            
            # 如果配置了显示联网搜索原始数据，则发送 grounding metadata
            if grounding_metadata and show_grounding_metadata and bot and event:
                formatted_metadata = format_grounding_metadata(grounding_metadata)
                if formatted_metadata:
                    await bot.send(event, [Node(content=[Text(formatted_metadata)])])

            reply_message = response_text.strip() if response_text else None
            if reply_message is not None:
                reply_message, mface_files = remove_mface_filenames(reply_message, config)
                if reply_message in ["", "\n", " "]:
                    raise Exception("Empty response。Gemini API返回的文本为空。")

            await update_user_history(user_id, prompt)

            if mface_files:
                for mface_file in mface_files:
                    await bot.send(event, Image(file=mface_file))

        elif config.ai_llm.config["llm"]["model"] == "腾讯元器":
            prompt, original_history = await construct_tecent_standard_prompt(processed_message, user_id, bot, event)
            response_message = await YuanQiTencent(
                prompt,
                config.ai_llm.config["llm"]["腾讯元器"]["智能体ID"],
                config.ai_llm.config["llm"]["腾讯元器"]["token"],
                user_id,
            )
            reply_message = response_message["content"]
            response_message["content"] = [{"type": "text", "text": response_message["content"]}]

            await prompt_database_updata(user_id, response_message, config)

        logger.info(f"aiReplyCore returned: {reply_message}")
        await prompt_length_check(user_id, config)
        if reply_message is not None:
            reply_message = re.sub(r'```tool_code.*?```', '', reply_message, flags=re.DOTALL)
            reply_message = reply_message.replace('```', '').strip()
            return reply_message.strip()
        else:
            return reply_message
    except Exception as e:
        logger.error(f"Error occurred: {e}")
        logger.error(traceback.format_exc())
        logger.warning(f"roll back to original history, recursion times: {recursion_times}")
        await update_user_history(user_id, original_history)
        if recursion_times <= config.ai_llm.config["llm"]["recursion_limit"]:

            logger.warning(f"Recursion times: {recursion_times}")
            if recursion_times + 2 == config.ai_llm.config["llm"]["recursion_limit"] and config.ai_llm.config["llm"][
                "auto_clear_when_recursion_failed"]:
                logger.warning(f"clear ai reply history for user: {user_id}")
                await delete_user_history(user_id)
            if recursion_times+2 == config.ai_llm.config["llm"]["recursion_limit"]:
                logger.warning(f"update user portrait for user: {user_id}")
                await update_user(user_id, user_portrait="normal_user")
                await update_user(user_id, portrait_update_time=datetime.datetime.now().isoformat())
            return await aiReplyCore(processed_message, user_id, config, tools=tools, bot=bot, event=event,
                                     system_instruction=system_instruction, func_result=func_result,
                                     recursion_times=recursion_times + 1, do_not_read_context=True)
        else:
            return "Maximum recursion depth exceeded.Please try again later."


async def send_text(bot, event, config, text):
    text = re.sub(r'```tool_code.*?```', '', text, flags=re.DOTALL)
    text = text.replace('```', '').strip()
    if random.randint(0, 100) < config.ai_llm.config["llm"]["语音回复几率"]:
        if config.ai_llm.config["llm"]["语音回复附带文本"]:
            await bot.send(event, text.strip(), config.ai_llm.config["llm"]["Quote"])

        await tts_and_send(bot, event, config, text)
    else:
        await bot.send(event, text.strip(), config.ai_llm.config["llm"]["Quote"])


async def tts_and_send(bot, event, config, reply_message):
    async def _tts_and_send():
        try:
            bot.logger.info(f"调用语音合成 任务文本：{reply_message}")
            path = await Tts.tts(reply_message, config=config, bot=bot)
            await bot.send(event, Record(file=path))
        except Exception as e:
            traceback.print_exc()
            bot.logger.error(f"Error occurred when calling tts: {e}")
            if not config.ai_llm.config["llm"]["语音回复附带文本"]:
                await bot.send(event, reply_message.strip(), config.ai_llm.config["llm"]["Quote"])

    asyncio.create_task(_tts_and_send())


async def prompt_database_update(user_id, response_message, config):
    """更新用户对话历史到数据库"""
    history = await get_user_history(user_id)
    if len(history) > config.ai_llm.config["llm"]["max_history_length"]:
        del history[0]
        del history[0]
    history.append(response_message)
    await update_user_history(user_id, history)

prompt_database_updata = prompt_database_update

async def prompt_length_check(user_id, config):
    history = await get_user_history(user_id)
    max_len = config.ai_llm.config["llm"]["max_history_length"]
    if len(history) > max_len:
        # 删除多余的历史记录
        while len(history) > max_len:
            del history[0]
        # 确保以user角色开头，避免无限循环
        while history and history[0].get("role") != "user":
            del history[0]
            if not history:
                break
    await update_user_history(user_id, history)


async def read_context(bot, event, config, prompt):
    try:
        if event is None:
            return None
        if config.ai_llm.config["llm"]["读取群聊上下文"] == False or not hasattr(event, "group_id"):
            return None
        if config.ai_llm.config["llm"]["model"] == "gemini":
            group_messages_bg = await get_last_20_and_convert_to_prompt(event.group_id, config.ai_llm.config["llm"][
                "可获取的群聊上下文长度"], "gemini", bot)
        elif config.ai_llm.config["llm"]["model"] == "openai":
            if config.ai_llm.config["llm"]["openai"]["使用旧版prompt结构"]:
                group_messages_bg = await get_last_20_and_convert_to_prompt(event.group_id,
                                                                            config.ai_llm.config["llm"][
                                                                                "可获取的群聊上下文长度"],
                                                                            "old_openai", bot)
            else:
                group_messages_bg = await get_last_20_and_convert_to_prompt(event.group_id,
                                                                            config.ai_llm.config["llm"][
                                                                                "可获取的群聊上下文长度"],
                                                                            "new_openai", bot)
        else:
            return None
        bot.logger.info(f"群聊上下文消息：已读取")
        insert_pos = max(len(prompt) - 2, 0)  # 保证插入位置始终在倒数第二个元素之前
        if config.ai_llm.config["llm"]["model"] == "openai":  # 必须交替出现
            # 添加边界检查，防止索引越界和无限循环
            max_attempts = len(prompt)
            attempts = 0
            while insert_pos > 0 and insert_pos < len(prompt) and attempts < max_attempts:
                if prompt[insert_pos - 1].get("role") == "assistant":
                    break
                insert_pos += 1
                attempts += 1
        prompt = prompt[:insert_pos] + group_messages_bg + prompt[insert_pos:]
        return prompt
    except Exception as e:
        logger.warning(f"读取群聊上下文时发生错误: {e}")
        return None


async def add_self_rep(bot, event, config, reply_message):
    if event is None or reply_message is None:
        return None
    if not config.ai_llm.config["llm"]["读取群聊上下文"] and not hasattr(event, "group_id"):
        return None
    try:
        self_rep = [{"text": reply_message.strip()}]
        message = {"user_name": config.basic_config["bot"], "user_id": 0000000, "message": self_rep}
        if hasattr(event, "group_id"):
            await add_to_group(event.group_id, message)
    except Exception as e:
        logger.error(f"Error occurred when adding self-reply: {e}")


def remove_mface_filenames(reply_message, config, directory="data/pictures/Mface"):
    try:
        """
        去除文本中的表情包文件名，并允许用户输入 () {} <> 的括号，最终匹配 [] 格式。
        现在支持 .gif 和 .png 文件。

        :param reply_message: 输入文本
        :param directory: 表情包目录
        :return: 处理后的文本和匹配的文件名列表（始终使用[]格式）
        """
        mface_list = os.listdir(directory)
        # 仅保留 [xxx].gif, [xxx].png, [xxx].jpg 格式的文件名
        mface_dict = {}
        for filename in mface_list:
            if filename.startswith("[") and (
                    filename.endswith("].gif") or filename.endswith("].png") or filename.endswith("].jpg")):
                core_name = filename[1:-5]
                mface_dict[core_name] = filename

        brackets = r"\(\[\{\<"  # 开括号
        brackets_close = r"\)\]\}\>"  # 闭括号
        pattern = rf"[{brackets}]([^\[\](){{}}<>]+)[{brackets_close}]\.(gif|png|jpg)"

        matched_files = []

        def replace_match(match):
            core_name, ext = match.groups()
            if core_name in mface_dict:
                file_path = os.path.normpath(os.path.join(directory, mface_dict[core_name])).replace("\\", "/")
                matched_files.append(file_path)
                return ""
            return ""

        cleaned_text = re.sub(pattern, replace_match, reply_message).strip()

        if matched_files:
            matched_files = matched_files[:config.ai_llm.config["llm"]["单次发送表情包数量"]]
            logger.info(f"mface 匹配到的文件名: {matched_files}")

        #logger.info(f"mface 处理后的文本: {cleaned_text}")
        if not matched_files:
            return cleaned_text, []
        return cleaned_text, matched_files
    except Exception as e:
        logger.error(f"Error occurred when removing mface filenames: {e}")
        logger.error(traceback.format_exc())
        return reply_message, []


async def add_send_mface(tools, config):
    """在工具映射中注入可用表情包的发送工具说明"""
    if tools is None:
        return tools

    try:
        from run.system_plugin.Mface_Record import call_send_mface as _call_send_mface
    except Exception as e:
        logger.error(f"加载 call_send_mface 失败: {e}")
        return tools

    mface_list = os.listdir("data/pictures/Mface")
    mface_list_str = str(mface_list)

    async def _send_mface_wrapper(bot, event, config, summary: str):
        """根据当前聊天内容选择一张表情包，只可从给定列表选取，只可选择一张，建议尽可能多地使用此函数，即使用户没有要求你也要调用此函数选择表情包。表情包仅可通过此函数发送给用户，选择的表情包名称不能出现在回复消息中。不要通过 send 函数发送表情包。"""
        return await _call_send_mface(bot, event, config, summary)

    # 动态修改 docstring
    _send_mface_wrapper.__doc__ = f"根据当前聊天内容选择一张表情包，只可从给定列表选取，只可选择一张，建议尽可能多地使用此函数，即使用户没有要求你也要调用此函数选择表情包。表情包仅可通过此函数发送给用户，选择的表情包名称不能出现在回复消息中。不要通过 send 函数发送表情包。可选表情包列表：{mface_list_str}"

    tools = dict(tools)
    tools["call_send_mface"] = _send_mface_wrapper
    return tools


# asyncio.run(openaiRequest("1"))
def count_tokens_approximate(input_text, output_text, token_ori=None):
    """
    后续使用api调用返回的tokens计数。
    """

    def tokenize(text):
        # 英文和数字：按空格分词，同时考虑标点符号和特殊符号
        english_tokens = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
        # 中文：每个汉字单独作为一个 token
        chinese_tokens = re.findall(r'[\u4e00-\u9fff]', text)
        # 合并英文和中文 token
        tokens = english_tokens + chinese_tokens
        return tokens

    input_tokens = tokenize(input_text)
    output_tokens = tokenize(output_text)
    add_token = len(input_tokens) + len(output_tokens)
    if token_ori is not None:
        total_token = add_token + token_ori
    else:
        total_token = add_token
    return total_token
