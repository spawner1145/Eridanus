"""
通用任务 Client - 用于用户画像总结等辅助任务
支持 openai 和 gemini 两种类型
"""
import json
import random
from typing import Optional, List, Dict, Any

from developTools.utils.logger import get_logger
from framework_common.utils.GeminiKeyManager import GeminiKeyManager
from run.ai_llm.clients.gemini_client import GeminiAPI
from run.ai_llm.clients.openai_client import OpenAIAPI

logger = get_logger("utility_client")


async def utility_request(
    config,
    messages: List[Dict[str, Any]],
    system_instruction: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Optional[str]:
    """
    通用任务请求函数
    
    Args:
        config: 配置对象
        messages: 消息列表（Gemini 格式或 OpenAI 格式，会自动转换）
        system_instruction: 系统指令
        user_id: 用户ID（用于获取历史记录等）
    
    Returns:
        响应文本或 None
    """
    try:
        utility_config = config.ai_llm.config["llm"].get("utility_client", {})
        client_type = utility_config.get("type", "gemini").strip().lower()
        
        proxy = config.common_config.basic_config["proxy"]["http_proxy"] if config.ai_llm.config["llm"]["enable_proxy"] else None
        proxies = {"http://": proxy, "https://": proxy} if proxy else None
        
        if client_type == "openai":
            return await _openai_request(config, utility_config, messages, system_instruction, proxies)
        else:
            return await _gemini_request(config, utility_config, messages, system_instruction, proxies)
            
    except Exception as e:
        logger.error(f"utility_request 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def _gemini_request(
    config,
    utility_config: dict,
    messages: List[Dict[str, Any]],
    system_instruction: Optional[str],
    proxies: Optional[dict],
) -> Optional[str]:
    """Gemini 请求"""
    # API Key
    api_key = utility_config.get("api_key", "").strip()
    if not api_key:
        api_key = await GeminiKeyManager.get_gemini_apikey()
    
    # Base URL
    base_url = utility_config.get("base_url", "").strip()
    if not base_url:
        base_url = config.ai_llm.config["llm"]["gemini"]["base_url"]
    
    # 模型选择逻辑：指定模型 + fallback_models 列表
    specified_model = utility_config.get("model", "").strip()
    gemini_fallback_models = config.ai_llm.config["llm"]["gemini"].get("fallback_models", [])
    if specified_model:
        fallback_models = [specified_model] + [m for m in gemini_fallback_models if m != specified_model]
    else:
        fallback_models = gemini_fallback_models
    
    api = GeminiAPI(
        apikey=api_key,
        baseurl=base_url,
        fallback_models=fallback_models,
        proxies=proxies
    )
    
    # 转换消息格式为 Gemini 格式，并将 system_instruction 合并到正文中
    gemini_messages = _convert_to_gemini_format(messages, system_instruction)
    
    response_text = ""
    async for part in api.chat(
        gemini_messages,
        stream=True,
        system_instruction=None,  # 不使用 system prompt，已合并到正文
        temperature=config.ai_llm.config["llm"]["gemini"]["temperature"],
        max_output_tokens=config.ai_llm.config["llm"]["gemini"]["maxOutputTokens"],
    ):
        if isinstance(part, str):
            response_text += part
    
    return response_text.strip() if response_text else None


async def _openai_request(
    config,
    utility_config: dict,
    messages: List[Dict[str, Any]],
    system_instruction: Optional[str],
    proxies: Optional[dict],
) -> Optional[str]:
    """OpenAI 请求"""
    # API Key
    api_key = utility_config.get("api_key", "").strip()
    if not api_key:
        api_keys = config.ai_llm.config["llm"]["openai"].get("api_keys", [])
        if api_keys:
            api_key = random.choice(api_keys)
        else:
            logger.error("utility_client: 未配置 OpenAI API Key")
            return None
    
    # Base URL
    base_url = utility_config.get("base_url", "").strip()
    if not base_url:
        base_url = config.ai_llm.config["llm"]["openai"].get("quest_url") or config.ai_llm.config["llm"]["openai"].get("base_url")
    
    # 模型
    model = utility_config.get("model", "").strip()
    if not model:
        model = config.ai_llm.config["llm"]["openai"]["model"]
    
    api = OpenAIAPI(
        apikey=api_key,
        baseurl=base_url,
        model=model,
        proxies=proxies
    )
    
    # 转换消息格式为 OpenAI 格式，并将 system_instruction 合并到正文中
    openai_messages = _convert_to_openai_format(messages, system_instruction)
    
    response_text = ""
    async for part in api.chat(
        openai_messages,
        stream=True,
        temperature=config.ai_llm.config["llm"]["openai"]["temperature"],
        max_output_tokens=config.ai_llm.config["llm"]["openai"]["max_tokens"],
    ):
        if isinstance(part, str):
            response_text += part
    
    return response_text.strip() if response_text else None


def _convert_to_gemini_format(messages: List[Dict[str, Any]], system_instruction: Optional[str] = None) -> List[Dict[str, Any]]:
    """将消息转换为 Gemini 格式，并将 system_instruction 合并到正文中"""
    result = []
    
    # 如果有 system_instruction，将其作为第一条消息的前缀
    prefix_text = f"[任务要求] {system_instruction}\n\n" if system_instruction else ""
    first_user_message_processed = False
    
    for msg in messages:
        if "parts" in msg:
            # 已经是 Gemini 格式
            if not first_user_message_processed and msg.get("role") == "user" and prefix_text:
                # 将 system_instruction 合并到第一条用户消息
                new_parts = []
                prefix_added = False
                for part in msg["parts"]:
                    if isinstance(part, dict) and "text" in part and not prefix_added:
                        new_parts.append({"text": prefix_text + part["text"]})
                        prefix_added = True
                    elif isinstance(part, dict) and "inlineData" in part:
                        # 保留图片数据
                        new_parts.append(part)
                    else:
                        new_parts.append(part)
                if not prefix_added and prefix_text:
                    # 如果没有文本部分，在开头添加前缀
                    new_parts.insert(0, {"text": prefix_text})
                result.append({"role": msg["role"], "parts": new_parts})
                first_user_message_processed = True
                prefix_text = ""
            else:
                result.append(msg)
        elif "content" in msg:
            # OpenAI 格式转换
            role = msg.get("role", "user")
            if role == "assistant":
                role = "model"
            elif role == "system":
                role = "user"  # Gemini 没有 system role，转为 user
            
            content = msg["content"]
            if isinstance(content, str):
                text = prefix_text + content if not first_user_message_processed and role == "user" else content
                parts = [{"text": text}]
                if role == "user":
                    first_user_message_processed = True
                    prefix_text = ""
            elif isinstance(content, list):
                parts = []
                prefix_added = False
                for i, item in enumerate(content):
                    if isinstance(item, dict) and "text" in item:
                        text = item["text"]
                        if not first_user_message_processed and role == "user" and not prefix_added:
                            text = prefix_text + text
                            prefix_added = True
                            first_user_message_processed = True
                        parts.append({"text": text})
                    elif isinstance(item, dict) and "type" in item and item["type"] == "text":
                        text = item.get("text", "")
                        if not first_user_message_processed and role == "user" and not prefix_added:
                            text = prefix_text + text
                            prefix_added = True
                            first_user_message_processed = True
                        parts.append({"text": text})
                    elif isinstance(item, dict) and "type" in item and item["type"] == "image_url":
                        # 将 OpenAI 图片格式转换为 Gemini 格式
                        image_url = item.get("image_url", {})
                        url = image_url.get("url", "") if isinstance(image_url, dict) else image_url
                        if url.startswith("data:"):
                            # 解析 base64 数据
                            import re
                            match = re.match(r'data:(image/\w+);base64,(.+)', url)
                            if match:
                                mime_type = match.group(1)
                                data = match.group(2)
                                parts.append({"inlineData": {"mimeType": mime_type, "data": data}})
                        else:
                            # URL 格式，暂不支持直接转换
                            parts.append({"text": f"[图片: {url}]"})
                    elif isinstance(item, dict) and "inlineData" in item:
                        # 已经是 Gemini 图片格式
                        parts.append(item)
                    else:
                        parts.append({"text": str(item)})
                if not prefix_added and prefix_text and role == "user":
                    parts.insert(0, {"text": prefix_text})
                    first_user_message_processed = True
                prefix_text = ""
            else:
                text = prefix_text + str(content) if not first_user_message_processed and role == "user" else str(content)
                parts = [{"text": text}]
                if role == "user":
                    first_user_message_processed = True
                    prefix_text = ""
            
            result.append({"role": role, "parts": parts})
        elif "text" in msg:
            # 简单的 text 格式
            text = prefix_text + msg["text"] if not first_user_message_processed else msg["text"]
            result.append({"role": "user", "parts": [{"text": text}]})
            first_user_message_processed = True
            prefix_text = ""
    
    return result


def _convert_to_openai_format(messages: List[Dict[str, Any]], system_instruction: Optional[str] = None) -> List[Dict[str, Any]]:
    """将消息转换为 OpenAI 格式，并将 system_instruction 合并到正文中（不使用 system role）"""
    result = []
    
    # 如果有 system_instruction，将其作为第一条消息的前缀
    prefix_text = f"[任务要求] {system_instruction}\n\n" if system_instruction else ""
    first_user_message_processed = False
    
    for msg in messages:
        if "content" in msg:
            # 已经是 OpenAI 格式
            role = msg.get("role", "user")
            if role == "system":
                role = "user"  # 不使用 system role
            
            if not first_user_message_processed and role == "user" and prefix_text:
                content = msg["content"]
                if isinstance(content, str):
                    new_content = [{"type": "text", "text": prefix_text + content}]
                elif isinstance(content, list):
                    new_content = []
                    prefix_added = False
                    for i, item in enumerate(content):
                        if isinstance(item, dict) and item.get("type") == "text" and not prefix_added:
                            new_content.append({"type": "text", "text": prefix_text + item.get("text", "")})
                            prefix_added = True
                        elif isinstance(item, dict) and item.get("type") == "image_url":
                            new_content.append(item)
                        else:
                            new_content.append(item)
                    if not prefix_added:
                        new_content.insert(0, {"type": "text", "text": prefix_text})
                else:
                    new_content = [{"type": "text", "text": prefix_text + str(content)}]
                result.append({"role": role, "content": new_content})
                first_user_message_processed = True
                prefix_text = ""
            else:
                result.append({"role": role, "content": msg["content"]})
        elif "parts" in msg:
            # Gemini 格式转换
            role = msg.get("role", "user")
            if role == "model":
                role = "assistant"
            
            parts = msg["parts"]
            content = []
            prefix_added = False
            for i, part in enumerate(parts):
                if isinstance(part, dict) and "text" in part:
                    text = part["text"]
                    if not first_user_message_processed and role == "user" and not prefix_added:
                        text = prefix_text + text
                        prefix_added = True
                        first_user_message_processed = True
                    content.append({"type": "text", "text": text})
                elif isinstance(part, dict) and "inlineData" in part:
                    # 将 Gemini 图片格式转换为 OpenAI 格式
                    inline_data = part["inlineData"]
                    mime_type = inline_data.get("mimeType", "image/jpeg")
                    data = inline_data.get("data", "")
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{data}", "detail": "auto"}
                    })
                else:
                    content.append({"type": "text", "text": str(part)})
            
            if not prefix_added and prefix_text and role == "user":
                content.insert(0, {"type": "text", "text": prefix_text})
                first_user_message_processed = True
            prefix_text = ""
            
            result.append({"role": role, "content": content})
        elif "text" in msg:
            # 简单的 text 格式
            text = prefix_text + msg["text"] if not first_user_message_processed else msg["text"]
            result.append({
                "role": "user",
                "content": [{"type": "text", "text": text}]
            })
            first_user_message_processed = True
            prefix_text = ""
    
    return result
