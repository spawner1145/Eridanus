import random
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
    
    for msg in messages:
        if "text" in msg:
            result.append({
                "role": "user",
                "parts": [{"text": msg["text"]}]
            })
        elif "parts" in msg:
            result.append(msg)
        elif "content" in msg:
            content = msg["content"]
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = " ".join([c.get("text", "") for c in content if c.get("type") == "text"])
            else:
                text = str(content)
            result.append({
                "role": "user" if msg.get("role") in ["user", "system"] else "model",
                "parts": [{"text": text}]
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
                text = " ".join([p.get("text", "") for p in ctx["parts"] if isinstance(p, dict) and "text" in p])
                role = "assistant" if ctx.get("role") == "model" else "user"
                result.append({
                    "role": role,
                    "content": [{"type": "text", "text": text}]
                })
            elif "content" in ctx:
                result.append(ctx)

    for msg in messages:
        if "text" in msg:
            result.append({
                "role": "user",
                "content": [{"type": "text", "text": msg["text"]}]
            })
        elif "content" in msg:
            result.append(msg)
        elif "parts" in msg:
            text = " ".join([p.get("text", "") for p in msg["parts"] if isinstance(p, dict) and "text" in p])
            role = "assistant" if msg.get("role") == "model" else "user"
            result.append({
                "role": role,
                "content": [{"type": "text", "text": text}]
            })
    
    return result
