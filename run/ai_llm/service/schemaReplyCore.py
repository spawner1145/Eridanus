import json
import random
from typing import Dict, Any

from framework_common.database_util.llmDB import update_user_history
from run.ai_llm.service.aiReplyHandler.gemini import get_current_gemini_prompt
from run.ai_llm.service.schemaHandler.gemini import GeminiFormattedChat
async def schemaReplyCore(config,schema: Dict[str, Any],user_message: str,user_id: int,keep_history=False):
    prompt = await get_current_gemini_prompt(user_id)
    if config.ai_llm.config["llm"]["model"]=="gemini":
        gemini_chatter=GeminiFormattedChat(api_key=random.choice(config.ai_llm.config["llm"]["gemini"]["api_keys"]),
                                           model_name=config.ai_llm.config["llm"]["gemini"]["model"],
                                           proxy=config.common_config.basic_config["proxy"]["http_proxy"] if config.ai_llm.config["llm"]["enable_proxy"] else None,
                                           base_url=config.ai_llm.config["llm"]["gemini"]["base_url"])
        copy_history = prompt.copy()  # 备份，出错的时候可以rollback
        copy_history.append({"role": "user", "parts": [{"text": user_message}]})
        model_response_parts = await gemini_chatter.chat(copy_history, schema)
        if config.ai_code_generator.ai_coder["多轮对话"] or keep_history:
            copy_history.append({"role": "model", "parts":[{"text": str(model_response_parts)}]})
            await update_user_history(user_id, copy_history)
        return model_response_parts