import httpx
import json
from typing import Dict, Any, List, Union

class AiChatbot:
    def __init__(self, ai_model, api_key,proxy,base_url):
        self.ai_model = ai_model
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

        r = await self.geminiRequest(
            ask_prompt=contents,
            base_url=self.base_url,
            apikey=self.api_key,
            model=self.ai_model,
            proxy=self.proxy,
            tools=tools,
            temperature=temperature,
            maxOutputTokens=maxOutputTokens,
            response_schema=response_schema # 将schema传递下去
        )
        return r

    async def geminiRequest(self, ask_prompt: List[Dict[str, Any]], base_url: str, apikey: str, model: str,
                            proxy: Union[str, None] = None, tools: Union[List, None] = None,
                            temperature: float = 0.7, maxOutputTokens: int = 2048,
                            response_schema: Union[Dict, None] = None) -> Dict[str, Any]:
        """
        发送请求到Gemini API，支持结构化输出。
        """
        if proxy is not None and proxy != "":
            proxies = {"http://": proxy, "https://": proxy}
        else:
            proxies = None
        url = f"{base_url}/v1beta/models/{model}:generateContent?key={apikey}"

        generation_config = {
            "temperature": temperature,
            "topK": 64,
            "topP": 0.95,
            "maxOutputTokens": maxOutputTokens,
            "responseMimeType": "application/json"
        }

        if response_schema:
            generation_config["responseSchema"] = response_schema

        pay_load = {
            "contents": ask_prompt,
            "safetySettings": [
                {'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT', "threshold": "BLOCK_NONE"},
                {'category': 'HARM_CATEGORY_HATE_SPEECH', "threshold": "BLOCK_NONE"},
                {'category': 'HARM_CATEGORY_HARASSMENT', "threshold": "BLOCK_NONE"},
                {'category': 'HARM_CATEGORY_DANGEROUS_CONTENT', "threshold": "BLOCK_NONE"}
            ],
            "generationConfig": generation_config
        }
        if tools is not None:
            pay_load["tools"] = tools

        async with httpx.AsyncClient(proxies=proxies, timeout=100) as client:
            r = await client.post(url, json=pay_load)
            r.raise_for_status()
            print(r.json())
            return r.json()