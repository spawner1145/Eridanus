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
from framework_common.database_util.GroupSummary import get_group_summary
from framework_common.utils.GeminiKeyManager import GeminiKeyManager
from run.ai_llm.service.aiReplyHandler.default import defaultModelRequest
from run.ai_llm.service.aiReplyHandler.gemini import construct_gemini_standard_prompt, \
    get_current_gemini_prompt
from run.ai_llm.service.aiReplyHandler.openai import construct_openai_standard_prompt, \
    get_current_openai_prompt, construct_openai_standard_prompt_old_version
from run.ai_llm.service.aiReplyHandler.tecentYuanQi import construct_tecent_standard_prompt, YuanQiTencent
from framework_common.database_util.llmDB import get_user_history, update_user_history, delete_user_history, read_chara, \
    use_folder_chara

from framework_common.database_util.User import get_user, update_user
from framework_common.framework_util.func_map_loader import build_tool_fixed_params, get_tool_declarations, \
    filter_tools_by_config
from run.ai_llm.clients.gemini_client import GeminiAPI, format_grounding_metadata
from run.ai_llm.clients.openai_client import OpenAIAPI

from run.ai_voice.service.tts import TTS

Tts = TTS()

logger = get_logger("aiReplyCore")


async def aiReplyCore(processed_message, user_id, config, tools=None, bot=None, event=None, system_instruction=None,
                      func_result=False):
    logger.info(f"aiReplyCore called with message: {processed_message}")
    if (bot or event) and isinstance(processed_message, list):
        bot_id = str(bot.id) if bot else str(event.self_id)
        bot_name = config.common_config.basic_config["bot"]
        group_id = getattr(event, 'group_id', None) if event else None
        logger.debug(f"Looking for at elements with bot_id: {bot_id}")

        for i in range(len(processed_message)):
            item = processed_message[i]
            if isinstance(item, dict) and 'at' in item:
                at_data = item['at']
                logger.debug(f"Found at element at position {i}: {at_data}")
                at_qq = None
                if isinstance(at_data, dict) and 'qq' in at_data:
                    at_qq = str(at_data['qq'])
                elif isinstance(at_data, str):
                    at_qq = at_data

                if at_qq:
                    if at_qq == bot_id:
                        processed_message[i] = {
                            'text': f'@{bot_name}(qq号:{at_qq}) '
                        }
                        logger.info(f"Replaced @bot at position {i} with: @{bot_name}")
                    else:
                        sender_name = None
                        try:
                            if bot and group_id:
                                member_info = await bot.get_group_member_info(group_id=group_id, user_id=int(at_qq))
                                if member_info and 'data' in member_info:
                                    sender_name = member_info['data'].get('nickname')
                            if not sender_name and bot:
                                stranger_info = await bot.get_stranger_info(user_id=int(at_qq))
                                if stranger_info and 'data' in stranger_info:
                                    sender_name = stranger_info['data'].get('nickname')
                        except Exception as e:
                            logger.debug(f"Failed to get user name for {at_qq}: {e}")
                        if not sender_name:
                            sender_name = at_qq

                        processed_message[i] = {
                            'text': f'@{sender_name} '
                        }
                        logger.info(f"Replaced @{at_qq} at position {i} with: @{sender_name} ")
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
            # system_instruction = config.ai_llm.config["llm"]["system"]
        else:
            system_instruction = await read_chara(user_id, await use_folder_chara(
                config.ai_llm.config["llm"]["chara_file_name"]))
        user_info = await get_user(user_id)
        # current_datetime = datetime.datetime.now()
        # formatted_datetime = current_datetime.strftime('%Y-%m-%d %H:%M:%S')
        system_instruction = (f"{system_instruction}").replace("{用户}", user_info.nickname).replace("{bot_name}",
                                                                                                     config.common_config.basic_config[
                                                                                                         "bot"])
    """
    用户画像读取（保存 user_info 供后续注入主 prompt 使用）
    """
    if config.ai_llm.config["llm"]["用户画像"]:
        if not user_info:
            user_info = await get_user(user_id)

    try:
        if config.ai_llm.config["llm"]["model"] == "default":
            prompt, original_history = await construct_openai_standard_prompt_old_version(processed_message,
                                                                                          system_instruction,
                                                                                          user_id)
            print(prompt)
            response_message = await defaultModelRequest(
                prompt,
                None,
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

            # 先注入用户画像到主 prompt
            if config.ai_llm.config["llm"]["用户画像"] and user_info and user_info.user_portrait:
                prompt = inject_user_portrait(prompt, user_info.user_portrait, "openai")

            # 再注入群聊上下文
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
            retries = config.ai_llm.config["llm"].get("retries", 3)
            response_text = ""
            thought_text = ""  # 累积思维链内容
            async for part in api.chat(
                    prompt,
                    stream=config.ai_llm.config["llm"]["stream"],
                    tools=tools,
                    tool_fixed_params=tool_fixed_params,
                    tool_declarations=tool_declarations,
                    max_output_tokens=config.ai_llm.config["llm"]["openai"]["max_tokens"],
                    temperature=config.ai_llm.config["llm"]["openai"]["temperature"],
                    retries=retries,
            ):
                if isinstance(part, dict) and "thought" in part:
                    # 流式累积思维链
                    thought_text += str(part["thought"])
                elif isinstance(part, str):
                    response_text += part

            # 思维链累积完成后一次性发送
            if thought_text and bot and event and ((config.ai_llm.config["llm"]["openai"]["CoT"] and
                                                    config.ai_llm.config["llm"]["model"] == "openai") or (
                                                           config.ai_llm.config["llm"]["gemini"]["include_thoughts"] and
                                                           config.ai_llm.config["llm"]["model"] == "gemini")):
                await bot.send(event, [Node(content=[Text(thought_text)])])

            reply_message = response_text.strip() if response_text else None
            if reply_message is not None:
                reply_message, mface_files = remove_mface_filenames(reply_message, config)

            # 注意：不在此处保存历史记录，construct_openai_standard_prompt 已经保存了不含群聊上下文的历史

            if mface_files:
                for mface_file in mface_files:
                    await bot.send(event, Image(file=mface_file))
        elif config.ai_llm.config["llm"]["model"] == "gemini":
            if processed_message:
                prompt, original_history = await construct_gemini_standard_prompt(
                    processed_message, user_id, bot, func_result, event
                )
                # 先注入用户画像到主 prompt
                if config.ai_llm.config["llm"]["用户画像"] and user_info and user_info.user_portrait:
                    prompt = inject_user_portrait(prompt, user_info.user_portrait, "gemini")
                # 再注入群聊上下文
                p = await read_context(bot, event, config, prompt)
                if p:
                    prompt = p
            else:
                prompt = await get_current_gemini_prompt(user_id)
                # 先注入用户画像到主 prompt
                if config.ai_llm.config["llm"]["用户画像"] and user_info and user_info.user_portrait:
                    prompt = inject_user_portrait(prompt, user_info.user_portrait, "gemini")
                # 再注入群聊上下文
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
            retries = config.ai_llm.config["llm"].get("retries", 3)

            response_text = ""
            grounding_metadata = None
            thought_text = ""  # 累积思维链内容
            async for part in api.chat(
                    prompt,
                    stream=config.ai_llm.config["llm"]["stream"],
                    tools=tools,
                    tool_fixed_params=tool_fixed_params,
                    tool_declarations=tool_declarations,
                    system_instruction=system_instruction,
                    temperature=config.ai_llm.config["llm"]["gemini"]["temperature"],
                    max_output_tokens=config.ai_llm.config["llm"]["gemini"]["maxOutputTokens"],
                    include_thoughts=config.ai_llm.config["llm"]["gemini"].get("include_thoughts", False),
                    google_search=False,
                    url_context=False,
                    retries=retries,
            ):
                if isinstance(part, dict) and part.get("thought"):
                    # 流式累积思维链
                    thought_text += str(part["thought"])
                elif isinstance(part, dict) and part.get("grounding_metadata"):
                    grounding_metadata = part["grounding_metadata"]
                elif isinstance(part, str):
                    response_text += part

            # 思维链累积完成后一次性发送
            if thought_text and bot and event and config.ai_llm.config["llm"]["gemini"].get("include_thoughts", False):
                await bot.send(event, [Node(content=[Text(thought_text)])])

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

            # 注意：不在此处保存历史记录，construct_gemini_standard_prompt 已经保存了不含群聊上下文的历史

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
        # 回滚历史记录
        if original_history:
            logger.warning("Rolling back to original history")
            await update_user_history(user_id, original_history)
        # 返回None让上层处理，不再递归重试（依赖client内部的重试机制）
        return None


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


def inject_user_portrait(prompt, user_portrait, model_type):
    """
    将用户画像注入到主 prompt 中（不保存到历史记录）
    测试发现插入在用户最新消息之前效果最好（倒数第二个位置）
    """
    if not user_portrait or user_portrait in ["", "默认用户"]:
        return prompt

    portrait_text = (
        "================== 用户画像 开始 ==================\n"
        f"【系统提示】以下为当前正在与你对话的用户的画像特征：\n{user_portrait}\n"
        "================== 用户画像 结束 =================="
    )

    if model_type == "gemini":
        portrait_message = {
            "role": "user",
            "parts": [{"text": portrait_text}]
        }
        confirm_message = {
            "role": "model",
            "parts": [{"text": "好的，我已经了解了这些信息。"}]
        }
    else:  # openai
        portrait_message = {
            "role": "user",
            "content": [{"type": "text", "text": portrait_text}]
        }
        confirm_message = {
            "role": "assistant",
            "content": [{"type": "text", "text": "好的，我已经了解了这些信息。"}]
        }

    insert_pos = max(len(prompt) - 1, 0)
    prompt = prompt[:insert_pos] + [portrait_message, confirm_message] + prompt[insert_pos:]
    return prompt


async def read_context(bot, event, config, prompt):
    try:
        if event is None:
            return None
        # 检查是否开启上下文带原文功能（需要同时开启读取群聊上下文总开关）
        if not config.ai_llm.config["llm"].get("上下文带原文", False) or not hasattr(event, "group_id"):
            return None
        include_images = config.ai_llm.config["llm"].get("上下文带图片原文", False)

        if config.ai_llm.config["llm"]["model"] == "gemini":
            group_messages_bg = await get_last_20_and_convert_to_prompt(event.group_id, config.ai_llm.config["llm"][
                "可获取的群聊上下文长度"], "gemini", bot, include_images=include_images)
        elif config.ai_llm.config["llm"]["model"] == "openai":
            if config.ai_llm.config["llm"]["openai"]["使用旧版prompt结构"]:
                group_messages_bg = await get_last_20_and_convert_to_prompt(event.group_id,
                                                                            config.ai_llm.config["llm"][
                                                                                "可获取的群聊上下文长度"],
                                                                            "old_openai", bot,
                                                                            include_images=include_images)
            else:
                group_messages_bg = await get_last_20_and_convert_to_prompt(event.group_id,
                                                                            config.ai_llm.config["llm"][
                                                                                "可获取的群聊上下文长度"],
                                                                            "new_openai", bot,
                                                                            include_images=include_images)
        else:
            return None

        if not group_messages_bg:
            return None

        bot.logger.info(f"群聊上下文消息：已读取")

        insert_pos = max(len(prompt) - 1, 0)
        context_to_insert = []
        if config.ai_llm.config["llm"].get("群聊总结", {}).get("聊天带总结", False):
            group_info = await get_group_summary(event.group_id)
            group_summary = group_info.get("summary", "")
            if group_summary:
                summary_text = (
                    "================== 群聊历史总结 开始 ==================\n"
                    f"以下是本群之前的聊天总结，供你参考：\n{group_summary}\n"
                    "================== 群聊历史总结 结束 =================="
                )
                if config.ai_llm.config["llm"]["model"] == "gemini":
                    summary_message = {
                        "role": "user",
                        "parts": [{"text": summary_text}]
                    }
                else:
                    summary_message = {
                        "role": "user",
                        "content": [{"type": "text", "text": summary_text}]
                    }
                context_to_insert.append(summary_message)
                bot.logger.info(f"群聊总结已注入到prompt中")

        context_to_insert.extend(group_messages_bg)
        prompt = prompt[:insert_pos] + context_to_insert + prompt[insert_pos:]

        return prompt
    except Exception as e:
        logger.warning(f"读取群聊上下文时发生错误: {e}")
        return None


async def add_self_rep(bot, event, config, reply_message):
    if event is None or reply_message is None:
        return None
    # 只要开启了读取群聊上下文总开关，就记录bot的回复
    if not config.ai_llm.config["llm"].get("读取群聊上下文", False) or not hasattr(event, "group_id"):
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

        # logger.info(f"mface 处理后的文本: {cleaned_text}")
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
