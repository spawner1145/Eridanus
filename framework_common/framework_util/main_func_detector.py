import sys
import importlib.util
from typing import List, Callable
from pathlib import Path
import logging
import traceback

import colorlog

from framework_common.utils.system_logger import get_logger

# 创建颜色日志处理器
logger = get_logger("main_func_detector")


def check_has_main(module_name: str) -> tuple[bool, object]:
    """检查模块是否包含 `main()` 方法，并缓存已加载的模块"""

    try:
        # 如果模块已经在sys.modules中，直接使用
        if module_name in sys.modules:
            module = sys.modules[module_name]
            return hasattr(module, "main") and callable(getattr(module, "main")), module

        # 尝试使用标准导入，避免手动构建模块导致的竞态条件
        try:
            module = importlib.import_module(module_name)
            return hasattr(module, "main") and callable(getattr(module, "main")), module
        except (ImportError, KeyError, AttributeError):
            # 标准导入失败，使用spec方式
            pass

        spec = importlib.util.find_spec(module_name)
        if spec is None:
            logger.warning(f"⚠️ 未找到模块 {module_name}")
            return False, None

        if spec.loader is None:
            logger.warning(f"⚠️ 模块 {module_name} 没有加载器")
            return False, None

        # 检查模块是否在导入过程中（避免竞态条件）
        if module_name in sys.modules:
            module = sys.modules[module_name]
            # 如果模块正在导入中但还未完成，等待一下
            if not hasattr(module, '__file__'):
                import time
                time.sleep(0.01)  # 等待10ms
                if module_name in sys.modules:
                    module = sys.modules[module_name]
            return hasattr(module, "main") and callable(getattr(module, "main")), module

        module = importlib.util.module_from_spec(spec)

        # 原子性操作：先设置一个占位符，避免并发导入时的竞态条件
        placeholder = type(sys)('placeholder')
        placeholder.__file__ = getattr(spec, 'origin', '')
        sys.modules[module_name] = placeholder

        # 预先加载所有依赖的父包
        parts = module_name.split('.')
        for i in range(1, len(parts)):
            parent_name = '.'.join(parts[:i])
            if parent_name not in sys.modules:
                try:
                    parent_spec = importlib.util.find_spec(parent_name)
                    if parent_spec and parent_spec.loader:
                        parent_module = importlib.util.module_from_spec(parent_spec)
                        # 同样使用占位符避免竞态条件
                        parent_placeholder = type(sys)('placeholder')
                        parent_placeholder.__file__ = getattr(parent_spec, 'origin', '')
                        sys.modules[parent_name] = parent_placeholder
                        parent_spec.loader.exec_module(parent_module)
                        sys.modules[parent_name] = parent_module
                except Exception:
                    # 父包加载失败不影响当前模块
                    pass

        try:
            # 执行模块
            spec.loader.exec_module(module)
            # 替换占位符为真实模块
            sys.modules[module_name] = module
            return hasattr(module, "main") and callable(getattr(module, "main")), module
        except Exception as exec_error:
            # 如果执行失败，从sys.modules中移除避免污染
            if module_name in sys.modules:
                del sys.modules[module_name]
            raise exec_error

    except Exception as e:
        if not module_name.startswith("run.character_detection."):
            logger.warning(f"⚠️ 加载模块 {module_name} 失败， \n{e}")
            traceback.print_exc()
        return False, None


def load_main_functions(init_file: str) -> List[Callable]:
    """
    从 **init**.py 所在目录加载包含 main 函数的模块。
    参数 init_file: **init**.py 的文件路径（通常为 **file**）。
    返回 entrance_func 列表，包含所有 main 函数。
    """
    entrance_func: List[Callable] = []
    module_names: List[str] = []

    # 获取 **init**.py 所在目录
    dir_path = Path(init_file).parent
    package = dir_path.parent.name  # 父目录名（如 run）
    subpackage = dir_path.name  # 当前目录名（如 acg_information）

    # 遍历目录下的 .py 文件
    for file_path in dir_path.glob("*.py"):
        if file_path.name == "__init__.py":  # 跳过 **init**.py
            continue
        module_name = file_path.stem
        # 构造模块路径（例如 run.acg_information.module_name）
        full_module_name = f"{package}.{subpackage}.{module_name}"

        # 检查是否包含 main 函数
        has_main, module = check_has_main(full_module_name)

        if has_main:
            entrance_func.append(module.main)
            module_names.append(module_name)
            # logger.info(f"成功导入 {module_name}.main")
        else:
            pass
            # logger.warning(f"跳过 {module_name}：无 callable main 函数")

    # 输出 entrance_func 内容
    if module_names:
        pass
        # print(f"entrance_func: [{', '.join(f'{name}.main' for name in module_names)}]")
    else:
        logger.warning(f"{init_file} 未找到任何可用的 entrance_func")
        # print("entrance_func: []", file=sys.stderr)

    return entrance_func