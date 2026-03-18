import httpx
import json
import re
import asyncio
import uuid
from typing import AsyncGenerator, Dict, List, Optional, Union, Callable

from openai import AsyncOpenAI
import logging

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  工具调用块的定界符（模型输出中的标记）
# ─────────────────────────────────────────────────────────────
_TC_BEGIN = "@@TOOL_CALL_BEGIN@@"
_TC_END   = "@@TOOL_CALL_END@@"

# 匹配一个或多个工具调用块
_TC_PATTERN = re.compile(
    rf"{re.escape(_TC_BEGIN)}\s*(.*?)\s*{re.escape(_TC_END)}",
    re.DOTALL,
)


def _build_tool_system_prompt(tool_declarations: List[Dict]) -> str:
    """将工具声明序列化为注入 system prompt 的说明文字。"""
    tool_json = json.dumps(tool_declarations, ensure_ascii=False, indent=2)
    return f"""## 核心设定：外部工具调用系统（绝密执行协议）

你被赋予了调用外部真实系统（工具）的能力。虽然你在扮演特定的角色（如可爱的猫娘），但**当用户的要求需要真实执行（如画图、查询、搜索）时，你绝对不能只用语言“假装”执行，必须精确输出工具调用代码块！**

### 🚨 绝对禁止的错误模式（你必须引以为戒）
你之前经常犯以下错误，现在**严禁再犯**：
❌ **错误示范（只演戏不调用）**：
“喵呜～这就给主人画图！*咻咻咻真正的text2img启动*！画好啦，你喜欢吗？”
（**严重错误**：光用嘴说，完全没有输出 `{_TC_BEGIN}` 代码块，系统根本无法为你画图！）
❌ **错误示范（假装已经拿到结果）**：
“我已经为你查到了，今天的番剧有...”
（**严重错误**：没有真正调用工具，直接靠内部过时知识瞎编！）

### ✅ 正确的调用工作流与格式（你必须严格模仿）

当你判断需要调用工具（例如需要画图）时，你可以先用符合人设的语气说一两句简短的过渡语，然后**必须紧接着**输出严格的 JSON 代码块，并且在输出完 `{_TC_END}` 后**立刻闭嘴，停止输出任何文字**！

【完美的画图调用范例】
管理员大人想看人家自己呀？好害羞呢，这就给你画一张最可爱的Erina喵～✨
{_TC_BEGIN}
{{
  "name": "call_text2img",
  "arguments": {{
    "prompt": "1girl, solo, light purple-light blue mixed eyes, bangs, blush, grey hair, gradient hair, blue hair, (Rella:1.2)"
  }}
}}
{_TC_END}

**注意格式细节：**
1. `{_TC_BEGIN}` 和 `{_TC_END}` 必须独占一行。
2. `{_TC_BEGIN}` 内部必须是纯净的 JSON，绝对不能有 ````json` 等多余的 Markdown 标记！
3. 输出完 `{_TC_END}` 后，**不要再说任何话**（不要问用户喜不喜欢，要等系统返回图片后再问）！

---

### 🛠️ 当前【可用工具】列表

{tool_json}

---
**系统最后警告**：如果你再用“我已经画好了”、“魔法启动中”来糊弄用户而不输出代码块，将受到严重惩罚！一旦需要使用工具，请立刻按照上述【完美范例】输出 `{_TC_BEGIN}` 块！"""


def _parse_tool_calls(text: str):
    """
    从模型的文本回复中提取工具调用，返回 (clean_text, tool_calls)。
    clean_text: 去掉工具调用块后的正文。
    tool_calls: list of {"id": str, "name": str, "arguments": dict}
    """
    tool_calls = []
    for m in _TC_PATTERN.finditer(text):
        raw = m.group(1).strip()
        try:
            obj = json.loads(raw)
            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:12]}",
                "name": obj.get("name", ""),
                "arguments": obj.get("arguments", {}),
            })
            r={
                "id": f"call_{uuid.uuid4().hex[:12]}",
                "name": obj.get("name", ""),
                "arguments": obj.get("arguments", {}),
            }
            logger.info(f"增加调用工具块：{r}")
        except json.JSONDecodeError:
            logger.warning(f"[Eridanus] 无法解析工具调用块: {raw!r}")

    # 去掉所有工具调用块（及其前面可能多余的空行）
    clean = _TC_PATTERN.sub("", text).rstrip()
    return clean, tool_calls


class EridanusModel:
    """
    与 OpenAIAPI 接口完全兼容的对话类。
    针对不支持原生 function calling 的自定义接口，
    通过 system prompt 引导模型以文本形式输出工具调用，
    由客户端解析后实际执行，再将结果追加上下文并续接。
    """

    def __init__(
        self,
        apikey: str,
        baseurl: str = "https://f k/v1",
        model: str = "grok-3",
        proxies: Optional[Dict[str, str]] = None,
        max_tool_rounds: int = 6,          # 最多连续工具调用轮次，防止死循环
    ):
        self.apikey = apikey
        self.baseurl = baseurl.rstrip("/")
        self.model = model
        self.max_tool_rounds = max_tool_rounds
        self.client = AsyncOpenAI(
            api_key=apikey,
            base_url=baseurl,
            http_client=httpx.AsyncClient(proxies=proxies, timeout=60.0) if proxies else None,
        )

    # ──────────────────────────────────────────────
    #  内部工具执行
    # ──────────────────────────────────────────────
    async def _execute_tool(
        self,
        tool_call: Dict,                        # {"id", "name", "arguments"}
        tools: Dict[str, Callable],
        tool_fixed_params: Optional[Dict[str, Dict]] = None,
    ) -> str:
        name = tool_call["name"]
        args = tool_call["arguments"]
        tc_id = tool_call["id"]

        func = tools.get(name)
        if not func:
            result = {"error": f"未找到工具 {name}"}
            logger.warning(f"[Eridanus] 未找到工具: {name}")
        else:
            fixed = {}
            if tool_fixed_params:
                fixed = tool_fixed_params.get(name, tool_fixed_params.get("all", {}))
            combined = {**fixed, **args}
            logger.info(f"[Eridanus Tool] {name} | 参数: {combined}")
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(**combined)
                else:
                    result = await asyncio.to_thread(func, **combined)
            except Exception as e:
                result = {"error": str(e)}
                logger.error(f"[Eridanus] 工具 {name} 执行失败: {e}")

        return json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)

    # ──────────────────────────────────────────────
    #  构造给 API 的 messages（注入工具 system prompt）
    # ──────────────────────────────────────────────
    @staticmethod
    def _build_api_messages(
        messages: List[Dict],
        tool_system_extra: Optional[str],
    ) -> List[Dict]:
        """
        将内部 messages 转换为 OpenAI chat 格式。
        若有工具说明，则合并进 system 消息（已有则追加，没有则插入）。
        """
        api = []
        system_injected = False

        for msg in messages:
            role = msg["role"]
            if role == "model":
                role = "assistant"

            content = msg.get("content", "")

            # 将 content 统一转为纯文本字符串
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                parts = []
                for p in content:
                    if isinstance(p, dict) and "text" in p:
                        parts.append(p["text"])
                text = "\n".join(parts)
            else:
                text = str(content)

            # 在第一个 system 消息末尾注入工具说明
            #if role == "system" and tool_system_extra and not system_injected:
                #text = text + "\n\n" + tool_system_extra if text.strip() else tool_system_extra
                #system_injected = True

            api.append({"role": role, "content": text})

        # 若没有 system 消息，则在最前面插入
        #if tool_system_extra and not system_injected:
        if tool_system_extra:
            api.insert(-3,{"role": "user", "content": tool_system_extra})
            api.insert(-2, {"role": "assistant", "content": "好的，我会在接下来的对话中，自主判断并调用函数"})

        return api

    # ──────────────────────────────────────────────
    #  单次 API 请求（非流式），返回完整文本
    # ──────────────────────────────────────────────
    async def _raw_completion(self, api_messages: List[Dict], params: Dict) -> str:
        resp = await self.client.chat.completions.create(
            **{**params, "messages": api_messages, "stream": False}
        )
        if not resp.choices:
            return ""
        return resp.choices[0].message.content or ""

    # ──────────────────────────────────────────────
    #  单次 API 请求（流式），yield 文本 chunk，最终返回完整文本
    # ──────────────────────────────────────────────
    async def _raw_stream(self, api_messages: List[Dict], params: Dict) -> AsyncGenerator[str, None]:
        """生成器：流式 yield chunk，同时在内部拼接完整文本后通过 StopAsyncIteration 的 value 返回。
        由于 Python 生成器不能同时 return value，我们用一个 list 收集完整文本供调用方读取。"""
        async for chunk in await self.client.chat.completions.create(
            **{**params, "messages": api_messages, "stream": True}
        ):
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    # ──────────────────────────────────────────────
    #  构造基础请求参数（不含 messages/stream）
    # ──────────────────────────────────────────────
    def _base_params(
        self,
        max_output_tokens, topp, temperature,
        presence_penalty, frequency_penalty,
        stop_sequences, response_format,
        reasoning_effort, seed,
    ) -> Dict:
        p: Dict = {"model": self.model}
        if max_output_tokens  is not None: p["max_tokens"]        = max_output_tokens
        if topp               is not None: p["top_p"]             = topp
        if temperature        is not None: p["temperature"]       = temperature
        if stop_sequences     is not None: p["stop"]              = stop_sequences
        if presence_penalty   is not None: p["presence_penalty"]  = presence_penalty
        if frequency_penalty  is not None: p["frequency_penalty"] = frequency_penalty
        if seed               is not None: p["seed"]              = seed
        if response_format                 : p["response_format"]  = response_format
        if reasoning_effort   is not None: p["reasoning_effort"]  = reasoning_effort
        return p

    # ──────────────────────────────────────────────
    #  将工具调用结果追加到 messages（内部格式 + api 格式）
    # ──────────────────────────────────────────────
    def _append_tool_round(
        self,
        messages: List[Dict],
        api_messages: List[Dict],
        assistant_text: str,         # 本轮模型的正文（已去掉工具块）
        tool_calls: List[Dict],      # 解析出的工具调用
        tool_results: List[str],     # 对应的执行结果
        tool_system_extra: str,
    ):
        # 1. 把模型本轮回复（含工具调用标记的原始文本）存入 messages
        #    用内部格式表示
        tc_block = "\n".join(
            f"{_TC_BEGIN}\n{json.dumps({'name': tc['name'], 'arguments': tc['arguments']}, ensure_ascii=False)}\n{_TC_END}"
            for tc in tool_calls
        )
        raw_assistant_text = (assistant_text + "\n" + tc_block).strip()

        messages.append({
            "role": "assistant",
            "content": [{"type": "text", "text": raw_assistant_text}],
        })
        api_messages.append({"role": "assistant", "content": raw_assistant_text})

        # 2. 把工具结果以 user 身份追加（模拟 tool result，兼容无 tool role 的接口）
        result_text_parts = []
        for tc, res in zip(tool_calls, tool_results):
            result_text_parts.append(
                f'[工具调用结果] {tc["name"]}（call_id={tc["id"]}）:\n{res}'
            )
        result_text = "\n\n".join(result_text_parts)

        messages.append({
            "role": "user",
            "content": [{"type": "text", "text": result_text}],
        })
        api_messages.append({"role": "user", "content": result_text})

    # ──────────────────────────────────────────────
    #  主入口：chat
    # ──────────────────────────────────────────────
    async def chat(
        self,
        messages: Union[str, List[Dict]],
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
        # 以下两个参数保留签名兼容性，但在 Eridanus 中忽略（无原生 logprobs 支持）
        response_logprobs: Optional[bool] = None,
        logprobs: Optional[int] = None,
        retries: int = 3,
        on_clear_context: Optional[Callable] = None,
    ) -> AsyncGenerator[Union[str, Dict], None]:
        # ── 规范化 messages ──
        if isinstance(messages, str):
            messages = [{"role": "user", "content": [{"type": "text", "text": messages}]}]

        # ── 注入 system_instruction ──
        if system_instruction:
            for i, m in enumerate(messages):
                if m.get("role") == "system":
                    messages[i] = {"role": "system", "content": [{"type": "text", "text": system_instruction}]}
                    break
            else:
                messages.insert(0, {"role": "system", "content": [{"type": "text", "text": system_instruction}]})

        # ── 构造工具 system prompt（若有工具）──
        tool_system_extra: Optional[str] = None
        if tools and tool_declarations:
            # 只保留 tools 字典中实际存在的声明
            valid_decls = [d for d in tool_declarations if d.get("name") in tools]
            if valid_decls:
                tool_system_extra = _build_tool_system_prompt(valid_decls)
        elif tools:
            # 没有显式声明则自动推断（只取函数名和 docstring）
            auto_decls = []
            fixed_all = (tool_fixed_params or {}).get("all", {})
            for name, func in tools.items():
                params_props = {}
                params_required = []
                if hasattr(func, "__code__"):
                    dynamic = [
                        v for v in func.__code__.co_varnames[: func.__code__.co_argcount]
                        if v not in fixed_all
                    ]
                    params_props = {v: {"type": "string", "description": v} for v in dynamic}
                    params_required = dynamic
                auto_decls.append({
                    "name": name,
                    "description": getattr(func, "__doc__", f"调用 {name}") or f"调用 {name}",
                    "parameters": {
                        "type": "object",
                        "properties": params_props,
                        "required": params_required,
                    },
                })
            if auto_decls:
                tool_system_extra = _build_tool_system_prompt(auto_decls)

        base_params = self._base_params(
            max_output_tokens, topp, temperature,
            presence_penalty, frequency_penalty,
            stop_sequences, response_format,
            reasoning_effort, seed,
        )

        # ── 构造初始 api_messages ──
        api_messages = self._build_api_messages(messages, tool_system_extra)
        print(api_messages)
        # ════════════════════════════════════════
        #  非流式
        # ════════════════════════════════════════
        if not stream:
            for attempt in range(retries):
                try:
                    full_text = await self._raw_completion(api_messages, base_params)
                except Exception as e:
                    logger.error(f"[Eridanus] 非流式请求失败 ({attempt+1}/{retries}): {e}")
                    if attempt == retries - 1:
                        yield f"[错误] 请求失败（{type(e).__name__}: {e}），已重试 {retries} 次"
                        return
                    await asyncio.sleep(2 ** attempt)
                    continue

                if not full_text:
                    logger.warning(f"[Eridanus] 空响应 ({attempt+1}/{retries})")
                    if attempt == retries - 1:
                        yield "[错误] AI 响应内容为空，已重试多次。"
                        return
                    await asyncio.sleep(2 ** attempt)
                    continue

                # 解析工具调用
                clean_text, tool_calls = _parse_tool_calls(full_text)

                if not tool_calls or not tools:
                    # 无工具调用 → 直接返回
                    messages.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": clean_text}],
                    })
                    yield clean_text
                    return

                # 有工具调用 → 先把正文 yield 出去
                if clean_text:
                    yield clean_text

                # 执行所有工具（并发）
                for _round in range(self.max_tool_rounds):
                    results = await asyncio.gather(*[
                        self._execute_tool(tc, tools, tool_fixed_params)
                        for tc in tool_calls
                    ])

                    self._append_tool_round(
                        messages, api_messages,
                        clean_text, tool_calls, list(results),
                        tool_system_extra or "",
                    )
                    # ======= 【新增：终端动作类工具拦截】 =======
                    # 如果本轮调用的所有工具都是纯执行动作（不需要AI看结果再废话的），直接结束本轮回复
                    ACTION_TOOLS = {"call_send_mface", "call_user_data_sign", "call_tts"}
                    if all(tc["name"] in ACTION_TOOLS for tc in tool_calls):
                        return
                    # ============================================

                    # 续接
                    try:
                        followup = await self._raw_completion(api_messages, base_params)
                    except Exception as e:
                        yield f"[错误] 工具续接请求失败: {e}"
                        return

                    clean_text, tool_calls = _parse_tool_calls(followup)

                    if clean_text:
                        yield clean_text

                    if not tool_calls or not tools:
                        messages.append({
                            "role": "assistant",
                            "content": [{"type": "text", "text": clean_text}],
                        })
                        return

                # 超过最大轮次
                yield "\n[提示] 已达到最大工具调用轮次限制。"
                return

        # ════════════════════════════════════════
        #  流式
        # ════════════════════════════════════════
        else:
            for _round in range(self.max_tool_rounds + 1):
                buffer = ""
                # 流式输出缓冲区：遇到工具块开始标记前先 yield，遇到后停止 yield 并缓冲
                pending = ""          # 尚未确认是否含工具块的末尾缓冲
                yielded_any = False

                try:
                    async for chunk in self._raw_stream(api_messages, base_params):
                        buffer += chunk
                        pending += chunk

                        # 只要 pending 中不包含工具块开始标记的任何前缀，就可以安全 yield
                        # 策略：若 pending 不含 _TC_BEGIN 的任何前缀，全部 yield
                        safe, pending = self._split_safe(pending)
                        if safe:
                            yield safe
                            yielded_any = True

                except Exception as e:
                    logger.error(f"[Eridanus] 流式请求失败: {e}")
                    yield f"\n[错误] 流式请求失败: {e}"
                    return

                # 流结束后，处理剩余 pending（可能含工具块）
                # pending 中可能有工具块，也可能只是普通文字
                clean_text, tool_calls = _parse_tool_calls(buffer)

                # 把 pending 中剩余的正文（去工具块后）yield 出去
                remaining_clean, _ = _parse_tool_calls(pending)
                if remaining_clean:
                    yield remaining_clean
                    yielded_any = True

                if not tool_calls or not tools:
                    messages.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": clean_text}],
                    })
                    return

                # 执行工具
                results = await asyncio.gather(*[
                    self._execute_tool(tc, tools, tool_fixed_params)
                    for tc in tool_calls
                ])

                self._append_tool_round(
                    messages, api_messages,
                    clean_text, tool_calls, list(results),
                    tool_system_extra or "",
                )
                # ======= 【新增：终端动作类工具拦截】 =======
                ACTION_TOOLS = {"call_send_mface"}
                if all(tc["name"] in ACTION_TOOLS for tc in tool_calls):
                    return
                # ===========================================
                # 下一轮续接（重置 buffer/pending）

            yield "\n[提示] 已达到最大工具调用轮次限制。"

    # ──────────────────────────────────────────────
    #  流式辅助：将 pending 拆分为"可安全 yield 的前缀"和"需继续观察的后缀"
    # ──────────────────────────────────────────────
    @staticmethod
    def _split_safe(text: str):
        """
        若 text 中不含 _TC_BEGIN 也不含其任何前缀，则全部安全。
        否则，找到最早可能是 _TC_BEGIN 前缀的位置，该位置之前的部分安全，之后继续缓冲。
        """
        marker = _TC_BEGIN
        # 检查 text 是否含完整 marker
        idx = text.find(marker)
        if idx != -1:
            # marker 完整出现，marker 前的部分安全
            return text[:idx], text[idx:]

        # 检查 text 末尾是否是 marker 的某个前缀（防止 marker 被拆成两个 chunk）
        for prefix_len in range(min(len(marker), len(text)), 0, -1):
            if text.endswith(marker[:prefix_len]):
                safe_end = len(text) - prefix_len
                return text[:safe_end], text[safe_end:]

        return text, ""

    async def __aenter__(self):
        return self

