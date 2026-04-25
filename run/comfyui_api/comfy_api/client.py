import httpx, json, asyncio, uuid, os, aiofiles, websockets, mimetypes, re
from typing import Dict, Any, Optional, List, AsyncGenerator

from .config import (
    HTTP_TIMEOUT, WS_OPEN_TIMEOUT, WS_PING_INTERVAL,
    WS_PING_TIMEOUT, WORKFLOW_EXECUTION_TIMEOUT,
    DOWNLOAD_RETRY_ATTEMPTS, DOWNLOAD_RETRY_DELAY
)
from .workflow import ComfyWorkflow

_SENTINEL = object()

class ComfyUIClient:
    def __init__(self, base_url: str, proxy: Optional[str] = None, token: Optional[str] = None):
        self.token = token
        if "@" in base_url:
            token_from_url, real_base_url = base_url.split("@", 1)
            self.base_url = real_base_url.rstrip('/')
            self.token = self.token or token_from_url
            self._headers = {}
        else:
            self.base_url = base_url.rstrip('/')
            self._headers = {}
        
        self.client_id = str(uuid.uuid4())
        ws_protocol = "ws" if self.base_url.startswith("http:") else "wss"
        host = self.base_url.split("://")[1]
        ws_params = f"clientId={self.client_id}"
        if self.token:
            ws_params += f"&token={self.token}"
        self.ws_address = f"{ws_protocol}://{host}/ws?{ws_params}"
        
        proxies = {"http://": proxy, "https://": proxy} if proxy else None
        
        self._client = httpx.AsyncClient(
            proxies=proxies,
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
            headers=self._headers
        )

    async def __aenter__(self): return self
    async def __aexit__(self, exc_type, exc_val, exc_tb): await self.close()
    async def close(self): await self._client.aclose()
    
    def _get_http_url(self, endpoint: str) -> str:
        base = f"{self.base_url}{endpoint}"
        if self.token:
            separator = "&" if "?" in base else "?"
            base = f"{base}{separator}token={self.token}"
        return base
    
    def _get_data_by_selector(self, data: Any, selector: str) -> Any:
        parts = re.split(r'\.|\[(\d+)\]', selector)
        parts = [p for p in parts if p]
        
        current_data = data
        for part in parts:
            if current_data is None: return _SENTINEL
            if isinstance(current_data, list) and part.isdigit():
                try:
                    current_data = current_data[int(part)]
                except IndexError:
                    return _SENTINEL
            elif isinstance(current_data, dict):
                current_data = current_data.get(part, _SENTINEL)
                if current_data is _SENTINEL:
                    return _SENTINEL
            else:
                return _SENTINEL
        return current_data

    async def execute_workflow(self, workflow: ComfyWorkflow, output_dir: str = "outputs") -> Dict[str, Any]:
        wf_to_run = await self.load_and_prepare_workflow(workflow.workflow_json_path, workflow._replacements)
        prompt_id = await self.queue_prompt(wf_to_run)
        if not prompt_id: return {"error": "无法提交工作流到队列"}

        completed = await self.wait_for_prompt_completion(prompt_id)
        if not completed: return {"error": "工作流执行失败或超时"}

        history = await self.get_history(prompt_id)
        if not history: return {"error": "无法获取执行历史记录"}

        print(f"\n✅ 任务完成，开始收集所有节点的输出...")
        
        results = {}
        total_outputs_processed = 0

        for node_id, selectors in workflow._output_nodes.items():
            results[node_id] = {}
            async for item_result in self._get_outputs_for_node(history, node_id, selectors, output_dir):
                selector = item_result['selector']
                output = item_result['output']
                
                if selector in results[node_id]:
                    if not isinstance(results[node_id][selector], list):
                        results[node_id][selector] = [results[node_id][selector]]
                    results[node_id][selector].append(output)
                else:
                    results[node_id][selector] = output
                total_outputs_processed +=1

        if total_outputs_processed > 0:
            print(f"\n🎉🎉🎉 工作流成功完成! 共处理 {total_outputs_processed} 个输出项。")
        else:
            print("\n⚠️ 工作流已结束，但没有定义或处理任何输出。")
            
        return results

    async def _get_outputs_for_node(self, history: Dict[str, Any], target_node_id: str, selectors: List[str], output_dir: str) -> AsyncGenerator[Dict[str, Any], None]:
        node_outputs = history.get('outputs', {})
        
        print(f"正在获取节点 '{target_node_id}' 的输出...")

        if target_node_id not in node_outputs:
            for selector in selectors:
                yield {"selector": selector, "output": "非输出节点"}
            return
        
        node_output_data = node_outputs[target_node_id]

        for selector in selectors:
            if selector == "DEFAULT_DOWNLOAD":
                found_files = False
                for key, value in node_output_data.items():
                    if isinstance(value, list) and value and isinstance(value[0], dict) and 'filename' in value[0]:
                        found_files = True
                        print(f"  - 在节点 '{target_node_id}' 的 '{key}' 中找到文件列表，准备下载...")
                        for item in value:
                            file_path = await self._download_file(item, output_dir)
                            if file_path:
                                yield {"selector": selector, "output": file_path}
                            else:
                                yield {"selector": selector, "output": f"文件 '{item.get('filename')}' 下载失败"}
                if not found_files:
                    yield {"selector": selector, "output": "在节点中未找到可下载的文件列表"}
                continue

            selected_data = self._get_data_by_selector(node_output_data, selector)
            
            if selected_data is _SENTINEL:
                yield {"selector": selector, "output": "指定的JSON路径不存在"}
                continue

            data_to_process = selected_data if isinstance(selected_data, list) else [selected_data]

            for item in data_to_process:
                if isinstance(item, dict) and 'filename' in item:
                    file_path = await self._download_file(item, output_dir)
                    if file_path:
                        yield {"selector": selector, "output": file_path}
                    else:
                        yield {"selector": selector, "output": f"文件 '{item.get('filename')}' 下载失败"}
                else:
                    yield {"selector": selector, "output": str(item)}

    async def wait_for_prompt_completion(self, prompt_id: str, timeout: Optional[int] = None) -> bool:
        effective_timeout = timeout if timeout is not None else WORKFLOW_EXECUTION_TIMEOUT
        print(f"开始通过 WebSocket 监听任务 {prompt_id} 的执行状态 (总超时: {effective_timeout}s)...")

        attempts = 0
        while attempts < DOWNLOAD_RETRY_ATTEMPTS:
            try:
                async with websockets.connect(
                    self.ws_address, 
                    ping_interval=WS_PING_INTERVAL, 
                    ping_timeout=WS_PING_TIMEOUT, 
                    open_timeout=WS_OPEN_TIMEOUT
                ) as ws:
                    print("✅ WebSocket 连接成功建立。")
                    attempts = 0

                    while True:
                        try:
                            message_data = await asyncio.wait_for(ws.recv(), timeout=effective_timeout)
                            if isinstance(message_data, str):
                                message = json.loads(message_data)
                                if message.get('type') == 'progress':
                                    data = message.get('data', {})
                                    print(f"  - 进度更新: 节点 {data.get('node', 'N/A')} - 步数 {data.get('value', 0)}/{data.get('max', 1)}")
                                if message.get('type') == 'execution_success' and message.get('data', {}).get('prompt_id') == prompt_id:
                                    print("✅ 任务执行流程结束。")
                                    return True
                                if message.get('type') == 'execution_interrupted':
                                    data = message.get('data', {})
                                    node_id = data.get('node_id', 'N/A')
                                    node_type = data.get('node_type', 'N/A')
                                    print(f"❌ 任务执行被中断: 节点 {node_id} ({node_type})")
                                    return False
                                if message.get('type') == 'status':
                                    exec_info = message.get('data', {}).get('status', {}).get('exec_info', {})
                                    if exec_info.get('queue_remaining') == 0:
                                        print(f"队列已空（queue_remaining:0），主动查历史确认任务 {prompt_id} 状态...")
                                        history = await self.get_history(prompt_id)
                                        status_messages = history.get('status', {}).get('messages', [])
                                        for msg in status_messages:
                                            if isinstance(msg, list) and len(msg) > 1 and msg[0] == 'execution_success':
                                                print("历史记录显示任务已成功！")
                                                return True
                                            if isinstance(msg, list) and len(msg) > 1 and msg[0] == 'execution_interrupted':
                                                print("历史记录显示任务被中断！")
                                                return False
                                        print("队列空但任务未成功，继续监听...")
                        except asyncio.TimeoutError:
                            print(f"\n监听消息超时 ({effective_timeout}秒)，主动查历史确认任务 {prompt_id} 状态...")
                            history = await self.get_history(prompt_id)
                            status_messages = history.get('status', {}).get('messages', [])
                            for msg in status_messages:
                                if isinstance(msg, list) and len(msg) > 1 and msg[0] == 'execution_success':
                                    print("超时后确认：历史记录显示任务已成功！")
                                    return True
                                if isinstance(msg, list) and len(msg) > 1 and msg[0] == 'execution_interrupted':
                                    print("超时后确认：历史记录显示任务被中断！")
                                    return False
                            print(f"超时且任务未成功，返回失败。")
                            return False
            
            except Exception as e:
                attempts += 1
                print(f"❌ 监听 WebSocket 时发生错误 (第 {attempts}/{DOWNLOAD_RETRY_ATTEMPTS} 次尝试): {e}")
                if attempts < DOWNLOAD_RETRY_ATTEMPTS:
                    print(f"   -> 将在 {DOWNLOAD_RETRY_DELAY} 秒后重连...")
                    await asyncio.sleep(DOWNLOAD_RETRY_DELAY)
                else:
                    print(f"   -> ❌ 所有连续的重连尝试均失败。")
        
        return False
        
    async def _download_file(self, file_data: Dict[str, str], target_dir: str) -> Optional[str]:
        filename, subfolder, file_type = file_data.get('filename'), file_data.get('subfolder', ''), file_data.get('type')
        if not filename or not file_type: return None
        
        output_sub_dir = os.path.join(target_dir, file_type); os.makedirs(output_sub_dir, exist_ok=True)
        url = self._get_http_url("/view")
        params = {"filename": filename, "subfolder": subfolder, "type": file_type}
        
        for attempt in range(DOWNLOAD_RETRY_ATTEMPTS):
            try:
                async with self._client.stream("GET", url, params=params) as response:
                    response.raise_for_status()
                    output_path = os.path.join(output_sub_dir, filename)
                    async with aiofiles.open(output_path, 'wb') as f:
                        async for chunk in response.aiter_bytes():
                            await f.write(chunk)
                    
                    absolute_path = os.path.abspath(output_path)
                    return absolute_path.replace("\\", "/")

            except Exception as e:
                print(f"   -> ❌ 下载或保存 {filename} 时发生错误 (第 {attempt + 1}/{DOWNLOAD_RETRY_ATTEMPTS} 次尝试): {e}")
                if attempt < DOWNLOAD_RETRY_ATTEMPTS - 1:
                    print(f"   -> 将在 {DOWNLOAD_RETRY_DELAY} 秒后重试...")
                    await asyncio.sleep(DOWNLOAD_RETRY_DELAY)
                else:
                    print(f"   -> ❌ 所有重试均失败，放弃下载 {filename}。")

        return None

    async def upload_file(self, file_path: str, server_subfolder: str = "", overwrite: bool = True) -> Dict[str, Any]:
        if not os.path.exists(file_path): raise FileNotFoundError(f"文件未找到: {file_path}")
        print(f"准备上传文件: {os.path.basename(file_path)}...")
        filename = os.path.basename(file_path)
        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type is None: mime_type = 'application/octet-stream'
        payload = {'overwrite': str(overwrite).lower(), 'subfolder': server_subfolder}
        url = self._get_http_url("/upload/image")
        try:
            with open(file_path, 'rb') as f:
                files = {'image': (filename, f.read(), mime_type)}
                response = await self._client.post(url, files=files, data=payload)
                response.raise_for_status()
            result = response.json()
            print(f"✅ 文件上传成功. 服务器文件名: {result['name']}")
            return result
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            print(f"❌ 上传文件时发生网络或HTTP错误: {e}")
            if isinstance(e, httpx.HTTPStatusError): print(f"   - 服务器响应: {e.response.text}")
            raise
    
    @classmethod
    async def load_and_prepare_workflow(cls, workflow_path: str, replacements: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        print(f"正在加载工作流: {os.path.basename(workflow_path)}")
        if not os.path.exists(workflow_path): raise FileNotFoundError(f"工作流文件未找到: {workflow_path}")
        async with aiofiles.open(workflow_path, 'r', encoding='utf-8') as f: workflow = json.loads(await f.read())
        print("正在动态替换节点内容...")
        for node_id, inputs_to_replace in replacements.items():
            if node_id in workflow:
                for input_name, new_value in inputs_to_replace.items():
                    workflow[node_id]['inputs'][input_name] = new_value
                    print(f"   - 节点 '{node_id}' 的输入 '{input_name}' 已更新。")
        return workflow

    async def queue_prompt(self, prepared_workflow: Dict[str, Any]) -> str:
        print("正在将工作流提交到队列...")
        url = self._get_http_url("/prompt")
        payload = {"prompt": prepared_workflow, "client_id": self.client_id}
        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            prompt_id = response.json().get("prompt_id")
            if prompt_id:
                print(f"✅ 工作流提交成功. Prompt ID: {prompt_id}")
                return prompt_id
            else:
                print(f"❌ 提交工作流后未收到 prompt_id。服务器响应: {response.text}")
                return None
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            print(f"❌ 提交工作流时发生网络或HTTP错误: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"   - 服务器响应: {e.response.text}")
            return None
        except json.JSONDecodeError as e:
            print(f"❌ 解析服务器响应时发生JSON错误。这通常意味着服务器返回了一个错误页面而不是有效的JSON。")
            print(f"   - 原始响应内容: {response.text}")
            return None


    async def get_history(self, prompt_id: str) -> Dict[str, Any]:
        url = self._get_http_url(f"/history/{prompt_id}")
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.json().get(prompt_id, {})
        except Exception as e:
            print(f"❌ 获取历史记录时发生错误: {e}")
            return {}
            
    async def view_tasks(self) -> Dict[str, List[Dict]]:
        try:
            queue_res = await self._client.get(self._get_http_url("/queue"))
            queue_res.raise_for_status()
            queue_data = queue_res.json()
            running_tasks = [{"prompt_id": item[1]} for item in queue_data.get('queue_running', []) if isinstance(item, list) and len(item) > 1]
            queued_tasks = [{"prompt_id": item[1]} for item in queue_data.get('queue_pending', []) if isinstance(item, list) and len(item) > 1]
            history_res = await self._client.get(self._get_http_url("/history"))
            history_res.raise_for_status()
            history_data = history_res.json()
            sortable_history = []
            for prompt_id, result in history_data.items():
                completion_timestamp = 0
                messages = result.get("status", {}).get("messages", [])
                for msg in messages:
                    if isinstance(msg, list) and len(msg) > 1 and msg[0] == 'execution_success':
                        if isinstance(msg[1], dict) and 'timestamp' in msg[1]:
                            completion_timestamp = msg[1]['timestamp']
                            break
                sortable_history.append({"prompt_id": prompt_id, "result": result, "timestamp": completion_timestamp})
            sortable_history.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            completed_tasks = []
            running_and_queued_ids = {t['prompt_id'] for t in running_tasks} | {t['prompt_id'] for t in queued_tasks}
            for item in sortable_history:
                prompt_id = item['prompt_id']
                if prompt_id in running_and_queued_ids: continue
                outputs_preview = "无输出"
                if 'outputs' in item['result']:
                    for node_output in item['result']['outputs'].values():
                        if 'images' in node_output and node_output['images']:
                           outputs_preview = node_output['images'][0]['filename']
                           break
                completed_tasks.append({"prompt_id": prompt_id, "outputs_preview": outputs_preview})
            return {"running": running_tasks, "queued": queued_tasks, "completed": completed_tasks}
        except Exception as e:
            print(f"❌ 获取任务列表时出错: {e}")
            return {"running": [], "queued": [], "completed": []}

    async def interrupt_running_task(self) -> bool:
        print("正尝试中断当前任务...")
        try:
            response = await self._client.post(self._get_http_url("/interrupt"))
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"❌ 发送中断请求失败: {e}")
            return False

    async def delete_queued_tasks(self, prompt_ids: List[str]) -> bool:
        print(f"正尝试从队列中删除任务: {prompt_ids}...")
        try:
            response = await self._client.post(self._get_http_url("/queue"), json={"delete": prompt_ids})
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"❌ 发送删除请求失败: {e}")
            return False