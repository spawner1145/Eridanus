import httpx
import os
import json
import asyncio
from typing import List, Dict, Any, Optional, Union

from framework_common.utils.system_logger import get_logger

logger=get_logger("gemini_chat")
class GeminiFormattedChat:
    """
    一个封装了Gemini多轮对话和格式化JSON输出的异步客户端。
    """

    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash-lite",proxy:str=None,base_url: str="https://generativelanguage.googleapis.com"):
        """
        初始化Gemini聊天客户端。

        Args:
            api_key (str): 你的Gemini API Key。
            model_name (str): 要使用的Gemini模型名称，默认为 "gemini-1.5-flash"。
                              你也可以使用 "gemini-1.5-pro" 或其他可用模型。
        """
        if proxy:
            self.proxies={
                "http://": proxy,
                "https://": proxy
            }
        else:
            self.proxies=None
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required.")
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = f"{base_url}/v1beta/models/{self.model_name}:generateContent"
        # 使用 httpx.AsyncClient() 来处理异步请求
        # 最好在整个应用生命周期中重用同一个客户端实例
        self._client = httpx.AsyncClient(proxies=self.proxies)
        #self.history: List[Dict[str, Any]] = [] # 存储多轮对话历史

    async def _send_request(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        内部方法：发送HTTP请求到Gemini API。
        """
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json"
        }

        try:
            response = await self._client.post(self.base_url, headers=headers, json=payload, timeout=60.0)
            response.raise_for_status()  # 如果状态码是 4xx 或 5xx，则抛出异常
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP错误 occurred: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            logger.error(f"请求错误 occurred: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误 occurred: {e}. Response text: {response.text}")
            return None
        except Exception as e:
            logger.error(f"一个未知错误 occurred: {e}")
            return None

    async def chat(
        self,
        prompt: list,
        response_schema: Optional[Dict[str, Any]] = None,
        generation_config: Optional[Dict[str, Any]] = None
    ) -> Optional[Union[str, Dict[str, Any], List[Dict[str, Any]]]]:
        """
        发送用户消息并获取Gemini的响应。支持自定义JSON格式输出。

        Args:
            user_message (str): 用户输入的消息。
            response_schema (Optional[Dict[str, Any]]): 期望的JSON输出模式。
                如果提供，responseMimeType将自动设置为 "application/json"。
                例如：
                {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "recipeName": { "type": "STRING" },
                            "ingredients": {
                                "type": "ARRAY",
                                "items": { "type": "STRING" }
                            }
                        },
                        "propertyOrdering": ["recipeName", "ingredients"]
                    }
                }
            generation_config (Optional[Dict[str, Any]]): 额外的生成配置参数，
                例如 temperature, topK, topP 等。
                此字典将与 responseMimeType 和 responseSchema 合并。

        Returns:
            Optional[Union[str, Dict[str, Any], List[Dict[str, Any]]]]:
            如果成功，返回模型响应的内容。
            - 如果没有指定 `response_schema`，返回字符串（文本）。
            - 如果指定了 `response_schema` 并且模型成功返回JSON，返回解析后的Python对象（字典或列表）。
            - 如果失败，返回 None。
        """
        # 将用户消息添加到历史记录
        #self.history.append({"role": "user", "parts": [{"text": user_message}]})

        payload_generation_config = generation_config if generation_config else {}

        if response_schema:
            payload_generation_config["responseMimeType"] = "application/json"
            payload_generation_config["responseSchema"] = response_schema

        payload = {
            "contents": prompt,
            "generationConfig": payload_generation_config
        }
        #print(prompt)
        response_data = await self._send_request(payload)

        if not response_data or "candidates" not in response_data:
            logger.error("未能从Gemini获取有效响应。")
            # 移除最后一条用户消息，因为它没有得到有效响应
            if prompt and prompt[-1]["role"] == "user":
                prompt.pop()
            return None

        # 提取模型响应
        candidate = response_data["candidates"][0]
        if "content" not in candidate or "parts" not in candidate["content"]:
            logger.error("Gemini响应中没有找到内容部分。")
            # 移除最后一条用户消息
            if prompt and prompt[-1]["role"] == "user":
                prompt.pop()
            return None

        model_response_parts = candidate["content"]["parts"]

        # 将模型响应添加到历史记录
        # 注意：这里直接添加了模型的原始 parts，因为它可以是 text 也可以是 json
        #prompt.append({"role": "model", "parts": model_response_parts})

        # 解析模型响应
        if response_schema:
            if model_response_parts and "json" in model_response_parts[0]:
                return model_response_parts[0]["json"]
            else:
                logger.warning("警告：期望JSON输出，但模型返回了非JSON内容或格式不符。")
                # 尝试返回原始文本，以防万一
                if model_response_parts and "text" in model_response_parts[0]:
                    #return model_response_parts[0]["text"]
                    return json.loads(model_response_parts[0]["text"])
                return None
        else:
            # 如果没有指定 response_schema，期望返回的是文本
            if model_response_parts and "text" in model_response_parts[0]:
                return model_response_parts[0]["text"]
            elif model_response_parts and "json" in model_response_parts[0]:
                 # 意外返回JSON，将其转换为字符串
                return json.dumps(model_response_parts[0]["json"], ensure_ascii=False, indent=2)
            return None

    def get_history(self) -> List[Dict[str, Any]]:
        """
        获取当前的对话历史。
        """
        return self.history

    def reset_history(self):
        """
        清空对话历史。
        """
        self.history = []
        print("对话历史已清空。")

    async def close(self):
        """
        关闭内部的 httpx 客户端连接。
        在应用程序结束时调用。
        """
        await self._client.aclose()
        print("Gemini客户端连接已关闭。")

