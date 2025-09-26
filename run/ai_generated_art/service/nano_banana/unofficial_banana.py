import base64
import os
import random
import traceback
from pathlib import Path
from typing import Dict, Any

import httpx

from run.ai_generated_art.service.nano_banana.apikey_iterator import RoundRobinSelector

api_key_selector = None
async def call_openrouter_api(contents, config) -> Dict[str, Any]:
    model_selected=config.ai_generated_art.config["ai绘画"]["nano_banana_config"]["model"]
    url = "https://openrouter.ai/api/v1/chat/completions"
    proxy = config.common_config.basic_config["proxy"]["http_proxy"] if config.common_config.basic_config["proxy"][
        "http_proxy"] else None
    proxies = {"http://": proxy, "https://": proxy} if proxy else None

    user_content = []
    for part in contents:
        if "text" in part:
            user_content.append({"type": "text", "text": part["text"]})
        elif "inlineData" in part:
            mime_type = part["inlineData"].get("mime_type", "image/png")
            b64_data = part["inlineData"]["data"]
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}
            })

    messages = [
        {"role": "system",
         "content": "You are a capable drawing assistant. For every conversation with the user, you must output an image. It is crucial to ensure that you generate an image and not return only text."},
        {"role": "user", "content": user_content}
    ]
    payload = {"model": model_selected, "messages": messages,"temperature": config.ai_generated_art.config["ai绘画"]["nano_banana_config"]["temperature"]}

    try:
        # 修正了您之前指出的笔误
        global api_key_selector
        api_keys = config.ai_generated_art.config["ai绘画"]["nano_banana_key"]

        if api_key_selector is None:
            api_key_selector = RoundRobinSelector(api_keys)

        api_key = api_key_selector.get_next()
    except KeyError:
        error_msg = "未在配置文件中找到 nano_banana_key。请在 config.ai_generated_art.config['ai绘画']['nano_banana_key'] 中配置您的OpenRouter Key。"
        print(error_msg)
        return {"success": False, "error": "配置错误", "details": error_msg}

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=None, proxies=proxies) as client:
            response = await client.post(url, json=payload, headers=headers)

        response.raise_for_status()
        response_data = response.json()

        if not response_data.get("choices"):
            raise ValueError("API响应中未包含 'choices'")

        choice = response_data["choices"][0]
        message = choice.get("message", {})

        base64_data = None
        text_responses = []

        # *** FINAL FIX: Parse message.images based on the user-provided log file ***
        images_list = message.get("images")
        if images_list and isinstance(images_list, list) and len(images_list) > 0:
            image_url_obj = images_list[0].get("image_url", {})
            url_string = image_url_obj.get("url")

            if url_string and "base64," in url_string:
                # Split the string at "base64," and take the second part
                parts = url_string.split("base64,", 1)
                if len(parts) > 1:
                    base64_data = parts[1]
                    print("成功从 message.images 中提取到图片数据。")

        # Fallback for text-only responses
        content = message.get("content")
        if isinstance(content, str) and content and content != '`':
            text_responses.append(content)

        full_text_response = " ".join(text_responses).strip()

        if not base64_data and not full_text_response:

            try:
                print(response.status_code)
                print(response.json())
            except:
                pass
            raise ValueError("API响应既未包含有效的图像数据，也未包含有效的文本。")

        save_path = None
        if base64_data:
            save_path = f"data/pictures/cache/{random.randint(1000, 9999)}.png"
            Path(os.path.dirname(save_path)).mkdir(parents=True, exist_ok=True)
            try:
                with open(save_path, "wb") as f:
                    f.write(base64.b64decode(base64_data))
            except (base64.binascii.Error, TypeError) as b64_error:
                print(f"Base64解码失败: {b64_error}")
                save_path = None

        return {"success": True, "result_path": save_path, "text": full_text_response,"has_image": bool(base64_data)}

    except httpx.HTTPStatusError as e:
        error_details = f"HTTP错误 (状态码: {e.response.status_code}): {e.response.text}"
        print(error_details)
        return {"success": False, "error": "API请求失败", "details": error_details}
    except Exception as e:
        error_details = f"未知错误: {e}\n{traceback.format_exc()}"
        print(error_details)
        return {"success": False, "error": "处理过程中发生未知错误", "details": error_details}
