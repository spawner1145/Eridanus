import json
from typing import Dict, Any, List, Union

from run.ai_llm.clients.gemini_client import GeminiAPI


class AiChatbot:
    def __init__(self, model, api_key, proxy, base_url):
        self.ai_model = model
        self.api_key = api_key
        self.proxy = proxy
        self.base_url = base_url

    async def get_response(self, prompt: str, tools: Union[List, None] = None,
                           system_instruction: Union[str, None] = None, temperature: float = 0.7,
                           maxOutputTokens: int = 2048, response_schema: Union[Dict, None] = None) -> Dict[str, Any]:
        """
        获取AI响应，现在可以接收response_schema来强制结构化输出。
        """
        contents = [
            {
                "parts": [
                    {
                        "text": prompt,
                    }
                ],
                "role": "user"
            },
        ]

        proxies = {"http://": self.proxy, "https://": self.proxy} if self.proxy else None

        api = GeminiAPI(
            apikey=self.api_key,
            baseurl=self.base_url,
            model=self.ai_model,
            proxies=proxies
        )

        response_text = ""
        async for part in api.chat(
            contents,
            stream=False,
            temperature=temperature,
            max_output_tokens=maxOutputTokens,
            response_schema=response_schema,
        ):
            if isinstance(part, str):
                response_text += part

        # 尝试解析为 JSON
        try:
            result = json.loads(response_text) if response_text else {}
        except json.JSONDecodeError:
            result = {"text": response_text}

        return result