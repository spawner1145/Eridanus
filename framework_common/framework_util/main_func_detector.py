import sys
import importlib.util
from typing import List, Callable
from pathlib import Path
import logging
import traceback

import colorlog

from framework_common.utils.system_logger import get_logger

# 创建颜色日志处理器
logger=get_logger("main_func_detector")

# 模块缓存
module_cache = {}


def check_has_main_and_cache(module_name: str) -> tuple[bool, object]:
    """检查模块是否包含 `main` 方法，并缓存已加载的模块"""
    try:
        if module_name in module_cache:
            module = module_cache[module_name]
        else:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                logger.warning(f"⚠️ 未找到模块 {module_name}")
                return False, None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            #module_cache[module_name] = module

        return hasattr(module, "main") and callable(getattr(module, "main")), module
    except Exception:
        logger.warning(f"⚠️ 加载模块 {module_name} 失败，请重试或提交issue，也可向q群913122269反馈")
        traceback.print_exc(file=sys.stderr)
        return False, None


def load_main_functions(init_file: str) -> List[Callable]:
    """
    从 __init__.py 所在目录加载包含 main 函数的模块。
    参数 init_file: __init__.py 的文件路径（通常为 __file__）。
    返回 entrance_func 列表，包含所有 main 函数。
    """
    entrance_func: List[Callable] = []
    module_names: List[str] = []

    # 获取 __init__.py 所在目录
    dir_path = Path(init_file).parent
    package = dir_path.parent.name  # 父目录名（如 run）
    subpackage = dir_path.name  # 当前目录名（如 acg_information）

    # 遍历目录下的 .py 文件
    for file_path in dir_path.glob("*.py"):
        if file_path.name == "__init__.py":  # 跳过 __init__.py
            continue
        module_name = file_path.stem
        # 构造模块路径（例如 run.acg_information.module_name）
        full_module_name = f"{package}.{subpackage}.{module_name}"

        # 检查是否包含 main 函数
        has_main, module = check_has_main_and_cache(full_module_name)

        if has_main:
            entrance_func.append(module.main)
            module_names.append(module_name)
            logger.info(f"成功导入 {module_name}.main")
        else:
            pass
            #logger.warning(f"跳过 {module_name}：无 callable main 函数")

    # 输出 entrance_func 内容
    if module_names:
        pass
        #print(f"entrance_func: [{', '.join(f'{name}.main' for name in module_names)}]")
    else:
        logger.warning(f"{init_file} 未找到任何可用的 entrance_func")
        #print("entrance_func: []", file=sys.stderr)

    return entrance_func