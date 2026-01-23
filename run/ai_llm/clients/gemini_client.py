# https://github.com/spawner1145/llm-api-backup/blob/main/gemini_advance.py

import httpx
import json
import mimetypes
import asyncio
import base64
import os
from typing import AsyncGenerator, Dict, List, Optional, Union, Callable
import aiofiles
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def format_grounding_metadata(grounding_metadata: Dict) -> str:
    if not grounding_metadata:
        return ""
    
    parts = []
    
    # 搜索查询
    if "webSearchQueries" in grounding_metadata:
        queries = grounding_metadata["webSearchQueries"]
        if queries:
            parts.append("搜索查询:")
            for q in queries:
                parts.append(f" - {q}")
    
    # 搜索来源
    if "groundingChunks" in grounding_metadata:
        chunks = grounding_metadata["groundingChunks"]
        if chunks:
            parts.append("\n参考来源:")
            seen_uris = set()
            for chunk in chunks:
                web = chunk.get("web", {})
                uri = web.get("uri", "")
                title = web.get("title", "未知标题")
                if uri and uri not in seen_uris:
                    seen_uris.add(uri)
                    parts.append(f" - [{title}]({uri})")
    
    # Google 搜索链接
    if "searchEntryPoint" in grounding_metadata:
        entry = grounding_metadata["searchEntryPoint"]
        rendered_content = entry.get("renderedContent", "")
        if rendered_content:
            parts.append("\n可通过 Google 搜索查看更多结果")
    
    return "\n".join(parts)


class GeminiAPI:
    def __init__(
        self,
        apikey: str,
        baseurl: str = "https://generativelanguage.googleapis.com",
        model: str = "gemini-2.0-flash-001",
        fallback_models: Optional[List[str]] = None,
        proxies: Optional[Dict[str, str]] = None
    ):
        self.apikey = apikey
        self.baseurl = baseurl.rstrip('/')
        # fallback_models 优先，如果提供了则使用第一个作为当前模型
        if fallback_models and len(fallback_models) > 0:
            self.model = fallback_models[0]
            self.fallback_models = fallback_models
            self.current_model_index = 0
        else:
            self.model = model
            self.fallback_models = [model] if model else []
            self.current_model_index = 0
        self.client = httpx.AsyncClient(
            base_url=baseurl,
            params={'key': apikey},
            proxies=proxies,
            timeout=60.0
        )
        self.tools = None  # 保存工具定义
    
    def _fallback_to_next_model(self) -> bool:
        """切换到下一个模型，返回是否成功"""
        if self.current_model_index < len(self.fallback_models) - 1:
            self.current_model_index += 1
            self.model = self.fallback_models[self.current_model_index]
            logger.warning(f"切换到下一个模型: {self.model}")
            return True
        return False
    
    def _reset_model(self):
        """重置到第一个模型"""
        self.current_model_index = 0
        if self.fallback_models:
            self.model = self.fallback_models[0]

    async def upload_file(self, file_path: str, display_name: Optional[str] = None) -> Dict[str, Union[str, None]]:
        """上传单个文件到 Gemini File API，并检查 ACTIVE 状态"""
        try:
            file_size = os.path.getsize(file_path)
            if file_size > 2 * 1024 * 1024 * 1024:  # 2GB 限制
                raise ValueError(f"文件 {file_path} 大小超过 2GB 限制")
        except FileNotFoundError:
            logger.error(f"文件 {file_path} 不存在")
            return {"fileUri": None, "mimeType": None, "error": f"文件 {file_path} 不存在"}

        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "application/octet-stream"
            logger.warning(f"无法检测文件 {file_path} 的 MIME 类型，使用默认值: {mime_type}")

        supported_mime_types = [
            "image/jpeg", "image/png", "image/gif", "image/webp",
            "video/mp4", "video/mpeg", "video/avi", "video/wmv", "video/flv",
            "audio/mp3", "audio/wav", "audio/ogg", "audio/flac",
            "text/plain", "text/markdown"
        ]
        if mime_type not in supported_mime_types:
            logger.warning(f"MIME 类型 {mime_type} 可能不受支持，可能导致上传失败")

        try:
            async with aiofiles.open(file_path, 'rb') as f:
                files = {'file': (display_name or os.path.basename(file_path), await f.read(), mime_type)}
                logger.info(f"上传文件请求: {file_path}")
                response = await self.client.post("/upload/v1beta/files", files=files)
                response.raise_for_status()
                file_data = response.json()
                logger.info(f"文件上传响应: {file_data}")
                file_uri = file_data['file'].get('uri')
                if not file_uri:
                    logger.error(f"文件 {file_path} 上传成功但未返回 URI: {file_data}")
                    return {"fileUri": None, "mimeType": mime_type, "error": f"文件 {file_path} 上传成功但未返回 URI"}
        except httpx.HTTPStatusError as e:
            logger.error(f"文件 {file_path} 上传失败: {e.response.text}")
            return {"fileUri": None, "mimeType": mime_type, "error": f"文件 {file_path} 上传失败: {e.response.text}"}
        except Exception as e:
            logger.error(f"文件 {file_path} 上传失败: {str(e)}")
            return {"fileUri": None, "mimeType": mime_type, "error": f"文件 {file_path} 上传失败: {str(e)}"}

        if not await self.wait_for_file_active(file_uri, timeout=120, interval=2):
            logger.error(f"文件 {file_path} 未能在规定时间内变为 ACTIVE 状态")
            return {"fileUri": None, "mimeType": mime_type, "error": f"文件 {file_path} 未能在规定时间内变为 ACTIVE 状态"}

        logger.info(f"文件 {file_path} 上传并激活成功，URI: {file_uri}")
        return {"fileUri": file_uri, "mimeType": mime_type, "error": None}

    async def wait_for_file_active(self, file_uri: str, timeout: Optional[int] = None, interval: int = 2) -> bool:
        """等待文件状态变为 ACTIVE"""
        file_id = file_uri.split('/')[-1]
        start_time = asyncio.get_event_loop().time()

        while timeout is None or (asyncio.get_event_loop().time() - start_time < timeout):
            try:
                response = await self.client.get(f"/v1beta/files/{file_id}")
                response.raise_for_status()
                file_info = response.json()
                logger.debug(f"文件 {file_id} 状态响应: {file_info}")
                state = file_info.get('state')
                if state == "ACTIVE":
                    logger.info(f"文件 {file_id} 已就绪，状态: {state}")
                    return True
                elif state == "FAILED":
                    logger.error(f"文件 {file_id} 处理失败，状态: {state}")
                    return False
                else:
                    logger.info(f"文件 {file_id} 仍在处理中，状态: {state}")
                    await asyncio.sleep(interval)
            except httpx.HTTPStatusError as e:
                logger.error(f"检查文件 {file_id} 状态失败: {e.response.text}")
                return False
            except Exception as e:
                logger.error(f"检查文件 {file_id} 状态失败: {str(e)}")
                return False
        logger.error(f"等待文件 {file_id} 超时 ({timeout}秒)")
        return False

    async def upload_files(self, file_paths: List[str], display_names: Optional[List[str]] = None) -> List[Dict[str, Union[str, None]]]:
        """并行上传多个文件到 Gemini File API"""
        if not file_paths:
            raise ValueError("文件路径列表不能为空")

        if display_names and len(display_names) != len(file_paths):
            raise ValueError("display_names 长度必须与 file_paths 一致")

        tasks = []
        for idx, file_path in enumerate(file_paths):
            display_name = display_names[idx] if display_names else None
            tasks.append(self.upload_file(file_path, display_name))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        final_results = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"上传文件 {file_paths[idx]} 失败: {str(result)}")
                final_results.append({"fileUri": None, "mimeType": None, "error": str(result)})
            else:
                final_results.append(result)
        return final_results

    async def prepare_inline_data(self, file_path: str) -> Dict[str, Dict[str, str]]:
        """将单个小文件转换为 Base64 编码的 inlineData"""
        file_size = os.path.getsize(file_path)
        if file_size * 4 / 3 > 20 * 1024 * 1024:
            raise ValueError(f"文件 {file_path} 过大，无法作为 inlineData，建议使用 File API 上传")

        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "application/octet-stream"
            logger.warning(f"无法检测文件 {file_path} 的 MIME 类型，使用默认值: {mime_type}")

        async with aiofiles.open(file_path, 'rb') as f:
            file_content = await f.read()

        base64_data = base64.b64encode(file_content).decode('utf-8')
        return {
            "inlineData": {
                "mimeType": mime_type,
                "data": base64_data
            }
        }

    async def prepare_inline_data_batch(self, file_paths: List[str]) -> List[Dict[str, Union[Dict[str, str], None]]]:
        """将多个小文件转换为 Base64 编码的 inlineData 列表"""
        if not file_paths:
            raise ValueError("文件路径列表不能为空")

        total_size = 0
        results = []
        for file_path in file_paths:
            try:
                file_size = os.path.getsize(file_path)
                encoded_size = file_size * 4 / 3
                total_size += encoded_size
                if total_size > 20 * 1024 * 1024:
                    raise ValueError(f"文件 {file_path} 加入后总大小超过 20MB，无法作为 inlineData")
                inline_data = await self.prepare_inline_data(file_path)
                results.append(inline_data)
            except Exception as e:
                logger.error(f"处理文件 {file_path} 失败: {str(e)}")
                results.append({"inlineData": None, "error": str(e)})
        return results

    async def _execute_tool(
        self,
        function_calls: List[Dict],
        tools: Dict[str, Callable],
        tool_fixed_params: Optional[Dict[str, Dict]] = None
    ) -> List[Dict]:
        async def run_single_tool(function_call):
            name = function_call["name"]
            args = function_call.get("args", {})
            func = tools.get(name)
            
            if not func:
                return {
                    "role": "user",
                    "parts": [{"functionResponse": {"name": name, "response": {"error": f"工具 {name} 未定义"}}}]
                }
            try:
                fixed_params = tool_fixed_params.get(name, tool_fixed_params.get("all", {})) if tool_fixed_params else {}
                combined_args = {**fixed_params, **args}
                
                if asyncio.iscoroutinefunction(func):
                    result = await func(**combined_args)
                else:
                    result = await asyncio.to_thread(func, **combined_args)
                    
                return {
                    "role": "user",
                    "parts": [{"functionResponse": {"name": name, "response": {"result": str(result)}}}]
                }
            except Exception as e:
                return {
                    "role": "user",
                    "parts": [{"functionResponse": {"name": name, "response": {"error": str(e)}}}]
                }
        tasks = [run_single_tool(call) for call in function_calls]
        function_responses = await asyncio.gather(*tasks)
        
        return list(function_responses)

    async def _chat_api(
        self,
        api_contents: List[Dict],
        stream: bool,
        tools: Optional[Dict[str, Callable]] = None,
        tool_fixed_params: Optional[Dict[str, Dict]] = None,
        tool_declarations: Optional[List[Dict]] = None,
        max_output_tokens: Optional[int] = None,
        system_instruction: Optional[str] = None,
        topp: Optional[float] = None,
        temperature: Optional[float] = None,
        include_thoughts: Optional[bool] = None,
        thinking_budget: Optional[int] = None,
        thinking_level: Optional[str] = None,
        topk: Optional[int] = None,
        candidate_count: Optional[int] = None,
        presence_penalty: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        stop_sequences: Optional[List[str]] = None,
        response_mime_type: Optional[str] = None,
        response_schema: Optional[Dict] = None,
        seed: Optional[int] = None,
        response_logprobs: Optional[bool] = None,
        logprobs: Optional[int] = None,
        audio_timestamp: Optional[bool] = None,
        safety_settings: Optional[List[Dict]] = None,
        google_search: bool = False,
        url_context: bool = False,
        retries: int = 3
    ) -> AsyncGenerator[Union[str, Dict], None]:
        """核心 API 调用逻辑"""
        if topp is not None and (topp < 0 or topp > 1):
            raise ValueError("topP 必须在 0 到 1 之间")
        if temperature is not None and (temperature < 0 or temperature > 2):
            raise ValueError("temperature 必须在 0 到 2 之间")
        if topk is not None and topk < 1:
            raise ValueError("topK 必须是正整数")
        if candidate_count is not None and (candidate_count < 1 or candidate_count > 8):
            raise ValueError("candidateCount 必须在 1 到 8 之间")
        if presence_penalty is not None and (presence_penalty < -2 or presence_penalty > 2):
            raise ValueError("presencePenalty 必须在 -2 到 2 之间")
        if frequency_penalty is not None and (frequency_penalty < -2 or frequency_penalty > 2):
            raise ValueError("frequencyPenalty 必须在 -2 到 2 之间")
        if response_mime_type is not None and response_mime_type not in ["text/plain", "application/json"]:
            raise ValueError("responseMimeType 必须是 'text/plain' 或 'application/json'")
        if logprobs is not None and (logprobs < 0 or logprobs > 5):
            raise ValueError("logprobs 必须在 0 到 5 之间")

        if tools:
            self.tools = tools

        body = {"contents": api_contents}
        
        api_tools = []

        if google_search:
            api_tools.append({"google_search": {}})
        if url_context:
            api_tools.append({"url_context": {}})
        if tools:
            # 如果提供了预定义的 tool_declarations，优先使用它
            if tool_declarations:
                # 过滤出 tools 中存在的函数声明
                tool_names = set(tools.keys())
                filtered_declarations = [decl for decl in tool_declarations if decl.get("name") in tool_names]
                if filtered_declarations:
                    api_tools.append({"functionDeclarations": filtered_declarations})
                else:
                    logger.warning("tool_declarations 中没有与 tools 匹配的函数声明，回退到自动推断")
                    tool_declarations = None
            
            # 如果没有提供 tool_declarations 或过滤后为空，则自动推断
            if not tool_declarations:
                function_declarations = []
                fixed_params = tool_fixed_params.get("all", {}) if tool_fixed_params else {}
                for name, func in tools.items():
                    params = []
                    if hasattr(func, "__code__"):
                        params = func.__code__.co_varnames[:func.__code__.co_argcount]
                    else:
                        logger.warning(f"函数 {name} 没有 __code__ 属性，使用空参数列表")
                    dynamic_params = [p for p in params if p not in fixed_params]
                    parameters = {
                        "type": "object",
                        "properties": {param: {"type": "string"} for param in dynamic_params},
                        "required": dynamic_params
                    }
                    function_declarations.append({
                        "name": name,
                        "description": getattr(func, "__doc__", f"调用 {name} 函数"),
                        "parameters": parameters
                    })
                api_tools.append({"functionDeclarations": function_declarations})
        
        if api_tools:
            body["tools"] = api_tools
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if safety_settings is None:
            body["safetySettings"] = [
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
        else:
            body["safetySettings"] = safety_settings

        generation_config = {}
        if max_output_tokens:
            generation_config["maxOutputTokens"] = max_output_tokens
        if topp:
            generation_config["topP"] = topp
        if temperature:
            generation_config["temperature"] = temperature
        if topk:
            generation_config["topK"] = topk
        if candidate_count:
            generation_config["candidateCount"] = candidate_count
        if presence_penalty:
            generation_config["presencePenalty"] = presence_penalty
        if frequency_penalty:
            generation_config["frequencyPenalty"] = frequency_penalty
        if stop_sequences:
            generation_config["stopSequences"] = stop_sequences
        if response_schema:
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = response_schema
        elif response_mime_type:
            generation_config["responseMimeType"] = response_mime_type
        if seed:
            generation_config["seed"] = seed
        if response_logprobs is not None:
            generation_config["responseLogprobs"] = response_logprobs
        if logprobs is not None:
            generation_config["logprobs"] = logprobs
        if audio_timestamp is not None:
            generation_config["audioTimestamp"] = audio_timestamp
        if include_thoughts == True:
            generation_config.setdefault("thinkingConfig", {})["include_thoughts"] = True
        if thinking_budget is not None:
            generation_config.setdefault("thinkingConfig", {})["thinkingBudget"] = thinking_budget
        if thinking_level is not None:
            generation_config.setdefault("thinkingConfig", {})["thinkingLevel"] = thinking_level

        if generation_config:
            body["generationConfig"] = generation_config

        if stream:
            # 流式请求支持模型降级
            stream_attempt = 0
            max_stream_attempts = len(self.fallback_models)
            while stream_attempt < max_stream_attempts:
                endpoint = f"/v1beta/models/{self.model}:streamGenerateContent"
                logger.info(f"请求端点: {endpoint}")
                try:
                    async with self.client.stream("POST", endpoint, json=body, params={'alt': 'sse'}) as response:
                        logger.info(f"流式响应状态: {response.status_code}")
                        
                        # 检查 429 错误
                        if response.status_code == 429:
                            logger.warning(f"模型 {self.model} 配额耗尽 (429)")
                            if self._fallback_to_next_model():
                                stream_attempt += 1
                                await asyncio.sleep(1)
                                continue
                            else:
                                logger.error("所有模型配额均已耗尽")
                                raise httpx.HTTPStatusError("所有模型配额均已耗尽", request=response.request, response=response)
                        
                        try:
                            response.raise_for_status()
                        except httpx.HTTPStatusError as e:
                            logger.error(f"流式 HTTP 错误: {e}")
                            logger.error(f"失败的请求体: {json.dumps(body, ensure_ascii=False, indent=2)}")
                            logger.error(f"服务器响应: {await response.aread()}")
                            raise
                        model_message = {"role": "model", "parts": []}
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data = line[len("data: "):].strip()
                                if data:
                                    try:
                                        chunk = json.loads(data)
                                        #print("debug:", chunk)
                                        for candidate in chunk.get("candidates", []):
                                            for part in candidate.get("content", {}).get("parts", []):
                                                model_message["parts"].append(part)
                                                if part.get("thought") is True:
                                                    yield {"thought": part.get("text")}
                                                elif "text" in part:
                                                    yield part["text"]
                                                elif "functionCall" in part and tools:
                                                    if model_message["parts"]:
                                                        api_contents.append(model_message)
                                                    function_calls = [part["functionCall"]]
                                                    function_responses = await self._execute_tool(function_calls, tools, tool_fixed_params)
                                                    api_contents.extend(function_responses)
                                                    async for text in self._chat_api(
                                                        api_contents, stream=stream, tools=tools, tool_fixed_params=tool_fixed_params,
                                                        tool_declarations=tool_declarations,
                                                        max_output_tokens=max_output_tokens,
                                                        system_instruction=system_instruction,
                                                        topp=topp, temperature=temperature,
                                                        include_thoughts=include_thoughts,
                                                        thinking_budget=thinking_budget,
                                                        thinking_level=thinking_level,
                                                        topk=topk, candidate_count=candidate_count,
                                                        presence_penalty=presence_penalty,
                                                        frequency_penalty=frequency_penalty,
                                                        stop_sequences=stop_sequences,
                                                        response_mime_type=response_mime_type,
                                                        response_schema=response_schema,
                                                        seed=seed, response_logprobs=response_logprobs,
                                                        logprobs=logprobs, audio_timestamp=audio_timestamp,
                                                        safety_settings=safety_settings,
                                                        google_search=google_search,
                                                        url_context=url_context,
                                                        retries=retries
                                                    ):
                                                        yield text
                                                    model_message = {"role": "model", "parts": []}
                                            if "groundingMetadata" in candidate:
                                                yield {"grounding_metadata": candidate["groundingMetadata"]}
                                    except json.JSONDecodeError as e:
                                        logger.error(f"流式 JSON 解析错误: {e}")
                        if model_message["parts"] and not any("functionCall" in part for part in model_message["parts"]):
                            api_contents.append(model_message)
                        break  # 成功完成，跳出重试循环
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        logger.warning(f"流式请求模型 {self.model} 配额耗尽 (429)")
                        if self._fallback_to_next_model():
                            stream_attempt += 1
                            await asyncio.sleep(1)
                            continue
                    raise
        else:
            total_attempts = retries * len(self.fallback_models)  # 总尝试次数 = 重试次数 * 模型数量
            attempt = 0
            while attempt < total_attempts:
                try:
                    endpoint = f"/v1beta/models/{self.model}:generateContent"
                    response = await self.client.post(endpoint, json=body)
                    logger.info(f"非流式响应状态: {response.status_code}")
                    
                    # 检查 429 错误
                    if response.status_code == 429:
                        logger.warning(f"模型 {self.model} 配额耗尽 (429)")
                        if self._fallback_to_next_model():
                            attempt += 1
                            await asyncio.sleep(1)  # 短暂等待后重试
                            continue
                        else:
                            logger.error("所有模型配额均已耗尽")
                            raise httpx.HTTPStatusError("所有模型配额均已耗尽", request=response.request, response=response)
                    
                    response.raise_for_status()
                    result = response.json()
                    #print("debug:", result)
                    candidate = result["candidates"][0]
                    model_message = candidate["content"] 
                    api_contents.append(model_message)
                    parts = model_message.get("parts", [])
                    for part in parts:
                        if part.get("thought") is True:
                            yield {"thought": part.get("text")}
                        elif "text" in part:
                            yield part["text"]
                    
                    # 解析并返回 groundingMetadata（如果存在）
                    if "groundingMetadata" in candidate:
                        grounding_metadata = candidate["groundingMetadata"]
                        yield {"grounding_metadata": grounding_metadata}
                    
                    function_calls = [part["functionCall"] for part in candidate["content"]["parts"] if "functionCall" in part]
                    if function_calls:
                        logger.info(f"发现函数调用: {function_calls}")
                        function_responses = await self._execute_tool(function_calls, tools, tool_fixed_params)
                        api_contents.extend(function_responses)
                        async for text in self._chat_api(
                            api_contents, stream=False, tools=tools, tool_fixed_params=tool_fixed_params,
                            tool_declarations=tool_declarations,
                            max_output_tokens=max_output_tokens,
                            system_instruction=system_instruction,
                            topp=topp, temperature=temperature,
                            include_thoughts=include_thoughts,
                            thinking_budget=thinking_budget,
                            thinking_level=thinking_level,
                            topk=topk, candidate_count=candidate_count,
                            presence_penalty=presence_penalty,
                            frequency_penalty=frequency_penalty,
                            stop_sequences=stop_sequences,
                            response_mime_type=response_mime_type,
                            response_schema=response_schema,
                            seed=seed, response_logprobs=response_logprobs,
                            logprobs=logprobs, audio_timestamp=audio_timestamp,
                            safety_settings=safety_settings,
                            google_search=google_search,
                            url_context=url_context,
                            retries=retries
                        ):
                            yield text
                    break
                except httpx.HTTPStatusError as e:
                    # 检查是否是 429 错误（在 raise_for_status 之后捕获）
                    if e.response.status_code == 429:
                        logger.warning(f"模型 {self.model} 配额耗尽 (429)")
                        if self._fallback_to_next_model():
                            attempt += 1
                            await asyncio.sleep(1)
                            continue
                        else:
                            logger.error("所有模型配额均已耗尽")
                            raise
                    logger.error(f"HTTP 错误 (尝试 {attempt+1}/{total_attempts}): {e}")
                    logger.error(f"失败的请求体: {json.dumps(body, ensure_ascii=False, indent=2)}")
                    logger.error(f"服务器响应: {e.response.text}")
                    attempt += 1
                    if attempt >= total_attempts:
                        raise
                    await asyncio.sleep(2 ** (attempt % retries))
                except json.JSONDecodeError:
                    logger.error(f"JSON 解析错误 (尝试 {attempt+1}/{total_attempts})")
                    logger.error(f"失败的请求体: {json.dumps(body, ensure_ascii=False, indent=2)}")
                    attempt += 1
                    if attempt >= total_attempts:
                        raise ValueError("无效的 JSON 响应")
                    await asyncio.sleep(2 ** (attempt % retries))

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
        include_thoughts: Optional[bool] = None,
        include_thoughts_in_history: bool = False,
        thinking_budget: Optional[int] = None,
        thinking_level: Optional[str] = None,
        topk: Optional[int] = None,
        candidate_count: Optional[int] = None,
        presence_penalty: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        stop_sequences: Optional[List[str]] = None,
        response_mime_type: Optional[str] = None,
        response_schema: Optional[Dict] = None,
        seed: Optional[int] = None,
        response_logprobs: Optional[bool] = None,
        logprobs: Optional[int] = None,
        audio_timestamp: Optional[bool] = None,
        safety_settings: Optional[List[Dict]] = None,
        google_search: bool = False,
        url_context: bool = False,
        retries: int = 3
    ) -> AsyncGenerator[Union[str, Dict, List[Dict[str, any]]], None]:
        """发起聊天请求"""
        if isinstance(messages, str):
            messages = [{"role": "user", "parts": [{"text": messages}]}]
            use_history = False
        else:
            use_history = True

        api_contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            parts = []
            for p in msg["parts"]:
                if isinstance(p, str):
                    parts.append({"text": p})
                elif isinstance(p, dict) and ("fileData" in p or "inlineData" in p or "functionCall" in p or "functionResponse" in p):
                    parts.append(p)
                else:
                    parts.append(p)
            api_contents.append({"role": role, "parts": parts})

        full_text = ""
        thought = []
        logprobs_data = []
        grounding_metadata = None
        async for part in self._chat_api(
            api_contents, stream, tools, tool_fixed_params, tool_declarations,
            max_output_tokens, system_instruction, topp, temperature, include_thoughts, thinking_budget, thinking_level,
            topk, candidate_count, presence_penalty, frequency_penalty,
            stop_sequences, response_mime_type, response_schema,
            seed, response_logprobs, logprobs, audio_timestamp,
            safety_settings, google_search, url_context, retries
        ):
            if isinstance(part, dict):
                if "text" in part:
                    if not part.get("thought"): 
                        full_text += part["text"]
                
                if "thought" in part and part["thought"]:
                    val = part["thought"]
                    thought.extend(val if isinstance(val, list) else [val])
                
                if "logprobs" in part and part["logprobs"]:
                    logprobs_data.extend(part["logprobs"])
                
                if "grounding_metadata" in part:
                    grounding_metadata = part["grounding_metadata"]
                
                yield part
            else:
                full_text += part
                yield part

        # 更新用户的历史记录（messages），确保与 api_contents 同步
        if use_history:
            messages.clear()
            for content in api_contents:
                # role 映射：API 返回 "model"，前端习惯用 "assistant"
                role = "assistant" if content["role"] == "model" else "user"
                parts_for_history = content["parts"]
                if not include_thoughts_in_history:
                    parts_for_history = [
                        part for part in parts_for_history
                        if not (isinstance(part, dict) and part.get("thought") is True)
                    ]
                messages.append({
                    "role": role,
                    "parts": parts_for_history # 默认不写入 thought 内容
                })

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.client.aclose()

# 示例工具函数
async def schedule_meeting(event: str, config: Dict, start_time: str, duration: str, attendees: str) -> str:
    """安排一个会议，参数包括事件、配置、开始时间、持续时间和与会者"""
    print(f"安排会议：事件 {event}，配置 {config}，开始时间 {start_time}，持续时间 {duration}，与会者 {attendees}")
    return f"会议已安排：事件 {event}，配置 {config}，开始时间 {start_time}，持续时间 {duration}，与会者 {attendees}。"

async def get_weather(event: str, config: Dict, location: str) -> str:
    """获取指定地点的天气信息"""
    print(f"获取 {location} 的天气信息（事件 {event}，配置 {config}）")
    return f"{location} 的天气是晴天，温度 25°C（事件 {event}，配置 {config}）。"

async def get_time(event: str, config: Dict, city: str) -> str:
    """获取指定城市的当前时间"""
    print(f"获取 {city} 的当前时间（事件 {event}，配置 {config}）")
    return f"{city} 的当前时间是 2025 年 4 月 23 日 18:00（事件 {event}，配置 {config}）。"

# 主函数
async def main():
    PROXY = 'http://127.0.0.1:7890'
    if PROXY and PROXY.strip():
        proxies = {
            "http://": PROXY,
            "https://": PROXY
        }
    else:
        proxies = None
    api = GeminiAPI(
        apikey="",
        model='gemini-3-flash-preview',
        proxies=proxies,
        baseurl="https://generativelanguage.googleapis.com"
    )
    tools = {
        "schedule_meeting": schedule_meeting,
        "get_weather": get_weather,
        "get_time": get_time
    }
    tool_fixed_params = {
        "all": {
            "event": "Team Sync",
            "config": {"location": "Room A", "priority": "high"}
        }
    }

    # 示例 1：单轮对话（非流式）
    print("示例 1：单轮对话（非流式）")
    async for part in api.chat("法国的首都是哪里？", stream=False):
        print(part)
    print()

    # 示例 2：多轮对话（非流式）
    print("示例 2：多轮对话（非流式）")
    messages = [
        {"role": "user", "parts": [{"text": "法国的首都是哪里？"}]},
        {"role": "assistant", "parts": [{"text": "法国的首都是巴黎。"}]},
        {"role": "user", "parts": [{"text": "巴黎的人口是多少？"}]}
    ]
    async for part in api.chat(messages, stream=False):
        print(part)
    print("更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 3：单轮对话（流式）
    print("示例 3：单轮对话（流式）")
    async for part in api.chat("讲一个关于魔法背包的故事。", stream=True):
        print(part, end="", flush=True)
    print("\n")

    # 示例 4：多轮对话（流式，带工具）
    print("示例 4：多轮对话（流式，带工具）")
    messages = [
        {"role": "user", "parts": [{"text": "你好！"}]},
        {"role": "assistant", "parts": [{"text": "你好！有什么可以帮助你的？"}]},
        {"role": "user", "parts": [{"text": "今天纽约的天气如何？"}]}
    ]
    async for part in api.chat(messages, stream=True, tools=tools, tool_fixed_params=tool_fixed_params):
        print(part, end="", flush=True)
    print("\n更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 5：多个工具调用（非流式）
    print("示例 5：多个工具调用（非流式）")
    messages = [
        {"role": "user", "parts": [{"text": "请安排一个明天上午10点的会议，持续1小时，与会者是Alice和Bob。然后告诉我纽约的天气和时间。"}]}
    ]
    async for part in api.chat(messages, stream=False, tools=tools, tool_fixed_params=tool_fixed_params):
        print(part)
    print("更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 6：思考模式（非流式，启用思考）非常不建议不用流式，不用流式这玩意很容易卡死
    print("示例 6：思考模式（非流式，启用思考）")
    messages = [
        {"role": "user", "parts": [{"text": "解决数学问题：用数字 10、8、3、7、1 和常用运算符，构造一个表达式等于 24，只能使用每个数字一次。"}]}
    ]
    # include_thoughts表示是否返回思维链，一般是开的，-1thinking_budget表示模型自由决定思考token，如果说gemini3系列的用thinking_level，有"minimal"、"low"、"medium" 和 "high"，默认是"high"的
    # 设置了thinking_budget或者thinking_level后，最好开启include_thoughts，这样可以看到思考过程，否则api不会返回思维链
    async for part in api.chat(messages, stream=False, include_thoughts=True, thinking_budget=-1):
        if isinstance(part, dict) and "thought" in part:
            print("思考过程:", part["thought"]) # 这边代表单独提取思维链的内容
        else:
            print(part)
    print("更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 7：思考模式（流式，启用思考）
    print("示例 7：思考模式（流式，启用思考）")
    messages = [
        {"role": "user", "parts": [{"text": "解决数学问题：用数字 10、8、3、7、1 和常用运算符，构造一个表达式等于 24，只能使用每个数字一次。"}]}
    ]
    async for part in api.chat(messages, stream=True, include_thoughts=True, thinking_budget=-1):
        if isinstance(part, dict) and "thought" in part:
            print("思考过程:", part["thought"]) # 这边代表单独提取思维链的内容
        else:
            print("流式输出:", part, end="", flush=True)
    print("\n更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 8：思考模式（非流式，禁用思考）
    print("示例 8：思考模式（非流式，禁用思考）")
    messages = [
        {"role": "user", "parts": [{"text": "解决数学问题：用数字 10、8、3、7、1 和常用运算符，构造一个表达式等于 24，只能使用每个数字一次。"}]}
    ]
    # 必须要thinking_budget=0，include_thoughts不影响是否思考，gemini3好像思考关不掉的，并且gemini3要带上thinking_level='minimal'
    async for part in api.chat(messages, stream=False, thinking_budget=0):
        print("最终回答:", part)
    print("更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 9：Google 搜索（非流式，使用 google_search 工具）
    print("示例 9：Google 搜索（非流式）")
    messages = [
        {"role": "user", "parts": [{"text": "2024年诺贝尔物理学奖授予了谁？"}]}
    ]
    async for part in api.chat(messages, stream=False, google_search=True):
        if isinstance(part, dict) and "grounding_metadata" in part:
            # 使用辅助函数格式化 grounding metadata
            formatted = format_grounding_metadata(part["grounding_metadata"])
            print("搜索来源信息:\n", formatted)
        else:
            print("回答:", part)
    print("更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 10：Google 搜索（流式）
    print("示例 10：Google 搜索（流式）")
    messages = [
        {"role": "user", "parts": [{"text": "最新的AI发展趋势是什么？"}]}
    ]
    async for part in api.chat(messages, stream=True, google_search=True):
        if isinstance(part, dict) and "grounding_metadata" in part:
            formatted = format_grounding_metadata(part["grounding_metadata"])
            print("\n搜索来源信息:\n", formatted)
        else:
            print(part, end="", flush=True)
    print("\n更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 11：URL 上下文（非流式，使用 url_context 工具抓取 URL 内容）
    print("示例 11：URL 上下文（非流式）")
    messages = [
        {"role": "user", "parts": [{"text": "总结这个网页的内容：https://blog.google/technology/ai/google-gemini-ai/"}]}
    ]
    async for part in api.chat(messages, stream=False, url_context=True):
        if isinstance(part, dict) and "grounding_metadata" in part:
            formatted = format_grounding_metadata(part["grounding_metadata"])
            print("URL 来源信息:\n", formatted)
        else:
            print("回答:", part)
    print("更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 12：同时启用 Google 搜索和 URL 上下文
    print("示例 12：同时启用 Google 搜索和 URL 上下文")
    messages = [
        {"role": "user", "parts": [{"text": "查看 https://www.python.org/ 并告诉我 Python 最新版本，同时搜索 Python 3.12 的新特性"}]}
    ]
    async for part in api.chat(messages, stream=False, google_search=True, url_context=True):
        if isinstance(part, dict) and "grounding_metadata" in part:
            formatted = format_grounding_metadata(part["grounding_metadata"])
            print("来源信息:\n", formatted)
        else:
            print("回答:", part)
    print("更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 13：结构化输出（非流式，使用 response_schema）
    print("示例 13：结构化输出")
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "用户的姓名"},
            "age": {"type": "integer", "description": "用户的年龄"}
        },
        "required": ["name", "age"],
        # 字段顺序
        "propertyOrdering": ["name", "age"]
    }
    messages = [{"role": "user", "parts": [{"text": "生成一个虚构的人物信息"}]}]
    
    async for part in api.chat(
        messages, 
        stream=False, 
        response_schema=schema # 具体的结构化格式
    ):
        print("结构化输出:", part)
    print("更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    print()

    # 示例 14：并行使用 File API 上传多个图像并生成描述（非流式）
    print("示例 14：并行使用 File API 上传多个图像并生成描述（非流式）")
    try:
        image_files = ["image1.jpg", "image2.png"]  # 请替换为实际图像路径
        file_data_list = await api.upload_files(image_files, display_names=["Image 1", "Image 2"])
        parts = [{"text": "描述这些图片中的内容。"}]
        for file_data in file_data_list:
            if file_data["fileUri"]:
                parts.append({"fileData": {"fileUri": file_data["fileUri"], "mimeType": file_data["mimeType"]}})
            else:
                print(f"文件上传失败: {file_data['error']}")
        if not any("fileData" in part for part in parts[1:]):
            print("所有文件上传失败，跳过请求")
        else:
            messages = [{"role": "user", "parts": parts}]
            async for part in api.chat(messages, stream=False):
                print("多图像描述:", part)
            print("更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    except FileNotFoundError as e:
        print(f"文件不存在: {e}")
    print()

    # 示例 15：并行使用 File API 上传图像和视频并总结内容（非流式）
    print("示例 15：并行使用 File API 上传图像和视频并总结内容（非流式）")
    try:
        media_files = ["image1.jpg", "video1.mp4"]  # 请替换为实际文件路径
        file_data_list = await api.upload_files(media_files, display_names=["Image 1", "Video 1"])
        parts = [{"text": "总结这些媒体文件的内容。"}]
        for file_data in file_data_list:
            if file_data["fileUri"]:
                parts.append({"fileData": {"fileUri": file_data["fileUri"], "mimeType": file_data["mimeType"]}})
            else:
                print(f"文件上传失败: {file_data['error']}")
        if not any("fileData" in part for part in parts[1:]):
            print("所有文件上传失败，跳过请求")
        else:
            messages = [{"role": "user", "parts": parts}]
            async for part in api.chat(messages, stream=False):
                print("媒体总结:", part)
            print("更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    except FileNotFoundError as e:
        print(f"文件不存在: {e}")
    print()

    # 示例 16：使用多个内联 Base64 图像生成描述（非流式）
    print("示例 16：使用多个内联 Base64 图像生成描述（非流式）")
    try:
        image_files = ["image1.jpg", "image2.png"]  # 请替换为实际小图像路径（<10MB）
        inline_data_list = await api.prepare_inline_data_batch(image_files)
        parts = [{"text": "描述这些图片中的内容。"}]
        for inline_data in inline_data_list:
            if inline_data.get("inlineData"):
                parts.append(inline_data)
            else:
                print(f"内联数据处理失败: {inline_data['error']}")
        messages = [{"role": "user", "parts": parts}]
        async for part in api.chat(messages, stream=False):
            print("多内联图像描述:", part)
        print("更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    except FileNotFoundError as e:
        print(f"文件不存在: {e}")
    except ValueError as e:
        print(f"内联数据错误: {e}")
    print()

    # 示例 17：混合并行上传文件和多内联数据（文本文件 + 多图像，非流式）
    print("示例 17：混合并行上传文件和多内联数据（文本文件 + 多图像，非流式）")
    try:
        text_files = ["requirements.txt"]  # 请替换为实际文本文件路径
        image_files = ["image1.jpg", "image2.png"]  # 请替换为实际小图像路径（<10MB）
        file_data_list = await api.upload_files(text_files, display_names=["Sample Text"])
        inline_data_list = await api.prepare_inline_data_batch(image_files)
        parts = [{"text": "根据上传的文本文件总结内容，并描述旁边的图片。"}]
        for file_data in file_data_list:
            if file_data["fileUri"]:
                parts.append({"fileData": {"fileUri": file_data["fileUri"], "mimeType": file_data["mimeType"]}})
            else:
                print(f"文件上传失败: {file_data['error']}")
        for inline_data in inline_data_list:
            if inline_data.get("inlineData"):
                parts.append(inline_data)
            else:
                print(f"内联数据处理失败: {inline_data['error']}")
        if not any("fileData" in part or "inlineData" in part for part in parts[1:]):
            print("所有文件和内联数据处理失败，跳过请求")
        else:
            messages = [{"role": "user", "parts": parts}]
            async for part in api.chat(messages, stream=False):
                print("混合内容输出:", part)
            print("更新后的消息列表：", json.dumps(messages, ensure_ascii=False, indent=2))
    except FileNotFoundError as e:
        print(f"文件不存在: {e}")
    except ValueError as e:
        print(f"内联数据错误: {e}")
    print()

if __name__ == "__main__":
    asyncio.run(main())