import random
from typing import Optional

from developTools.utils.logger import get_logger
from framework_common.utils.GeminiKeyManager import GeminiKeyManager
from run.ai_llm.clients.gemini_client import GeminiAPI, format_grounding_metadata

logger = get_logger("official_search_tool")


async def search_with_official_api(bot, event, config, query: str, urls: Optional[str] = None):
    try:
        google_search_enabled = config.ai_llm.config["llm"].get("google_search", False)
        url_context_enabled = config.ai_llm.config["llm"].get("url_context", False)
        show_grounding_metadata = config.ai_llm.config["llm"].get("联网搜索显示原始数据", True)
        
        if not google_search_enabled and not url_context_enabled:
            return {"result": "官方搜索功能未开启，请在配置中启用 google_search 或 url_context"}
        
        proxy = config.common_config.basic_config["proxy"]["http_proxy"] if config.ai_llm.config["llm"][
            "enable_proxy"] else None
        proxies = {"http://": proxy, "https://": proxy} if proxy else None
        search_config = config.ai_llm.config["llm"].get("search_client", {})
        search_api_key = search_config.get("api_key", "").strip()
        if not search_api_key:
            search_api_key = await GeminiKeyManager.get_gemini_apikey()
        search_base_url = search_config.get("base_url", "").strip()
        if not search_base_url:
            search_base_url = config.ai_llm.config["llm"]["gemini"]["base_url"]
        
        # 模型选择逻辑：指定模型 + fallback_models 列表
        search_model = search_config.get("model", "").strip()
        gemini_fallback_models = config.ai_llm.config["llm"]["gemini"].get("fallback_models", [])
        if search_model:
            # 如果指定了模型，则该模型作为首选，后面跟着 fallback_models
            fallback_models = [search_model] + [m for m in gemini_fallback_models if m != search_model]
        else:
            # 如果没有指定模型，则直接使用 fallback_models
            fallback_models = gemini_fallback_models
        
        api = GeminiAPI(
            apikey=search_api_key,
            baseurl=search_base_url,
            fallback_models=fallback_models,
            proxies=proxies
        )
        
        if urls:
            url_list = [u.strip() for u in urls.split(",") if u.strip()]
            if url_list:
                prompt_content = f"请访问以下网址并回答问题：\n网址：{', '.join(url_list)}\n问题：{query}"
            else:
                prompt_content = query
        else:
            prompt_content = query
        
        messages = [{"role": "user", "parts": [{"text": prompt_content}]}]
        search_system_instruction = (
            "你是一个专业的信息搜索助手。你的任务是根据用户的问题进行联网搜索或访问指定网页，"
            "然后提供准确、简洁、有用的信息。请注意：\n"
            "1. 优先使用搜索结果中的最新信息\n"
            "2. 如果搜索结果包含多个来源，请综合整理\n"
            "3. 对于时效性信息（如新闻、天气、股票等），请注明信息的时间\n"
            "4. 如果无法找到相关信息，请如实告知"
        )
        
        # 只启用官方搜索功能，不启用任何自定义 tools
        response_text = ""
        grounding_metadata = None
        
        async for part in api.chat(
            messages,
            stream=True,
            tools=None,
            system_instruction=search_system_instruction,
            google_search=google_search_enabled,
            url_context=url_context_enabled,
            temperature=config.ai_llm.config["llm"]["gemini"]["temperature"],
            max_output_tokens=config.ai_llm.config["llm"]["gemini"]["maxOutputTokens"],
        ):
            if isinstance(part, dict) and part.get("grounding_metadata"):
                grounding_metadata = part["grounding_metadata"]
            elif isinstance(part, str):
                response_text += part
        if grounding_metadata and show_grounding_metadata and bot and event:
            from developTools.message.message_components import Node, Text
            formatted_metadata = format_grounding_metadata(grounding_metadata)
            if formatted_metadata:
                await bot.send(event, [Node(content=[Text(formatted_metadata)])])
        
        result = response_text.strip() if response_text else "搜索未返回结果"
        return {"result": result}
        
    except Exception as e:
        logger.error(f"官方搜索功能调用失败: {e}")
        import traceback
        traceback.print_exc()
        return {"result": f"搜索失败: {str(e)}"}
