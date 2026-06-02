"""
Live2D 网页版桌宠（/live2dchat）的进程内共享状态。

【为什么放在 framework_common 而不是 run/live2d】
WebUI 的 Flask 服务在 main.py 的子线程里运行，导入 web/server_new.py 时就调用
register_live2d_webchat(app) 注册了路由，路由闭包绑定的是此模块的 get_state。
而插件管理器在加载 run/live2d 插件时，会**清空并重新导入所有 run.live2d.* 模块**
（见 PluginAwareExtendBot._clear_plugin_modules_from_cache）。若状态模块放在
run.live2d 下，就会出现“路由读的是旧实例、插件写的是新实例”的两份状态，导致页面
永远拿不到运行时配置（表现为‘未配置模型路径’、口令门不触发）。

framework_common.* 不在插件清理范围内，是稳定单例 —— 路由与插件都引用同一份 _STATE。
"""

# runtime：去密钥前的完整运行时配置（含 expression/tts 端点，供服务端代理用）
# model_dir：已解析的模型目录绝对路径（/live2dchat/model 从这里发文件）
# model_entry：模型入口文件名（增强后的 *.eridanus.model3.json 或原始 *.model3.json）
# password：访问 /live2dchat 的口令（webui_password）；空串表示不鉴权
# enabled：webui_enable 是否开启
_STATE = {"runtime": None, "model_dir": None, "model_entry": None, "password": "", "enabled": False}


def set_runtime(runtime, model_dir, model_entry, password=""):
    """由 run/live2d/main.py 在 webui_enable 时调用，交接运行时配置给网页蓝图。"""
    _STATE.update(
        runtime=runtime,
        model_dir=model_dir,
        model_entry=model_entry,
        password=password or "",
        enabled=True,
    )


def get_state():
    """供 run/live2d/webchat.py 的路由读取当前运行时状态。"""
    return _STATE
