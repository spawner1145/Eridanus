import random
from typing import Dict, Any

from run.ai_llm.service.aiReplyHandler.gemini import get_current_gemini_prompt
from run.ai_llm.service.schemaHandler.gemini import GeminiFormattedChat
async def schemaReplyCore(config,schema: Dict[str, Any],user_message: str,user_id: int):
    prompt = await get_current_gemini_prompt(user_id)
    if config.ai_llm.config["llm"]["model"]=="gemini":
        gemini_chatter=GeminiFormattedChat(api_key=random.choice(config.ai_llm.config["llm"]["gemini"]["api_keys"]),
                                           model_name=config.ai_llm.config["llm"]["gemini"]["model"],
                                           proxy=config.common_config.basic_config["proxy"]["http_proxy"] if config.ai_llm.config["llm"]["enable_proxy"] else None,
                                           base_url=config.ai_llm.config["llm"]["gemini"]["base_url"])
        original_history = prompt.copy()  # 备份，出错的时候可以rollback
        original_history.append({"role": "user", "parts": [{"text": user_message}]})
        return await gemini_chatter.chat(original_history,schema)