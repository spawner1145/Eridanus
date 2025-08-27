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
from framework_common.utils.utils import get_img, delay_recall

# 普通用户每日最大调用次数
MAX_USES_PER_DAY = 20
# 不受限制的用户ID列表 (请将这里的数字替换为实际的QQ号)
UNLIMITED_USERS = [1462079129, 2508473558]
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

async def call_gemini_api(contents, config) -> Dict[str, Any]:
    url = f"{config.ai_llm.config['llm']['gemini']['base_url']}/v1beta/models/gemini-2.5-flash-image-preview:generateContent"
    proxy = config.common_config.basic_config["proxy"]["http_proxy"] if config.common_config.basic_config["proxy"]["http_proxy"] else None
    proxies={"http://": proxy, "https://": proxy} if proxy else None
    payload = {"contents": [{"parts": contents}]}
    headers = {
        "x-goog-api-key": config.ai_generated_art.config["ai绘画"]["nano_banana的key"],
        "Content-Type": "application/json"
    }
    try:
        async with httpx.AsyncClient(timeout=None, proxies=proxies) as client:
            response = await client.post(url, json=payload, headers=headers)
        print("API响应状态码:", response.status_code)
        response.raise_for_status()
        response_data = response.json()
        candidates = response_data.get("candidates")
        if not candidates:
            raise ValueError("API响应中未包含 'candidates'。")
        content = candidates[0].get("content", {})
        parts = content.get("parts")
        if not parts:
            raise ValueError("API响应的候选结果中未包含 'parts'。")
        base64_data = None
        text_responses = []
        for part in parts:
            if "inlineData" in part and part["inlineData"].get("data"):
                base64_data = part["inlineData"]["data"]
            if "text" in part:
                text_responses.append(part["text"])
        full_text_response = " ".join(text_responses).strip()
        if not base64_data and not full_text_response:
            raise ValueError("API响应既未包含图像数据，也未包含有效的文本。")
        save_path = None
        if base64_data:
            save_path = f"data/pictures/cache/{random.randint(1000, 9999)}.png"
            Path(os.path.dirname(save_path)).mkdir(parents=True, exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(base64.b64decode(base64_data))
        return {
            "success": True,
            "result_path": save_path,
            "text": full_text_response
        }
    except httpx.HTTPStatusError as e:
        error_details = f"HTTP错误 (状态码: {e.response.status_code}): {e.response.text}"
        print(error_details)
        return {"success": False, "error": "API请求失败", "details": error_details}
    except httpx.RequestError as e:
        error_details = f"请求错误: {e}"
        print(error_details)
        return {"success": False, "error": "网络连接或请求配置错误", "details": error_details}
    except (ValueError, KeyError, IndexError) as e:
        error_details = f"解析API响应失败: {e}\n{traceback.format_exc()}"
        print(error_details)
        return {"success": False, "error": str(e), "details": error_details}
    except Exception as e:
        error_details = f"未知错误: {e}\n{traceback.format_exc()}"
        print(error_details)
        return {"success": False, "error": "处理过程中发生未知错误", "details": error_details}


def init_user_cache(user_id: int):
    if user_id not in user_cache:
        user_cache[user_id] = {
            "active": False,
            "messages": []
        }

def main(bot, config):
    @bot.on(GroupMessageEvent)
    async def nano_message_handler(event: GroupMessageEvent):
        user_id = event.sender.user_id
        init_user_cache(user_id)
        current_cache = user_cache[user_id]
        pure_text = str(event.pure_text).strip()
        
        if pure_text == "#nano":
            if current_cache["active"]:
                msg = await bot.send(event, [Text("已处于监听状态，可直接发送消息或图片")], True)
                await delay_recall(bot, msg, 10)
            else:
                if user_id not in UNLIMITED_USERS:
                    usage_data = load_or_reset_usage_data()
                    user_uses = usage_data.get("usage_data", {}).get(str(user_id), 0)
                    if user_uses >= MAX_USES_PER_DAY:
                        await bot.send(event, [Text(f"你今天已经达到 {MAX_USES_PER_DAY} 次调用上限，请明天再来吧！")], True)
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
            
            api_contents = []
            for msg_item in messages_to_process:
                if msg_item["type"] == "text":
                    api_contents.append({"text": msg_item["content"]})
                
                elif msg_item["type"] == "image":
                    try:
                        async with httpx.AsyncClient() as client:
                            response = await client.get(msg_item["content"], timeout=30.0)
                            response.raise_for_status()
                        image_data = response.content

                        with BytesIO(image_data) as img_buffer:
                            with PILImage.open(img_buffer) as img:
                                processed_img = img
                                if getattr(img, 'is_animated', False):
                                    img.seek(0)
                                    processed_img = img.convert('RGB')
                                
                                with BytesIO() as output_buffer:
                                    processed_img.save(output_buffer, format="PNG")
                                    processed_image_data = output_buffer.getvalue()
                        
                        b64_data = base64.b64encode(processed_image_data).decode('utf-8')
                        
                        api_contents.append({
                            "inlineData": {
                                "mime_type": "image/png",
                                "data": b64_data
                            }
                        })
                    except Exception as e:
                        error_msg = await bot.send(event, [Text(f"处理图片时出错: {str(e)}")], True)
                        await delay_recall(bot, error_msg, 15)
                        print(f"图片处理错误详情: {traceback.format_exc()}")
            
            if not api_contents:
                msg = await bot.send(event, [Text("没有有效的内容可提交，请重新输入")], True)
                await delay_recall(bot, msg, 10)
                return
            
            processing_msg = await bot.send(event, [Text("已提交nano banana请求，正在处理...")], True)
            
            api_result = await call_gemini_api(api_contents, config)
            
            await bot.recall(processing_msg)

            if api_result.get("success"):
                remaining_uses_text = ""
                if user_id not in UNLIMITED_USERS:
                    usage_data = load_or_reset_usage_data()
                    current_uses = usage_data.get("usage_data", {}).get(str(user_id), 0)
                    new_uses = current_uses + 1
                    usage_data["usage_data"][str(user_id)] = new_uses
                    save_usage_data(usage_data)
                    remaining = MAX_USES_PER_DAY - new_uses
                    if remaining > 0:
                        remaining_uses_text = f"调用成功！你今天还剩下 {remaining} 次调用机会"
                    else:
                        remaining_uses_text = "今天没得🦌了"
                
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
