import random
import re
from typing import Optional, List, Dict, Any

from developTools.utils.logger import get_logger
from framework_common.utils.GeminiKeyManager import GeminiKeyManager
from run.ai_llm.clients.gemini_client import GeminiAPI
from run.ai_llm.clients.openai_client import OpenAIAPI

logger = get_logger("heartflow_client")


async def heartflow_request(
    config,
    messages: List[Dict[str, Any]],
    system_instruction: Optional[str] = None,
    group_context: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    try:
        heartflow_config = config.ai_llm.config.get("heartflow", {})
        client_config = heartflow_config.get("client", {})
        client_type = client_config.get("type", "gemini").strip().lower()
        
        proxy = config.common_config.basic_config["proxy"]["http_proxy"] if config.ai_llm.config["llm"]["enable_proxy"] else None
        proxies = {"http://": proxy, "https://": proxy} if proxy else None
        
        if client_type == "openai":
            return await _openai_request(config, client_config, messages, system_instruction, group_context, proxies)
        else:
            return await _gemini_request(config, client_config, messages, system_instruction, group_context, proxies)
            
    except Exception as e:
        logger.error(f"heartflow_request 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def _gemini_request(
    config,
    client_config: dict,
    messages: List[Dict[str, Any]],
    system_instruction: Optional[str],
    group_context: Optional[List[Dict[str, Any]]],
    proxies: Optional[dict],
) -> Optional[str]:
    api_key = client_config.get("api_key", "").strip()
    if not api_key:
        api_key = await GeminiKeyManager.get_gemini_apikey()

    base_url = client_config.get("base_url", "").strip()
    if not base_url:
        base_url = config.ai_llm.config["llm"]["gemini"]["base_url"]
    specified_model = client_config.get("model", "").strip()
    gemini_fallback_models = config.ai_llm.config["llm"]["gemini"].get("fallback_models", [])
    if specified_model:
        fallback_models = [specified_model] + [m for m in gemini_fallback_models if m != specified_model]
    else:
        fallback_models = gemini_fallback_models

    temperature = client_config.get("temperature")
    if temperature is None or temperature == "":
        temperature = config.ai_llm.config["llm"]["gemini"]["temperature"]

    max_tokens = client_config.get("max_tokens")
    if max_tokens is None or max_tokens == "":
        max_tokens = config.ai_llm.config["llm"]["gemini"]["maxOutputTokens"]
    
    api = GeminiAPI(
        apikey=api_key,
        baseurl=base_url,
        fallback_models=fallback_models,
        proxies=proxies
    )
    full_messages = _build_gemini_messages(messages, system_instruction, group_context)
    
    response_text = ""
    async for part in api.chat(
        full_messages,
        stream=True,
        system_instruction=None,
        temperature=temperature,
        max_output_tokens=max_tokens,
    ):
        if isinstance(part, str):
            response_text += part
    
    return response_text.strip() if response_text else None


async def _openai_request(
    config,
    client_config: dict,
    messages: List[Dict[str, Any]],
    system_instruction: Optional[str],
    group_context: Optional[List[Dict[str, Any]]],
    proxies: Optional[dict],
) -> Optional[str]:
    api_key = client_config.get("api_key", "").strip()
    if not api_key:
        api_keys = config.ai_llm.config["llm"]["openai"].get("api_keys", [])
        if api_keys:
            api_key = random.choice(api_keys)
        else:
            logger.error("heartflow_client: 未配置 OpenAI API Key")
            return None

    base_url = client_config.get("base_url", "").strip()
    if not base_url:
        base_url = config.ai_llm.config["llm"]["openai"].get("quest_url") or config.ai_llm.config["llm"]["openai"].get("base_url")
    model = client_config.get("model", "").strip()
    if not model:
        model = config.ai_llm.config["llm"]["openai"]["model"]
    temperature = client_config.get("temperature")
    if temperature is None or temperature == "":
        temperature = config.ai_llm.config["llm"]["openai"]["temperature"]
    max_tokens = client_config.get("max_tokens")
    if max_tokens is None or max_tokens == "":
        max_tokens = config.ai_llm.config["llm"]["openai"]["max_tokens"]
    
    api = OpenAIAPI(
        apikey=api_key,
        baseurl=base_url,
        model=model,
        proxies=proxies
    )
    full_messages = _build_openai_messages(messages, system_instruction, group_context)
    
    response_text = ""
    async for part in api.chat(
        full_messages,
        stream=True,
        temperature=temperature,
        max_output_tokens=max_tokens,
    ):
        if isinstance(part, str):
            response_text += part
    
    return response_text.strip() if response_text else None


def _build_gemini_messages(
    messages: List[Dict[str, Any]],
    system_instruction: Optional[str],
    group_context: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    result = []
    if group_context:
        result.extend(group_context)
    if system_instruction:
        result.append({
            "role": "user",
            "parts": [{"text": f"[系统指令] {system_instruction}"}]
        })
        result.append({
            "role": "model",
            "parts": [{"text": "好的，我已了解指令。"}]
        })
    
    user_parts = []
    for msg in messages:
        if "text" in msg:
            user_parts.append({"text": msg["text"]})
        elif "inlineData" in msg:
            user_parts.append({"inlineData": msg["inlineData"]})
        elif "image_url" in msg:
            # 转换 OpenAI 格式图片为 Gemini 格式
            url = msg["image_url"].get("url", "")
            if url.startswith("data:"):
                # 解析 data URI
                match = re.match(r"data:([^;]+);base64,(.+)", url)
                if match:
                    mime_type = match.group(1)
                    base64_data = match.group(2)
                    user_parts.append({"inlineData": {"mimeType": mime_type, "data": base64_data}})
        elif "parts" in msg:
            result.append(msg)
        elif "content" in msg:
            # OpenAI 格式转 Gemini 格式，包含图片支持
            content = msg["content"]
            parts = []
            if isinstance(content, str):
                parts.append({"text": content})
            elif isinstance(content, list):
                for c in content:
                    if isinstance(c, dict):
                        if c.get("type") == "text":
                            parts.append({"text": c.get("text", "")})
                        elif c.get("type") == "image_url":
                            url = c.get("image_url", {}).get("url", "")
                            if url.startswith("data:"):
                                match = re.match(r"data:([^;]+);base64,(.+)", url)
                                if match:
                                    mime_type = match.group(1)
                                    base64_data = match.group(2)
                                    parts.append({"inlineData": {"mimeType": mime_type, "data": base64_data}})
            if parts:
                result.append({
                    "role": "user" if msg.get("role") in ["user", "system"] else "model",
                    "parts": parts
                })
    
    if user_parts:
        result.append({
            "role": "user",
            "parts": user_parts
        })
    
    return result


def _build_openai_messages(
    messages: List[Dict[str, Any]],
    system_instruction: Optional[str],
    group_context: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    result = []
    if system_instruction:
        result.append({
            "role": "system",
            "content": [{"type": "text", "text": system_instruction}]
        })
    
    if group_context:
        for ctx in group_context:
            if "parts" in ctx:
                # Gemini 格式转 OpenAI 格式，包含图片支持
                content_parts = []
                for p in ctx["parts"]:
                    if isinstance(p, dict):
                        if "text" in p:
                            content_parts.append({"type": "text", "text": p["text"]})
                        elif "inlineData" in p:
                            # 转换 Gemini 的 inlineData 为 OpenAI 的 image_url 格式
                            inline_data = p["inlineData"]
                            mime_type = inline_data.get("mimeType", "image/jpeg")
                            base64_data = inline_data.get("data", "")
                            content_parts.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_data}",
                                    "detail": "auto"
                                }
                            })
                if content_parts:
                    role = "assistant" if ctx.get("role") == "model" else "user"
                    result.append({
                        "role": role,
                        "content": content_parts
                    })
            elif "content" in ctx:
                result.append(ctx)

    user_content = []
    for msg in messages:
        if "text" in msg:
            user_content.append({"type": "text", "text": msg["text"]})
        elif "input_image" in msg:
            user_content.append(msg)
        elif "image_url" in msg:
            # 直接支持 OpenAI 格式的图片
            user_content.append({"type": "image_url", "image_url": msg["image_url"]})
        elif "inlineData" in msg:
            # 转换 Gemini 格式图片为 OpenAI 格式
            inline_data = msg["inlineData"]
            mime_type = inline_data.get("mimeType", "image/jpeg")
            base64_data = inline_data.get("data", "")
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{base64_data}",
                    "detail": "auto"
                }
            })
        elif "content" in msg:
            result.append(msg)
        elif "parts" in msg:
            # Gemini 格式的完整消息
            content_parts = []
            for p in msg["parts"]:
                if isinstance(p, dict):
                    if "text" in p:
                        content_parts.append({"type": "text", "text": p["text"]})
                    elif "inlineData" in p:
                        inline_data = p["inlineData"]
                        mime_type = inline_data.get("mimeType", "image/jpeg")
                        base64_data = inline_data.get("data", "")
                        content_parts.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_data}",
                                "detail": "auto"
                            }
                        })
            if content_parts:
                role = "assistant" if msg.get("role") == "model" else "user"
                result.append({
                    "role": role,
                    "content": content_parts
                })
    
    if user_content:
        result.append({
            "role": "user",
            "content": user_content
        })
    
    return result
