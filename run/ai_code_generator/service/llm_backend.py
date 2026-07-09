"""
llm_backend.py —— ai_code_generator 的「端点无关」结构化生成后端。

按 ai_coder.yaml 的 endpoint 决定用谁生成：
  - endpoint.base_url 非空 & type==openai：直连 OpenAI 兼容 /chat/completions（json_schema→json_object→纯文本 三级回退）。
  - endpoint.base_url 非空 & type==gemini：复用 run/ai_llm 的 GeminiAPI，走专用端点。
  - endpoint.base_url 为空：回退到 ai_llm 的 schemaReplyCore（保持旧行为，用聊天插件的 gemini 端点 + 使用模型）。

这样代码生成的模型/端点与 ai 聊天插件解耦，用户可自选更强的代码模型；密钥只留在服务端。
"""

import json
import re

from framework_common.utils.system_logger import get_logger

logger = get_logger("ai_code_generator")

_TIMEOUT = 180.0


def _endpoint_cfg(cfg):
    try:
        return cfg.ai_code_generator.ai_coder.get("endpoint", {}) or {}
    except Exception:
        return {}


async def generate_structured(cfg, schema, prompt, user_id=None):
    """按配置端点生成结构化结果（dict）。失败返回 None。"""
    ep = _endpoint_cfg(cfg)
    base_url = str(ep.get("base_url") or "").strip()
    ep_type = str(ep.get("type") or "openai").strip().lower()
    api_key = str(ep.get("api_key") or "").strip()
    model = str(ep.get("model") or "").strip()

    if not base_url:
        # 回退旧路径：ai 聊天插件的 gemini 端点 + 「使用模型」
        from run.ai_llm.service.schemaReplyCore import schemaReplyCore
        model_set = None
        try:
            model_set = cfg.ai_code_generator.ai_coder.get("使用模型")
        except Exception:
            pass
        logger.info("[ai_code_generator] endpoint.base_url 为空，回退 schemaReplyCore")
        return await schemaReplyCore(
            config=cfg,
            schema=schema,
            user_message=prompt,
            user_id=int(f"{user_id}1024") if user_id else 1024,
            keep_history=True,
            model_set=model_set,
        )

    if ep_type == "gemini":
        logger.info(f"[ai_code_generator] 使用专用 gemini 端点: {base_url} model={model or 'gemini-2.5-pro'}")
        return await _gemini_call(base_url, api_key, model, schema, prompt)

    logger.info(f"[ai_code_generator] 使用专用 openai 兼容端点: {base_url} model={model or 'gpt-4o'}")
    return await _openai_call(base_url, api_key, model, schema, prompt)


async def _openai_call(base_url, api_key, model, schema, prompt):
    import httpx

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    messages = [
        {"role": "system", "content": "你是资深的 Python 机器人插件工程师。严格只输出满足要求的 JSON，不要任何解释或 markdown 包裹。"},
        {"role": "user", "content": prompt},
    ]
    mdl = model or "gpt-4o"

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        # 1) 首选严格 json_schema
        body = {
            "model": mdl,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "plugin_result", "schema": schema, "strict": False},
            },
        }
        r = await client.post(url, json=body, headers=headers)
        # 2) 端点不支持 json_schema -> json_object
        if r.status_code != 200:
            body = {"model": mdl, "messages": messages, "temperature": 0.2,
                    "response_format": {"type": "json_object"}}
            r = await client.post(url, json=body, headers=headers)
        # 3) 仍失败 -> 纯文本，靠 prompt 约束 + 事后解析
        if r.status_code != 200:
            body = {"model": mdl, "messages": messages, "temperature": 0.2}
            r = await client.post(url, json=body, headers=headers)
        if r.status_code != 200:
            logger.error(f"[ai_code_generator] openai 端点错误 {r.status_code}: {r.text[:500]}")
            return None
        data = r.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        logger.error(f"[ai_code_generator] 无法解析响应结构: {str(data)[:500]}")
        return None
    return _parse_json(content)


async def _gemini_call(base_url, api_key, model, schema, prompt):
    from run.ai_llm.clients.gemini_client import GeminiAPI

    api = GeminiAPI(apikey=api_key, baseurl=base_url, model=model or "gemini-2.5-pro", proxies=None)
    history = [{"role": "user", "parts": [{"text": prompt}]}]
    text = ""
    async for part in api.chat(history, stream=False, response_schema=schema):
        if isinstance(part, str):
            text += part
    return _parse_json(text)


def _parse_json(text):
    if isinstance(text, dict):
        return text
    s = str(text or "").strip()
    # 去掉 ```json ... ``` 包裹
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r"\{.*\}", s, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    logger.error(f"[ai_code_generator] JSON 解析失败，原文前 500 字: {s[:500]}")
    return None
