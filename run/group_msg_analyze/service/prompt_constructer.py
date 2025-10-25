import asyncio
import base64
import io
import os
import re
import traceback
import uuid

import httpx
from PIL import Image

from developTools.utils.logger import get_logger

logger=get_logger(__name__)

BASE64_PATTERN = re.compile(r"^data:([a-zA-Z0-9]+/[a-zA-Z0-9-.+]+);base64,([A-Za-z0-9+/=]+)$")
async def gemini_prompt_construct_vGroup(precessed_message, bot=None, func_result=False, event=None):
    """
    构建Gemini API的prompt元素
    支持两种消息格式:
    1. 原始格式: [{"text": ...}, {"image": ...}, ...]
    2. 新格式: {"data": {"messages": [{"sender": {...}, "content": [...]}]}}
    """
    prompt_elements = []

    # 检测消息格式
    if isinstance(precessed_message, dict) and "data" in precessed_message and "messages" in precessed_message["data"]:
        # 新格式: 处理消息列表
        messages = precessed_message["data"]["messages"]

        for msg in messages:
            sender_info = msg.get("sender", {})
            nickname = sender_info.get("nickname", "未知用户")
            user_id = sender_info.get("user_id", "")

            # 添加发送者标识
            prompt_elements.append({"text": f"[{nickname} (ID: {user_id})]:"})

            # 处理消息内容
            content_list = msg.get("content", [])
            for item in content_list:
                item_type = item.get("type")
                item_data = item.get("data", {})

                if item_type == "text":
                    text_content = item_data.get("text", "")
                    if text_content.strip():  # 忽略空白文本
                        prompt_elements.append({"text": text_content})

                elif item_type == "image":
                    await process_image(item_data, prompt_elements, bot)

                elif item_type == "record":
                    await process_audio(item_data, prompt_elements, bot)

                elif item_type == "video":
                    await process_video(item_data, prompt_elements, bot)

                else:
                    # 未知类型，转为文本
                    prompt_elements.append({"text": f"[未知类型消息: {item_type}]"})

    else:
        # 原始格式: 直接处理消息元素列表
        for i in precessed_message:
            if "text" in i:
                prompt_elements.append({"text": i["text"]})

            elif "image" in i or "mface" in i:
                image_data = i.get("mface") or i.get("image")
                await process_image(image_data, prompt_elements, bot)

            elif "record" in i and bot is not None:
                await process_audio(i["record"], prompt_elements, bot)

            elif "video" in i and bot is not None:
                await process_video(i.get("video"), prompt_elements, bot)

            elif "reply" in i and event is not None and bot is not None:
                try:
                    event_obj = await bot.get_msg(int(event.get("reply")[0]["id"]))
                    message = await gemini_prompt_elements_construct(event_obj.processed_message)
                    prompt_elements.extend(message["parts"])
                except Exception as e:
                    traceback.print_exc()
                    logger.warning(f"引用消息解析失败:{e}")
                    continue

            else:
                prompt_elements.append({"text": str(i)})

    if func_result:
        return {"role": "model", "parts": prompt_elements}
    return {"role": "user", "parts": prompt_elements}


async def process_image(image_data, prompt_elements, bot):
    """处理图片消息"""
    try:
        # 获取URL
        url = image_data.get("url") or image_data.get("file", "")

        # 检查是否为base64格式
        base64_match = BASE64_PATTERN.match(url)
        if base64_match:
            img_base64 = base64_match.group(2)
            prompt_elements.append({"inline_data": {"mime_type": "image/jpeg", "data": img_base64}})
            return

        prompt_elements.append({"text": f"system提示: 当前图片的url为{url}"})

        # 下载并转换图片
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.get(url)
            image = None
            img_byte_arr = None

            try:
                image = Image.open(io.BytesIO(res.content))
                image = image.convert("RGB")
            except Exception as e:
                logger.warning(f"下载图片失败:{url} 原因:{e}")
                return

            quality = 85
            while True:
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='JPEG', quality=quality)
                size_kb = img_byte_arr.tell() / 1024
                if size_kb <= 400 or quality <= 10:
                    break
                quality -= 5
                img_byte_arr.close()

            img_base64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            prompt_elements.append({"inline_data": {"mime_type": "image/jpeg", "data": img_base64}})

    except Exception as e:
        traceback.print_exc()
        prompt_elements.append({"text": f"系统提示：下载图片失败"})

    finally:
        if image is not None:
            image.close()
        if img_byte_arr is not None:
            img_byte_arr.close()
        if 'res' in locals():
            del res


async def process_audio(audio_data, prompt_elements, bot):
    """处理音频消息"""
    origin_voice_url = audio_data.get("file", "")

    base64_match = BASE64_PATTERN.match(origin_voice_url)
    if base64_match:
        img_base64 = base64_match.group(2)
        prompt_elements.append({"inline_data": {"mime_type": "audio/mp3", "data": img_base64}})
        return

    mp3_data = None
    try:
        r = await bot.get_record(origin_voice_url)
        logger.info(f"下载语音成功:{r}")
        mp3_filepath = r["data"]["file"]

        with open(mp3_filepath, "rb") as mp3_file:
            mp3_data = mp3_file.read()
            base64_encoded_data = base64.b64encode(mp3_data)
            base64_message = base64_encoded_data.decode('utf-8')
            prompt_elements.append({"inline_data": {"mime_type": "audio/mp3", "data": base64_message}})

    except Exception as e:
        logger.warning(f"下载语音失败:{origin_voice_url} 原因:{e}")

    finally:
        if mp3_data is not None:
            del mp3_data


async def process_video(video_data, prompt_elements, bot):
    """处理视频消息"""
    mp4_data = None
    base64_encoded_data = None

    try:
        video_url = video_data.get("url") or video_data.get("file", "")

        base64_match = BASE64_PATTERN.match(video_url)
        if base64_match:
            img_base64 = base64_match.group(2)
            prompt_elements.append({"inline_data": {"mime_type": "video/mp4", "data": img_base64}})
            return

        video = await bot.get_video(video_url, f"data/pictures/cache/{uuid.uuid4()}.mp4")

        # 下载视频文件大小限制(15MB)
        file_size = os.path.getsize(video)
        if file_size > 15 * 1024 * 1024:
            raise Exception(f"视频文件大小超出限制: {file_size / (1024 * 1024):.2f}MB，最大允许 15MB")

        with open(video, "rb") as mp4_file:
            mp4_data = mp4_file.read()
            base64_encoded_data = base64.b64encode(mp4_data)
            base64_message = base64_encoded_data.decode('utf-8')
            prompt_elements.append({"inline_data": {"mime_type": "video/mp4", "data": base64_message}})

    except Exception as e:
        logger.warning(f"下载视频失败:{video_url} 原因:{e}")
        prompt_elements.append({"text": str(video_data)})

    finally:
        if mp4_data is not None:
            del mp4_data
        if base64_encoded_data is not None:
            del base64_encoded_data
