import json
import random
from typing import Dict, Any

from framework_common.database_util.llmDB import update_user_history
from framework_common.utils.GeminiKeyManager import GeminiKeyManager
from run.ai_llm.service.aiReplyHandler.gemini import get_current_gemini_prompt
from run.ai_llm.clients.gemini_client import GeminiAPI


async def schemaReplyCore(config, schema: Dict[str, Any], user_message: str, user_id: int, keep_history=False, group_messages_bg=[], model_set=None):
    prompt = await get_current_gemini_prompt(user_id)
    if config.ai_llm.config["llm"]["model"] == "gemini":
        proxy = config.common_config.basic_config["proxy"]["http_proxy"] if config.ai_llm.config["llm"]["enable_proxy"] else None
        proxies = {"http://": proxy, "https://": proxy} if proxy else None

        api = GeminiAPI(
            apikey=await GeminiKeyManager.get_gemini_apikey(),
            baseurl=config.ai_llm.config["llm"]["gemini"]["base_url"],
            model=model_set if model_set else config.ai_llm.config["llm"]["gemini"]["model"],
            proxies=proxies
        )

        copy_history = prompt.copy()
        copy_history.append({"role": "user", "parts": [{"text": user_message}]})
        if group_messages_bg:
            copy_history.insert(0, group_messages_bg[0])
            copy_history.insert(1, group_messages_bg[1])

        response_text = ""
        async for part in api.chat(
            copy_history,
            stream=False,
            response_schema=schema,
        ):
            if isinstance(part, str):
                response_text += part

        # 尝试解析为 JSON
        try:
            model_response_parts = json.loads(response_text) if response_text else None
        except json.JSONDecodeError:
            model_response_parts = response_text

        # 使用 get 方法安全获取配置，避免 KeyError
        multi_turn_enabled = False
        try:
            multi_turn_enabled = config.ai_llm.config.get("llm", {}).get("多轮对话", False)
        except (AttributeError, KeyError):
            pass
        
        # 如果需要保存历史记录
        if keep_history:
            copy_history.append({"role": "model", "parts": [{"text": str(model_response_parts)}]})
            # 只有启用多轮对话时才保存到数据库
            if multi_turn_enabled:
                await update_user_history(user_id, copy_history)
        
        return model_response_parts