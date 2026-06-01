"""
Electron 桌宠子进程管理：定位 node/npm、首次按需安装依赖、拉起 / 关闭渲染进程。
"""

import json
import os
import shutil
import subprocess
import sys
import threading

from framework_common.utils.system_logger import get_logger

logger = get_logger("Live2DProcess")

# run/live2d/service/process_manager.py -> 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DESKTOP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desktop")
MODELS_DIR = os.path.join(DESKTOP_DIR, "models")
IS_WIN = sys.platform == "win32"


def _which(*names):
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def _to_file_url(abs_path):
    """把绝对路径转成渲染层可加载的 file:// URL（统一正斜杠）。"""
    p = os.path.abspath(abs_path).replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p  # Windows 盘符 D:/... -> /D:/...
    return "file://" + p


def resolve_model_dir(config):
    """按 model_path（自定义文件夹）优先、否则内置 model，返回模型目录绝对路径。"""
    model_path = (config.get("model_path") or "").strip()
    if model_path:
        base = model_path if os.path.isabs(model_path) else os.path.join(PROJECT_ROOT, model_path)
        return os.path.abspath(base)
    return os.path.join(MODELS_DIR, config.get("model", "hiyori_pro_en"))


AUG_SUFFIX = ".eridanus.model3.json"  # 我们生成的增强模型文件后缀


def find_model_entry_in(base):
    """在目录下递归找第一个原始 *.model3.json（排除我们生成的增强文件），返回绝对路径。"""
    if not os.path.isdir(base):
        return None
    for root, _dirs, files in os.walk(base):
        for f in files:
            if f.endswith(".model3.json") and not f.endswith(AUG_SUFFIX):
                return os.path.join(root, f)
    return None


def prepare_model(base):
    """
    准备模型：自动发现同目录下散落的 *.exp3.json / *.motion3.json，把它们补进
    model3.json 的 FileReferences（生成一个**非破坏性**的增强副本），使
    model.expression(name) / model.motion(group) 可用。

    返回 (model_url, expr_names, motion_names)；找不到模型返回 (None, [], [])。
    """
    orig = find_model_entry_in(base)
    if orig is None:
        return None, [], []
    model_dir = os.path.dirname(orig)
    try:
        with open(orig, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"读取 model3.json 失败：{e}")
        return _to_file_url(orig), [], []

    fr = data.setdefault("FileReferences", {})
    changed = False

    # 补充表情：目录下所有 *.exp3.json
    if not fr.get("Expressions"):
        exprs = []
        for fn in sorted(os.listdir(model_dir)):
            if fn.endswith(".exp3.json"):
                exprs.append({"Name": fn[: -len(".exp3.json")], "File": fn})
        if exprs:
            fr["Expressions"] = exprs
            changed = True

    # 补充动作：目录下所有 *.motion3.json，每个文件单独成组（组名=文件名）
    if not fr.get("Motions"):
        motions = {}
        for fn in sorted(os.listdir(model_dir)):
            if fn.endswith(".motion3.json"):
                motions[fn[: -len(".motion3.json")]] = [{"File": fn}]
        if motions:
            fr["Motions"] = motions
            changed = True

    expr_names = [e.get("Name") for e in fr.get("Expressions", []) if e.get("Name")]
    motion_names = list(fr.get("Motions", {}).keys())

    if not changed:
        # 原模型已自带表情/动作引用，直接用原文件
        return _to_file_url(orig), expr_names, motion_names

    # 写出增强副本（与原文件同目录，相对路径仍可解析）
    out = os.path.join(model_dir, os.path.basename(orig)[: -len(".model3.json")] + AUG_SUFFIX)
    try:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"写入增强 model3.json 失败：{e}，回退原文件")
        return _to_file_url(orig), expr_names, motion_names
    return _to_file_url(out), expr_names, motion_names


def resolve_model_url(config):
    """返回模型（增强后）*.model3.json 的 file:// URL。"""
    url, _exprs, _motions = prepare_model(resolve_model_dir(config))
    return url


def get_model_assets(config):
    """返回 (model_url, expr_names, motion_names)，供桌宠大脑告诉 AI 可用的表情/动作。"""
    return prepare_model(resolve_model_dir(config))


def find_model_entry(folder_or_path):
    """兼容旧接口：传内置文件夹名或路径，返回（增强后）*.model3.json 的 file:// URL。"""
    if os.path.isabs(folder_or_path) or os.sep in folder_or_path or "/" in folder_or_path:
        base = folder_or_path if os.path.isabs(folder_or_path) else os.path.join(PROJECT_ROOT, folder_or_path)
    else:
        base = os.path.join(MODELS_DIR, folder_or_path)
    url, _exprs, _motions = prepare_model(base)
    return url


class Live2DProcessManager:
    def __init__(self, config: dict, expression_endpoint: dict = None):
        self.config = config or {}
        # 已解析好的表情控制 LLM 端点 {enable, base_url, api_key, model}，写入 runtime_config 供渲染端用
        self.expression_endpoint = expression_endpoint or {"enable": True, "base_url": "", "api_key": "", "model": "gpt-4o-mini"}
        self.proc = None
        self._lock = threading.Lock()

    # ---------- 运行时配置 ----------

    def _write_runtime_config(self):
        model_url, expr_names, motion_names = get_model_assets(self.config)
        if model_url is None:
            logger.warning(f"未找到模型 *.model3.json：{resolve_model_dir(self.config)}")
        runtime = {
            "model_url": model_url,
            "webui": self.config.get("webui", {"host": "127.0.0.1", "port": 5007}),
            "window": self.config.get("window", {}),
            "chat": self.config.get("chat", {"enable": True}),
            "lip_sync_parameter_ids": self.config.get("lip_sync_parameter_ids", ["ParamMouthOpenY"]),
            # 表情/动作自动控制：渲染端收到文字回复后用快速 LLM 挑选并本地应用
            "expression": self.expression_endpoint,
            # 兜底清单（渲染端优先从已加载模型直接读取可用表情/动作，读不到才用这里）
            "expr_names": expr_names,
            "motion_names": motion_names,
        }
        with open(os.path.join(DESKTOP_DIR, "runtime_config.json"), "w", encoding="utf-8") as f:
            json.dump(runtime, f, ensure_ascii=False, indent=2)

    # ---------- 依赖安装 ----------

    def _deps_installed(self):
        return os.path.isdir(os.path.join(DESKTOP_DIR, "node_modules", "electron"))

    def ensure_deps(self):
        if self._deps_installed():
            return True
        if not self.config.get("auto_install", True):
            logger.error("Electron 依赖未安装且 auto_install=false，请手动在 desktop 目录执行 npm install")
            return False
        npm = _which("npm.cmd", "npm") if IS_WIN else _which("npm")
        if not npm:
            logger.error("未找到 npm，请先安装 Node.js (https://nodejs.org)")
            return False
        logger.server("🔧 首次启用 Live2D：正在执行 npm install（将下载 Electron，约百 MB，请耐心等待）…")
        # Electron 二进制默认从 github 下载，国内常超时；用可配置镜像兜底
        env = os.environ.copy()
        env.setdefault(
            "ELECTRON_MIRROR",
            self.config.get("electron_mirror", "https://registry.npmmirror.com/-/binary/electron/"),
        )
        env.setdefault("npm_config_registry", self.config.get("npm_registry", "https://registry.npmmirror.com/"))
        try:
            result = subprocess.run(
                [npm, "install"],
                cwd=DESKTOP_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                shell=IS_WIN,  # Windows 下 npm.cmd 需要 shell
                env=env,
            )
            if result.returncode != 0:
                logger.error(f"npm install 失败：\n{result.stdout[-2000:]}")
                return False
            logger.info("Electron 依赖安装完成")
            return True
        except Exception as e:
            logger.error(f"npm install 执行异常：{e}")
            return False

    # ---------- 启动 / 关闭 ----------

    def is_running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self):
        with self._lock:
            if self.is_running():
                logger.info("Live2D 渲染进程已在运行")
                return True
            if not self.ensure_deps():
                return False
            self._write_runtime_config()

            npx = _which("npx.cmd", "npx") if IS_WIN else _which("npx")
            if not npx:
                logger.error("未找到 npx，无法启动 Electron")
                return False

            creationflags = 0
            preexec_fn = None
            if IS_WIN:
                # 新建进程组，便于整组终止
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                preexec_fn = os.setsid

            try:
                self.proc = subprocess.Popen(
                    [npx, "electron", "."],
                    cwd=DESKTOP_DIR,
                    creationflags=creationflags,
                    preexec_fn=preexec_fn,
                    shell=IS_WIN,
                )
                logger.info(f"Live2D 渲染进程已启动 (pid={self.proc.pid})")
                return True
            except Exception as e:
                logger.error(f"启动 Electron 失败：{e}")
                self.proc = None
                return False

    def stop(self):
        with self._lock:
            if not self.is_running():
                self.proc = None
                return
            try:
                if IS_WIN:
                    # 用 taskkill 终止整个进程树（electron 会派生多个子进程）
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    os.killpg(os.getpgid(self.proc.pid), 15)
            except Exception as e:
                logger.warning(f"终止 Live2D 进程出错：{e}")
                try:
                    self.proc.terminate()
                except Exception:
                    pass
            finally:
                self.proc = None
                logger.info("Live2D 渲染进程已关闭")

    def restart(self):
        """重启渲染进程：用于切换模型（stop 后 start 会用最新 config 重写 runtime_config）。"""
        self.stop()
        return self.start()
