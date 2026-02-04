# https://github.com/spawner1145/llm-api-backup/blob/main/openai_advance.py

import httpx
import json
import mimetypes
import asyncio
import base64
import os
import uuid
from typing import AsyncGenerator, Dict, List, Optional, Union, Callable
import aiofiles
import logging
from openai import AsyncOpenAI

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OpenAIAPI:
    def __init__(
        self,
        apikey: str,
        baseurl: str = "https://api-inference.modelscope.cn",
        model: str = "deepseek-ai/DeepSeek-R1",
        proxies: Optional[Dict[str, str]] = None
    ):
        self.apikey = apikey
        self.baseurl = baseurl.rstrip('/')
        self.model = model
        self.client = AsyncOpenAI(
            api_key=apikey,
            base_url=baseurl,
            http_client=httpx.AsyncClient(proxies=proxies, timeout=60.0) if proxies else None
        )

    async def upload_file(self, file_path: str, display_name: Optional[str] = None) -> Dict[str, Union[str, None]]:
        """上传单个文件，使用 client.files.create，目的为 user_data"""
        try:
            file_size = os.path.getsize(file_path)
            if file_size > 32 * 1024 * 1024:  # 32MB 限制
                raise ValueError(f"文件 {file_path} 大小超过 32MB 限制")
        except FileNotFoundError:
            logger.error(f"文件 {file_path} 不存在")
            return {"fileId": None, "mimeType": None, "error": f"文件 {file_path} 不存在"}

        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "application/octet-stream"
            logger.warning(f"无法检测文件 {file_path} 的 MIME 类型，使用默认值: {mime_type}")

        supported_mime_types = [
            "application/pdf", "image/jpeg", "image/png", "image/webp", "image/gif"
        ]
        if mime_type not in supported_mime_types:
            logger.warning(f"MIME 类型 {mime_type} 可能不受支持，可能导致处理失败")

        try:
            async with aiofiles.open(file_path, 'rb') as f:
                file = await self.client.files.create(
                    file=(display_name or os.path.basename(file_path), await f.read(), mime_type),
                    purpose="user_data"
                )
                file_id = file.id
                logger.info(f"文件 {file_path} 上传成功，ID: {file_id}")
                return {"fileId": file_id, "mimeType": mime_type, "error": None}
        except Exception as e:
            logger.error(f"文件 {file_path} 上传失败: {str(e)}")
            return {"fileId": None, "mimeType": mime_type, "error": str(e)}

    async def upload_files(self, file_paths: List[str], display_names: Optional[List[str]] = None) -> List[Dict[str, Union[str, None]]]:
        """并行上传多个文件"""
        if not file_paths:
            raise ValueError("文件路径列表不能为空")

        if display_names and len(display_names) != len(file_paths):
            raise ValueError("display_names 长度必须与 file_paths 一致")

        tasks = [self.upload_file(file_paths[idx], display_names[idx] if display_names else None) for idx in range(len(file_paths))]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        final_results = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"上传文件 {file_paths[idx]} 失败: {str(result)}")
                final_results.append({"fileId": None, "mimeType": None, "error": str(result)})
            else:
                final_results.append(result)
        return final_results

    async def prepare_inline_image(self, file_path: str, detail: str = "auto") -> Dict[str, Union[Dict, None]]:
        """将单个图片转换为 Base64 编码的 input_image"""
        try:
            file_size = os.path.getsize(file_path)
            if file_size > 20 * 1024 * 1024:  # 20MB 限制
                raise ValueError(f"文件 {file_path} 过大，超过 20MB 限制")

            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type or mime_type not in ["image/jpeg", "image/png", "image/webp", "image/gif"]:
                mime_type = "image/jpeg"
                logger.warning(f"无效图片 MIME 类型，使用默认值: {mime_type}")

            async with aiofiles.open(file_path, 'rb') as f:
                file_content = await f.read()
            base64_data = base64.b64encode(file_content).decode('utf-8')
            return {
                "input_image": {
                    "image_url": f"data:{mime_type};base64,{base64_data}",
                    "detail": detail
                }
            }
        except Exception as e:
            logger.error(f"处理图片 {file_path} 失败: {str(e)}")
            return {"input_image": None, "error": str(e)}

    async def prepare_inline_image_batch(self, file_paths: List[str], detail: str = "auto") -> List[Dict[str, Union[Dict, None]]]:
        """将多个图片转换为 Base64 编码的 input_image 列表"""
        if not file_paths:
            raise ValueError("文件路径列表不能为空")

        results = []
        for file_path in file_paths:
            result = await self.prepare_inline_image(file_path, detail)
            results.append(result)
        return results

    async def _execute_tool(
        self,
        tool_calls: List[Union[Dict, any]],
        tools: Dict[str, Callable],
        tool_fixed_params: Optional[Dict[str, Dict]] = None
    ) -> List[Dict]:
        async def run_single_tool(tool_call):
            if isinstance(tool_call, dict):
                name = tool_call["function"]["name"]
                arguments = tool_call["function"]["arguments"]
                tool_call_id = tool_call.get("id")
            else:
                name = tool_call.function.name
                arguments = tool_call.function.arguments
                tool_call_id = tool_call.id
            
            tool_call_id = tool_call_id or f"call_{uuid.uuid4()}"
            
            try:
                args = json.loads(arguments)
                func = tools.get(name)
                
                if not func:
                    return {"role": "tool", "content": json.dumps({"error": f"未找到工具 {name}"}), "tool_call_id": tool_call_id}

                fixed_params = tool_fixed_params.get(name, tool_fixed_params.get("all", {})) if tool_fixed_params else {}
                combined_args = {**fixed_params, **args}
                
                if args:
                    logger.info(f"[Tool Call] {name} | 参数: {args}")
                else:
                    logger.info(f"[Tool Call] {name} | 无自由参数")
                
                if asyncio.iscoroutinefunction(func):
                    result = await func(**combined_args)
                else:
                    result = await asyncio.to_thread(func, **combined_args)
                
                return {
                    "role": "tool",
                    "content": json.dumps(result, ensure_ascii=False),
                    "tool_call_id": tool_call_id
                }
            except Exception as e:
                logger.error(f"工具 {name} 执行失败: {str(e)}")
                return {"role": "tool", "content": json.dumps({"error": str(e)}, ensure_ascii=False), "tool_call_id": tool_call_id}

        tasks = [run_single_tool(tc) for tc in tool_calls]
        return list(await asyncio.gather(*tasks))

    async def _chat_api(
        self,
        messages: List[Dict],
        stream: bool,
        tools: Optional[Dict[str, Callable]] = None,
        tool_fixed_params: Optional[Dict[str, Dict]] = None,
        tool_declarations: Optional[List[Dict]] = None,
        max_output_tokens: Optional[int] = None,
        system_instruction: Optional[str] = None,
        topp: Optional[float] = None,
        temperature: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        stop_sequences: Optional[List[str]] = None,
        response_format: Optional[Dict] = None,
        reasoning_effort: Optional[str] = None,
        seed: Optional[int] = None,
        response_logprobs: Optional[bool] = None,
        logprobs: Optional[int] = None,
        retries: int = 3
    ) -> AsyncGenerator[Union[str, Dict], None]:
        """核心 API 调用逻辑，遵循 OpenAI 标准，支持 reasoning_content 但不记录到历史"""
        original_model = self.model

        # 验证参数
        if topp is not None and (topp < 0 or topp > 1):
            raise ValueError("top_p 必须在 0 到 1 之间")
        if temperature is not None and (temperature < 0 or temperature > 2):
            raise ValueError("temperature 必须在 0 到 2 之间")
        if presence_penalty is not None and (presence_penalty < -2 or presence_penalty > 2):
            raise ValueError("presence_penalty 必须在 -2 到 2 之间")
        if frequency_penalty is not None and (frequency_penalty < -2 or frequency_penalty > 2):
            raise ValueError("frequency_penalty 必须在 -2 到 2 之间")
        if logprobs is not None and (logprobs < 0 or logprobs > 20):
            raise ValueError("logprobs 必须在 0 到 20 之间")
        if reasoning_effort is not None and reasoning_effort not in ["minimal", "low", "medium", "high"]:
            raise ValueError("reasoning_effort 必须是 minimal、low、medium 或 high")

        # 构造消息
        api_messages = []
        for msg in messages:
            role = msg["role"]
            content = msg.get("content", "")
            if isinstance(content, str):
                api_content = [{"type": "text", "text": content}]
            elif isinstance(content, list):
                api_content = []
                for part in content:
                    if "text" in part:
                        api_content.append({"type": "text", "text": part["text"]})
                    elif "input_file" in part:
                        api_content.append({
                            "type": "input_file",
                            "file_id": part["input_file"]["file_id"]
                        } if "file_id" in part["input_file"] else {
                            "type": "input_file",
                            "filename": part["input_file"]["filename"],
                            "file_data": part["input_file"]["file_data"]
                        })
                    elif "input_image" in part:
                        api_content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": part["input_image"]["image_url"],
                                "detail": part["input_image"].get("detail", "auto")
                            }
                        })
                    elif part.get("type") == "image_url" and "image_url" in part:
                        api_content.append(part)
            else:
                raise ValueError(f"无效的消息内容格式: {content}")
            api_msg = {
                "role": role,
                "content": api_content
            }
            if "tool_calls" in msg:
                api_msg["tool_calls"] = msg["tool_calls"]
            if "tool_call_id" in msg:
                api_msg["tool_call_id"] = msg["tool_call_id"]
            logger.debug(f"构造消息: {json.dumps(api_msg, ensure_ascii=False)}")
            api_messages.append(api_msg)

        # 构造请求参数
        request_params = {
            "model": self.model,
            "messages": api_messages,
            "stream": stream
        }
        if max_output_tokens is not None:
            request_params["max_tokens"] = max_output_tokens
        if topp is not None:
            request_params["top_p"] = topp
        if temperature is not None:
            request_params["temperature"] = temperature
        if stop_sequences is not None:
            request_params["stop"] = stop_sequences
        if presence_penalty is not None:
            request_params["presence_penalty"] = presence_penalty
        if frequency_penalty is not None:
            request_params["frequency_penalty"] = frequency_penalty
        if seed is not None:
            request_params["seed"] = seed
        if response_logprobs is not None:
            request_params["logprobs"] = response_logprobs
            if logprobs is not None:
                request_params["top_logprobs"] = logprobs
        if response_format:
            request_params["response_format"] = response_format
        if reasoning_effort is not None:
            request_params["reasoning_effort"] = reasoning_effort

        if tools is not None:
            # 如果提供了预定义的 tool_declarations，优先使用它（转换为 OpenAI 格式）
            if tool_declarations:
                tool_names = set(tools.keys())
                tool_definitions = []
                for decl in tool_declarations:
                    if decl.get("name") in tool_names:
                        # 转换 Gemini 格式到 OpenAI 格式
                        params = decl.get("parameters", {"type": "object", "properties": {}, "required": []})
                        if "additionalProperties" not in params:
                            params["additionalProperties"] = False
                        tool_definitions.append({
                            "type": "function",
                            "function": {
                                "name": decl["name"],
                                "description": decl.get("description", f"调用 {decl['name']} 函数"),
                                "parameters": params
                            }
                        })
                if not tool_definitions:
                    logger.warning("tool_declarations 中没有与 tools 匹配的函数声明，回退到自动推断")
                    tool_declarations = None
                else:
                    request_params["tools"] = tool_definitions
            
            # 如果没有提供 tool_declarations 或过滤后为空，则自动推断
            if not tool_declarations:
                tool_definitions = []
                # 获取全局固定参数（如果存在）
                fixed_params = tool_fixed_params.get("all", {}) if tool_fixed_params else {}
                for name, func in tools.items():
                    params = {
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False
                    }
                    if hasattr(func, "__code__"):
                        param_names = func.__code__.co_varnames[:func.__code__.co_argcount]
                        # 排除固定参数，仅声明动态参数
                        dynamic_params = [p for p in param_names if p not in fixed_params]
                        for param in dynamic_params:
                            params["properties"][param] = {"type": "string"}
                            params["required"].append(param)
                    else:
                        params["properties"] = {"arg": {"type": "string"}}
                        params["required"] = ["arg"]
                    tool_definitions.append({
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": getattr(func, "__doc__", f"调用 {name} 函数"),
                            "parameters": params
                        }
                    })
                request_params["tools"] = tool_definitions

        #print(f"[DEBUG] OpenAI request params: {json.dumps(request_params, ensure_ascii=False, indent=2, default=str)}")

        if stream:
            assistant_content = ""
            tool_calls_buffer = []
            async for chunk in await self.client.chat.completions.create(**request_params):
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        yield {"thought": delta.reasoning_content}
                    if delta.content:
                        yield delta.content
                        assistant_content += delta.content
                    elif delta.tool_calls:
                        for tool_call in delta.tool_calls:
                            if tool_call and tool_call.function:
                                tool_call_id = tool_call.id or f"call_{uuid.uuid4()}"
                                try:
                                    arguments = tool_call.function.arguments or "{}"
                                    json.loads(arguments)
                                    tc_dict = {
                                        "id": tool_call_id,
                                        "type": "function",
                                        "function": {
                                            "name": tool_call.function.name,
                                            "arguments": arguments
                                        }
                                    }
                                    if hasattr(tool_call, 'extra_content') and tool_call.extra_content:
                                        tc_dict["extra_content"] = tool_call.extra_content
                                    elif isinstance(tool_call, dict) and "extra_content" in tool_call:
                                        tc_dict["extra_content"] = tool_call["extra_content"]
                                    tool_calls_buffer.append(tc_dict)
                                except json.JSONDecodeError:
                                    continue
                        if chunk.choices[0].finish_reason == "tool_calls" and tool_calls_buffer:
                            assistant_message = {
                                "role": "assistant",
                                "content": [{"type": "text", "text": "Tool calls executed"}],
                                "tool_calls": tool_calls_buffer
                            }
                            api_messages.append(assistant_message)
                            messages.append(assistant_message)
                            tool_messages = await self._execute_tool(
                                tool_calls_buffer, 
                                tools, 
                                tool_fixed_params
                            )
                            
                            api_messages.extend(tool_messages)
                            messages.extend(tool_messages)
                            second_request_params = request_params.copy()
                            second_request_params["messages"] = api_messages
                            second_request_params["stream"] = True
                            try:
                                async for chunk in await self.client.chat.completions.create(**second_request_params):
                                    if chunk.choices:
                                        delta = chunk.choices[0].delta
                                        if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                                            yield {"thought": delta.reasoning_content}
                                        if delta.content:
                                            yield delta.content
                                            assistant_content += delta.content
                                        if chunk.choices[0].finish_reason in ["stop", "length"]:
                                            if assistant_content:
                                                messages.append({
                                                    "role": "assistant",
                                                    "content": [{"type": "text", "text": assistant_content}]
                                                })
                                            assistant_content = ""
                            except Exception as e:
                                logger.error(f"第二次 API 调用失败: {str(e)}")
                                yield f"错误: 无法获取最终响应 - {str(e)}"
                                messages.append({
                                    "role": "assistant",
                                    "content": [{"type": "text", "text": f"错误: {str(e)}"}]
                                })
                            tool_calls_buffer = []
                    if chunk.choices[0].finish_reason in ["stop", "length"]:
                        if assistant_content:
                            messages.append({
                                "role": "assistant",
                                "content": [{"type": "text", "text": assistant_content}]
                            })
                        assistant_content = ""
        else:
            for attempt in range(retries):
                try:
                    response = await self.client.chat.completions.create(**request_params)
                    choice = response.choices[0]
                    message = choice.message
                    if message.tool_calls:
                        tool_calls = []
                        for tc in message.tool_calls:
                            tc_dict = {
                                "id": tc.id or f"call_{uuid.uuid4()}",
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                }
                            }
                            if hasattr(tc, 'extra_content') and tc.extra_content:
                                tc_dict["extra_content"] = tc.extra_content
                            elif isinstance(tc, dict) and "extra_content" in tc:
                                tc_dict["extra_content"] = tc["extra_content"]
                            tool_calls.append(tc_dict)
                        assistant_message = {
                            "role": "assistant",
                            "content": [{"type": "text", "text": "Tool calls executed"}],
                            "tool_calls": tool_calls
                        }
                        api_messages.append(assistant_message)
                        messages.append(assistant_message)
                        tool_messages = await self._execute_tool(message.tool_calls, tools, tool_fixed_params)
                        api_messages.extend(tool_messages)
                        messages.extend(tool_messages)
                        second_request_params = request_params.copy()
                        second_request_params["messages"] = api_messages
                        second_request_params["stream"] = False
                        response = await self.client.chat.completions.create(**second_request_params)
                        choice = response.choices[0]
                        message = choice.message
                        assistant_message = {
                            "role": "assistant",
                            "content": [{"type": "text", "text": message.content or ""}]
                        }
                        messages.append(assistant_message)
                        if hasattr(message, 'reasoning_content') and message.reasoning_content:
                            yield {"thought": message.reasoning_content}
                        if message.content:
                            yield message.content
                    else:
                        assistant_message = {
                            "role": "assistant",
                            "content": [{"type": "text", "text": message.content or ""}]
                        }
                        if response_logprobs and choice.logprobs:
                            assistant_message["logprobs"] = choice.logprobs.content
                            messages.append(assistant_message)
                            if hasattr(message, 'reasoning_content') and message.reasoning_content:
                                yield {"thought": message.reasoning_content}
                            yield f"{message.content or ''}\nLogprobs: {json.dumps(choice.logprobs.content, ensure_ascii=False)}"
                        else:
                            messages.append(assistant_message)
                            if hasattr(message, 'reasoning_content') and message.reasoning_content:
                                yield {"thought": message.reasoning_content}
                            if message.content:
                                yield message.content
                    break
                except Exception as e:
                    logger.error(f"API 调用失败 (尝试 {attempt+1}/{retries}): {str(e)}")
                    if attempt == retries - 1:
                        raise
                    await asyncio.sleep(2 ** attempt)

        self.model = original_model

    async def chat(
        self,
        messages: Union[str, List[Dict[str, any]]],
        stream: bool = False,
        tools: Optional[Dict[str, Callable]] = None,
        tool_fixed_params: Optional[Dict[str, Dict]] = None,
        tool_declarations: Optional[List[Dict]] = None,
        max_output_tokens: Optional[int] = None,
        system_instruction: Optional[str] = None,
        topp: Optional[float] = None,
        temperature: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        stop_sequences: Optional[List[str]] = None,
        response_format: Optional[Dict] = None,
        reasoning_effort: Optional[str] = None,
        seed: Optional[int] = None,
        response_logprobs: Optional[bool] = None,
        logprobs: Optional[int] = None,
        retries: int = 3
    ) -> AsyncGenerator[Union[str, Dict], None]:
        """发起聊天请求，支持多文件和多图片输入"""
        if isinstance(messages, str):
            messages = [{"role": "user", "content": [{"type": "text", "text": messages}]}]
        if system_instruction:
            for i, message in enumerate(messages):
                if message.get("role") == "system":
                    messages[i] = {"role": "system", "content": [{"type": "text", "text": system_instruction}]}
                    break
            else:
                messages.insert(0, {"role": "system", "content": [{"type": "text", "text": system_instruction}]})

        async for part in self._chat_api(
            messages, stream, tools, tool_fixed_params, tool_declarations,
            max_output_tokens, system_instruction, topp, temperature,
            presence_penalty, frequency_penalty,
            stop_sequences, response_format,
            reasoning_effort, seed, response_logprobs, logprobs,
            retries
        ):
            yield part

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.client.aclose()

# 示例工具函数
async def schedule_meeting(event: str, config: Dict, start_time: str, duration: str, attendees: str) -> str:
    """安排一个会议，参数包括事件、配置、开始时间、持续时间和与会者"""
    return f"会议已安排：事件 {event}，配置 {config}，开始时间 {start_time}，持续时间 {duration}，与会者 {attendees}。"

async def get_weather(event: str, config: Dict, location: str) -> str:
    """获取指定地点的天气信息"""
    return f"{location} 的天气是晴天，温度 25°C（事件 {event}，配置 {config}）。"

async def get_time(event: str, config: Dict, city: str) -> str:
    """获取指定城市的当前时间"""
    return f"{city} 的当前时间是 2025 年 4 月 24 日 13:00（事件 {event}，配置 {config}）。"

async def send_email(event: str, config: Dict, to: str, body: str) -> str:
    """发送电子邮件"""
    return f"邮件已发送至 {to}，内容：{body}（事件 {event}，配置 {config}）。"

# 主函数
async def main():
    api = OpenAIAPI(
        apikey="",  # 请替换为你的实际 API 密钥
        baseurl="https://api-inference.modelscope.cn/v1/",
        model="deepseek-ai/DeepSeek-R1",
        proxies={
            "http://": "http://127.0.0.1:7890",
            "https://": "http://127.0.0.1:7890"
        }
    )
    tools = {
        "schedule_meeting": schedule_meeting,
        "get_weather": get_weather,
        "get_time": get_time,
        "send_email": send_email
    }
    tool_fixed_params = {
        "all": {
            "event": "Team Sync",
            "config": {"location": "Room A", "priority": "high"}
        }
    }

    # 示例 1：单轮对话（非流式，无额外参数）
    print("示例 1：单轮对话（非流式，无额外参数）")
    messages = [{"role": "user", "content": [{"type": "text", "text": "法国的首都是哪里？"}]}]
    async for part in api.chat(messages, stream=False):
        if isinstance(part, dict) and "thought" in part:
            print("思考过程:", part["thought"], flush=True)
        else:
            print(part, end="", flush=True)
    print("\n更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 2：多轮对话（非流式，无额外参数）
    print("示例 2：多轮对话（非流式，无额外参数）")
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "法国的首都是哪里？"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "法国的首都是巴黎。"}]},
        {"role": "user", "content": [{"type": "text", "text": "巴黎的人口是多少？"}]}
    ]
    async for part in api.chat(messages, stream=False):
        if isinstance(part, dict) and "thought" in part:
            print("思考过程:", part["thought"], flush=True)
        else:
            print(part, end="", flush=True)
    print("\n更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 3：单轮对话（流式，无额外参数）
    print("示例 3：单轮对话（流式，无额外参数）")
    messages = [{"role": "user", "content": [{"type": "text", "text": "讲一个关于魔法背包的故事。"}]}]
    async for part in api.chat(messages, stream=True):
        if isinstance(part, dict) and "thought" in part:
            print("思考过程:", part["thought"], flush=True)
        else:
            print(part, end="", flush=True)
    print("\n更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 4：多轮对话（流式，带工具和 presence_penalty）
    print("示例 4：多轮对话（流式，带工具和 presence_penalty）")
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "今天纽约的天气如何？"}]}
    ]
    async for part in api.chat(messages, stream=True, tools=tools, tool_fixed_params=tool_fixed_params, presence_penalty=0.5):
        if isinstance(part, dict) and "thought" in part:
            print("思考过程:", part["thought"], flush=True)
        else:
            print(part, end="", flush=True)
    print("\n更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 5：多个工具调用（流式，带工具）
    print("示例 5：多个工具调用（流式，带工具）")
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "请安排一个明天上午10点的会议，持续1小时，与会者是Alice和Bob。然后告诉我巴黎和波哥大的天气，并给 Bob 发送一封邮件（bob@email.com），内容为 'Hi Bob'。"}]}
    ]
    async for part in api.chat(messages, stream=True, tools=tools, tool_fixed_params=tool_fixed_params):
        if isinstance(part, dict) and "thought" in part:
            print("思考过程:", part["thought"], flush=True)
        else:
            print(part, end="", flush=True)
    print("\n更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 6：推理模式（流式，启用推理）
    # reasoning_effort 可选：minimal、low、medium、high
    print("示例 6：推理模式（流式，启用推理）")
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "你好"}]}
    ]
    async for part in api.chat(messages, stream=True, max_output_tokens=500, reasoning_effort="low"):
        if isinstance(part, dict) and "thought" in part:
            print("思考过程:", part["thought"], flush=True)
        else:
            print(part, end="", flush=True)
    print("\n更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 7：结构化输出（非流式，使用 response_format）
    print("示例 7：结构化输出（非流式，使用 response_format）")
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "person_info",
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer"}
                },
                "required": ["name", "age"],
                "additionalProperties": False
            },
            "strict": True
        }
    }
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "请提供一个人的信息，包括姓名和年龄。"}]}
    ]
    async for part in api.chat(messages, stream=False, response_format=response_format):
        if isinstance(part, dict) and "thought" in part:
            continue
        print("结构化输出:", part, end="", flush=True)
    print("\n更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 8：聊天中使用多文件上传（PDF）
    print("示例 8：聊天中使用多文件上传（PDF）")
    file_paths = [
        'pdf1.pdf',
        'pdf2.pdf'
    ]
    display_names = ["doc1.pdf", "doc2.pdf"]

    # 上传文件
    upload_results = await api.upload_files(file_paths, display_names)
    file_parts = []
    for idx, result in enumerate(upload_results):
        if result["fileId"] and not result["error"]:
            file_parts.append({
                "input_file": {
                    "file_id": result["fileId"]
                }
            })
        else:
            print(f"文件 {file_paths[idx]} 上传失败: {result['error']}")

    if file_parts:
        # 构造包含 input_file 的聊天消息
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "请总结以下 PDF 文件的要点："},
                *file_parts
            ]
        }]
        print("发送 PDF 文件进行聊天：")
        async for part in api.chat(messages, stream=False):
            if isinstance(part, dict) and "thought" in part:
                continue
            print(part, end="", flush=True)
        print("\n更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    else:
        print("无有效文件 ID，无法发起聊天")
    print()

    # 示例 9：聊天中使用多 inline 图片
    print("示例 9：聊天中使用多 inline 图片")
    file_paths = [
        '《Break the Cocoon》封面.jpg',
        '92D32EDFF4535D91F4E60234FD4703E1.jpg'
    ]

    # 转换为 inline 图片
    inline_results = await api.prepare_inline_image_batch(file_paths, detail="high")
    image_parts = []
    for idx, result in enumerate(inline_results):
        if "input_image" in result and result["input_image"]:
            image_parts.append({
                "input_image": result["input_image"]
            })
        else:
            print(f"图片 {file_paths[idx]} 处理失败: {result.get('error', '未知错误')}")

    if image_parts:
        # 构造包含 input_image 的聊天消息
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "请描述以下图片的内容："},
                *image_parts
            ]
        }]
        print("发送 inline 图片进行聊天：")
        async for part in api.chat(messages, stream=False):
            if isinstance(part, dict) and "thought" in part:
                continue
            print(part, end="", flush=True)
        print("\n更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    else:
        print("无有效 inline 图片，无法发起聊天")
    print()

if __name__ == "__main__":
    asyncio.run(main())
