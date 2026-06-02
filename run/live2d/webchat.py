"""
Live2D 网页版桌宠（localhost:5007/live2dchat）。

把桌宠模式整套能力搬进浏览器：复用 run/live2d/desktop 下的 renderer.js + vendor + 模型，
连同样的 WebUI 集线器 /api/ws（与网页前端、Electron 桌宠共用后端与对话上下文）。

本模块只在 WebUI 的 Flask app 上注册若干路由（由 web/server_new.py 在导入时调用
register_live2d_webchat(app)）。真正的运行时配置由 run/live2d 插件在加载时通过
webchat_state.set_runtime() 交接过来；这里在请求时读取。

安全：5007 可能被公网访问。
- /live2dchat/config 只下发**去密钥**的配置；表情 LLM 与 TTS 都经服务端代理调用，
  api_key / api_base 始终留在服务端。
- 图片/文件复用 WebUI 现成的 /api/chat/file（@auth）。
"""

import functools
import os
import secrets

from flask import jsonify, request, send_from_directory, abort, Response, make_response

# 状态放在 framework_common（稳定单例）：插件管理器会清空/重导 run.live2d.* 模块，
# 若状态在插件包内会与路由闭包绑定的实例分裂，导致页面拿不到运行时配置。
from framework_common.framework_util.live2d_webchat_state import get_state

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))           # run/live2d
DESKTOP_DIR = os.path.join(PLUGIN_DIR, "desktop")

# 表情判定 / TTS 代理的超时（秒）
_LLM_TIMEOUT = 6.0
_TTS_TIMEOUT = 60.0

# 通过口令校验后签发的访问令牌（内存集合，重启即失效）
_TOKENS = set()
_COOKIE = "live2d_token"


def _require_token(func):
    """口令门：webui_password 非空时，数据路由需带有效 live2d_token cookie。

    页面本身（/live2dchat）与静态资源不鉴权——页面会先探测 /config，401 则弹口令框。
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        pwd = (get_state().get("password") or "").strip()
        if not pwd:
            return func(*args, **kwargs)  # 未设口令 = 开放
        token = request.cookies.get(_COOKIE)
        if token and token in _TOKENS:
            return func(*args, **kwargs)
        return jsonify({"error": "Unauthorized"}), 401
    return wrapper


def register_live2d_webchat(app):
    """在 WebUI 的 Flask app 上注册 /live2dchat 相关路由。"""

    @app.route("/live2dchat/auth", methods=["POST"])
    def live2dchat_auth():
        pwd = (get_state().get("password") or "").strip()
        if not pwd:
            return jsonify({"ok": True})  # 未设口令，直接放行
        data = request.get_json(silent=True) or {}
        if str(data.get("password") or "") != pwd:
            return jsonify({"error": "密码错误"}), 401
        token = secrets.token_hex(16)
        _TOKENS.add(token)
        resp = make_response(jsonify({"ok": True}))
        resp.set_cookie(_COOKIE, token, httponly=True, samesite="Lax")
        return resp

    @app.route("/live2dchat")
    def live2dchat_index():
        return send_from_directory(DESKTOP_DIR, "webchat.html")

    @app.route("/live2dchat/static/<path:p>")
    def live2dchat_static(p):
        # 发 vendor/*.js、renderer.js 等；send_from_directory 自带防路径穿越
        return send_from_directory(DESKTOP_DIR, p)

    @app.route("/live2dchat/asset/<path:p>")
    def live2dchat_asset(p):
        # 发插件目录下的页面素材（背景图 bg.jpg 等）；非机密、不鉴权
        return send_from_directory(PLUGIN_DIR, p)

    @app.route("/live2dchat/config")
    @_require_token
    def live2dchat_config():
        st = get_state()
        rt = st.get("runtime")
        if not st.get("enabled") or not rt:
            return jsonify({"error": "live2d webui_enable 未开启"}), 503
        expr = rt.get("expression", {}) or {}
        tts = rt.get("tts", {}) or {}
        # 去密钥：emotions/scenes/复位延时下发给前端做本地变脸；base_url/api_key 不下发
        return jsonify({
            "host_mode": "web",
            "model_url": "/live2dchat/model/" + (st.get("model_entry") or ""),
            "window": rt.get("window", {}),
            "chat": rt.get("chat", {"enable": True}),
            "lip_sync_parameter_ids": rt.get("lip_sync_parameter_ids", ["ParamMouthOpenY"]),
            "expression": {
                "enable": expr.get("enable", True),
                "emotions": expr.get("emotions", {}),
                "scenes": expr.get("scenes", {}),
                "reset_delay_ms": expr.get("reset_delay_ms", 6000),
                # 标记服务端是否具备 LLM 端点：有则前端走 /live2dchat/llm，无则走关键词兜底
                "llm": bool(expr.get("base_url")),
            },
            "tts": {"enable": bool(tts.get("enable") and tts.get("api_base"))},
            "expr_names": rt.get("expr_names", []),
            "motion_names": rt.get("motion_names", []),
        })

    @app.route("/live2dchat/model/<path:p>")
    def live2dchat_model(p):
        # 不鉴权：与桌宠一致（模型文件非机密），且确保 pixi 加载贴图/动作时不受 cookie
        # 转发差异影响。页面已在口令门之后才加载渲染端，/config 与代理仍鉴权。
        st = get_state()
        model_dir = st.get("model_dir")
        if not model_dir or not os.path.isdir(model_dir):
            abort(404)
        return send_from_directory(model_dir, p)

    @app.route("/live2dchat/llm", methods=["POST"])
    @_require_token
    def live2dchat_llm():
        """表情判定代理：前端只传 prompt，服务端注入 base_url/api_key 调 LLM，回完成 JSON。"""
        st = get_state()
        rt = st.get("runtime") or {}
        expr = rt.get("expression", {}) or {}
        base = (expr.get("base_url") or "").strip()
        if not base:
            return jsonify({"error": "no llm endpoint"}), 503
        data = request.get_json(silent=True) or {}
        prompt = str(data.get("prompt") or "").strip()
        if not prompt:
            return jsonify({"error": "empty prompt"}), 400
        headers = {"Content-Type": "application/json"}
        if expr.get("api_key"):
            headers["Authorization"] = "Bearer " + expr["api_key"]
        body = {
            "model": expr.get("model") or "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 60,
            "stream": False,
        }
        try:
            import httpx
            r = httpx.post(base.rstrip("/") + "/chat/completions", json=body, headers=headers, timeout=_LLM_TIMEOUT)
            return Response(r.content, status=r.status_code, content_type="application/json")
        except Exception as e:
            return jsonify({"error": str(e)}), 502

    @app.route("/live2dchat/tts", methods=["POST"])
    @_require_token
    def live2dchat_tts():
        """语音代理：前端只传 text，服务端按 tts 配置拼 GPT-SoVITS 载荷调用，回 wav 字节。"""
        st = get_state()
        rt = st.get("runtime") or {}
        tts = rt.get("tts", {}) or {}
        api_base = (tts.get("api_base") or "").strip()
        if not tts.get("enable") or not api_base:
            return jsonify({"error": "tts disabled"}), 503
        data = request.get_json(silent=True) or {}
        text = str(data.get("text") or "").strip()
        if not text:
            return jsonify({"error": "empty text"}), 400
        # 载荷与 renderer.js synthesizeTTS / run/tts_v2 对齐
        payload = {
            "text": text,
            "text_lang": tts.get("target_lang", "zh"),
            "ref_audio_path": tts.get("ref_audio_path"),
            "prompt_text": tts.get("ref_text"),
            "prompt_lang": tts.get("ref_lang", "zh"),
            "top_k": tts.get("top_k"),
            "top_p": tts.get("top_p"),
            "temperature": tts.get("temperature"),
            "text_split_method": tts.get("text_split_method", "cut5"),
            "batch_size": tts.get("batch_size"),
            "speed_factor": tts.get("speed_factor"),
            "streaming_mode": tts.get("streaming_mode"),
            "seed": tts.get("seed"),
            "fragment_interval": 0.32,
            "media_type": "wav",
            "repetition_penalty": tts.get("repetition_penalty", 1.35),
        }
        try:
            import httpx
            r = httpx.post(api_base.rstrip("/") + "/tts", json=payload, timeout=_TTS_TIMEOUT)
            if r.status_code != 200:
                return jsonify({"error": "tts upstream " + str(r.status_code)}), 502
            return Response(r.content, status=200, content_type="audio/wav")
        except Exception as e:
            return jsonify({"error": str(e)}), 502
