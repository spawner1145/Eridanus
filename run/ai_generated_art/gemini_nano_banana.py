import asyncio
import base64
import traceback
from io import BytesIO
import random
import os
from typing import Optional, Dict, Any
from pathlib import Path
import json
from datetime import datetime

import httpx
from PIL import Image as PILImage

from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import Image, Text
from framework_common.database_util.User import get_user
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.utils.utils import get_img, delay_recall
from run.ai_generated_art.service.nano_banana.gemini_official_banana import call_gemini_api
from run.ai_generated_art.service.nano_banana.unofficial_banana import call_openrouter_api



# 使用记录文件路径
USAGE_FILE_PATH = Path("data/uses.json")

user_cache: Dict[int, Dict[str, Any]] = {}



def get_today_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def load_or_reset_usage_data() -> Dict[str, Any]:
    today_str = get_today_date()
    USAGE_FILE_PATH.parent.mkdir(exist_ok=True)
    if not USAGE_FILE_PATH.exists():
        new_data = {"date": today_str, "usage_data": {}}
        save_usage_data(new_data)
        return new_data
    try:
        with open(USAGE_FILE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if data.get("date") != today_str:
            new_data = {"date": today_str, "usage_data": {}}
            save_usage_data(new_data)
            return new_data
        else:
            return data
    except (json.JSONDecodeError, FileNotFoundError):
        new_data = {"date": today_str, "usage_data": {}}
        save_usage_data(new_data)
        return new_data

def save_usage_data(data: Dict[str, Any]):
    with open(USAGE_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)




def init_user_cache(user_id: int):
    if user_id not in user_cache:
        user_cache[user_id] = {
            "active": False,
            "messages": []
        }

def main(bot: ExtendBot, config):
    @bot.on(GroupMessageEvent)
    async def nano_message_handler(event: GroupMessageEvent):
        user_id = event.sender.user_id
        init_user_cache(user_id)
        current_cache = user_cache[user_id]
        pure_text = str(event.pure_text).strip()
        
        if pure_text == "#nano":
            if current_cache["active"]:
                msg = await bot.send(event, [Text("已处于监听状态，可直接发送消息或图片")], True)
                await bot.delay_recall(msg,20)
            else:
                user_info=await get_user(event.user_id)
                if user_info.permission < config.ai_generated_art.config["ai绘画"]["nano_banana不限制次数所需权限"]:
                    usage_data = load_or_reset_usage_data()
                    user_uses = usage_data.get("usage_data", {}).get(str(user_id), 0)
                    if user_uses >= config.ai_generated_art.config["ai绘画"]["nano_banana默认权限用户可用次数"]:
                        use_times=config.ai_generated_art.config["ai绘画"]["nano_banana默认权限用户可用次数"]
                        await bot.send(event, [Text(f"你今天已经达到 {use_times} 次调用上限，请明天再来吧！")], True)
                        return
                
                current_cache["active"] = True
                msg = await bot.send(event, [Text("开始监听消息，发送#ok结束并提交，#clear清空，#view查看缓存")], True)
                await delay_recall(bot, msg, 10)
            return
        
        if pure_text == "#ok":
            if not current_cache["active"]:
                return
            if not current_cache["messages"]:
                msg = await bot.send(event, [Text("输入内容为空，无法提交")], True)
                await delay_recall(bot, msg, 10)
                return
            
            messages_to_process = current_cache["messages"].copy()
            current_cache["active"] = False
            current_cache["messages"] = []
            
            text_parts = []
            image_parts = []
            
            for msg_item in messages_to_process:
                if msg_item["type"] == "text":
                    text_parts.append({"text": msg_item["content"]})
                
                elif msg_item["type"] == "image":
                    try:
                        async with httpx.AsyncClient() as client:
                            response = await client.get(msg_item["content"], timeout=30.0)
                            response.raise_for_status()
                        image_data = response.content
                        with BytesIO(image_data) as img_buffer:
                            with PILImage.open(img_buffer) as img:
                                max_size = 1024
                                if img.width > max_size or img.height > max_size:
                                    img.thumbnail((max_size, max_size))

                                processed_img = img
                                if getattr(img, 'is_animated', False):
                                    img.seek(0)
                                    processed_img = img.convert('RGB')
                                
                                with BytesIO() as output_buffer:
                                    processed_img.save(output_buffer, format="PNG")
                                    processed_image_data = output_buffer.getvalue()
                        
                        b64_data = base64.b64encode(processed_image_data).decode('utf-8')
                        
                        image_parts.append({
                            "inlineData": {
                                "mime_type": "image/png",
                                "data": b64_data
                            }
                        })
                    except Exception as e:
                        error_msg = await bot.send(event, [Text(f"处理图片时出错: {str(e)}")], True)
                        await delay_recall(bot, error_msg, 15)
                        print(f"图片处理错误详情: {traceback.format_exc()}")

            api_contents = text_parts + image_parts
            
            if not api_contents:
                msg = await bot.send(event, [Text("没有有效的内容可提交，请重新输入")], True)
                await delay_recall(bot, msg, 10)
                return
            
            processing_msg = await bot.send(event, [Text("已提交nano banana请求，正在处理...")], True)
            if not config.ai_generated_art.config["ai绘画"]["原生gemini接口"]:
                bot.logger.warning("当前nano banana使用第三方中转")
                try:
                    api_result = await call_openrouter_api(api_contents, config)
                except Exception as e:
                    traceback.print_exc()
                    api_contents=None
            else:
                api_result = await call_gemini_api(api_contents, config)
            
            await bot.recall(processing_msg)

            if api_result.get("success"):
                remaining_uses_text = ""
                # 仅当返回图片时才更新计数
                user_info=await get_user(event.user_id)
                if user_info.permission < config.ai_generated_art.config["ai绘画"]["nano_banana不限制次数所需权限"] and api_result["has_image"]:

                    usage_data = load_or_reset_usage_data()
                    current_uses = usage_data.get("usage_data", {}).get(str(user_id), 0)
                    new_uses = current_uses + 1
                    usage_data["usage_data"][str(user_id)] = new_uses
                    save_usage_data(usage_data)
                    remaining = config.ai_generated_art.config["ai绘画"]["nano_banana默认权限用户可用次数"] - new_uses
                    if remaining > 0:
                        remaining_uses_text = f"调用成功！你今天还剩下 {remaining} 次调用机会"
                    else:
                        remaining_uses_text = "今天没得🦌了"
                # 没有返回图片时的提示
                elif not api_result["has_image"]:
                    remaining_uses_text = "本次调用未生成图片，不消耗次数"
                
                message_to_send = [Text("nano banana：")]
                returned_text = api_result.get("text")
                if returned_text:
                    message_to_send.append(Text(f"\n{returned_text}"))
                result_path = api_result.get("result_path")
                if result_path and os.path.exists(result_path):
                    message_to_send.append(Image(file=result_path))
                if remaining_uses_text:
                    message_to_send.append(Text(f"\n{remaining_uses_text}"))
                if len(message_to_send) > 1:
                    await bot.send(event, message_to_send, True)
                else:
                    error_msg = await bot.send(event, [Text("处理成功，但未返回有效内容。")], True)
                    await delay_recall(bot, error_msg, 15)
            else:
                user_error_msg = [Text(f"请求处理失败: {api_result.get('error', '未知错误')}\n")]
                error_msg = await bot.send(event, user_error_msg, True)
                await delay_recall(bot, error_msg, 30)
                print(f"API调用失败详情: {api_result.get('details', '无详细信息')}")
            return

        if pure_text == "#clear":
            current_cache["messages"] = []
            current_cache["active"] = False
            msg = await bot.send(event, [Text("已清空缓存并退出监听状态，请重新发送 #nano 开始。")], True)
            await delay_recall(bot, msg, 10)
            return

        if pure_text == "#view":
            if not current_cache["messages"]:
                msg = await bot.send(event, [Text("当前缓存为空")], True)
                await delay_recall(bot, msg, 10)
                return
            view_msg = [Text("当前缓存内容：\n")]
            for i, msg_item in enumerate(current_cache["messages"], 1):
                if msg_item["type"] == "text":
                    content_preview = msg_item['content']
                    if len(content_preview) > 50:
                        content_preview = content_preview[:50] + '...'
                    view_msg.append(Text(f"{i}. 文本: {content_preview}\n"))
                elif msg_item["type"] == "image":
                    view_msg.append(Text(f"{i}. 图片\n"))
                    view_msg.append(Image(file=msg_item["content"]))
            msg = await bot.send(event, view_msg, True)
            await delay_recall(bot, msg, 30)
            return

        if current_cache["active"]:
            try:
                img_url = await get_img(event, bot)
                if img_url:
                    current_cache["messages"].append({"type": "image", "content": img_url})
                    msg = await bot.send(event, [Text("图片已添加到缓存")], True)
                    await delay_recall(bot, msg, 10)
            except Exception as e:
                error_msg = await bot.send(event, [Text(f"添加图片时出错: {str(e)}")], True)
                await delay_recall(bot, error_msg, 15)
                print(f"添加图片错误详情: {traceback.format_exc()}")
            
            if pure_text and not pure_text.startswith("#"):
                current_cache["messages"].append({"type": "text", "content": pure_text})
                msg = await bot.send(event, [Text("文本已添加到缓存")], True)
                await delay_recall(bot, msg, 10)
    
    return nano_message_handler
    
