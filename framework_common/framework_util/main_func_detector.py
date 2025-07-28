import sys
import importlib.util
from typing import List, Callable
from pathlib import Path
import logging
import traceback

from framework_common.utils.system_logger import get_logger

logger = get_logger("main_func_detector")


def check_has_main(module_name: str) -> tuple[bool, object]:
    """检查模块是否包含 `main` 方法，并缓存已加载的模块"""
    try:
        # 先检查模块是否已经在 sys.modules 中
        if module_name in sys.modules:
            module = sys.modules[module_name]
            return hasattr(module, "main") and callable(getattr(module, "main")), module

        spec = importlib.util.find_spec(module_name)
        if spec is None or spec.loader is None:
            logger.warning(f"⚠️ 未找到模块 {module_name}")
            return False, None

        # 检查文件是否存在
        if spec.origin and not Path(spec.origin).exists():
            logger.warning(f"⚠️ 模块文件不存在: {spec.origin}")
            return False, None

        module = importlib.util.module_from_spec(spec)

        # 在执行前将模块添加到 sys.modules，支持相对导入
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception:
            # 如果执行失败，从 sys.modules 中移除
            sys.modules.pop(module_name, None)
            raise

        return hasattr(module, "main") and callable(getattr(module, "main")), module

    except Exception as e:
        logger.warning(f"⚠️ 加载模块 {module_name} 失败，请重试或提交issue，也可向q群913122269反馈")
        logger.debug(f"详细错误: {str(e)}")
        # 清理可能的残留
        sys.modules.pop(module_name, None)
        return False, None


def load_main_functions(init_file: str) -> List[Callable]:
    """
    从 __init__.py 所在目录加载包含 main 函数的模块。
    参数 init_file: __init__.py 的文件路径（通常为 __file__）。
    返回 entrance_func 列表，包含所有 main 函数。
    """
    entrance_func: List[Callable] = []
    module_names: List[str] = []

    try:
        # 获取 __init__.py 所在目录
        dir_path = Path(init_file).parent.resolve()

        # 更安全地构建包路径
        package_parts = []
        current_path = dir_path

        # 向上查找，构建完整包路径
        while current_path.parent != current_path:
            if (current_path / "__init__.py").exists():
                package_parts.append(current_path.name)
                current_path = current_path.parent
            else:
                break

        if not package_parts:
            logger.warning(f"无法确定包结构，使用目录名: {dir_path.name}")
            package_parts = [dir_path.name]

        package_parts.reverse()
        base_package = ".".join(package_parts)

        logger.debug(f"扫描目录: {dir_path}, 包路径: {base_package}")

        # 遍历目录下的 .py 文件
        py_files = [f for f in dir_path.glob("*.py") if f.name != "__init__.py"]

        if not py_files:
            logger.warning(f"{dir_path} 目录下没有找到 Python 文件")
            return []

        for file_path in py_files:
            module_name = file_path.stem
            # 构造完整模块路径
            full_module_name = f"{base_package}.{module_name}"

            # 检查是否包含 main 函数
            has_main, module = check_has_main(full_module_name)

            if has_main and module is not None:
                entrance_func.append(module.main)
                module_names.append(module_name)
                logger.info(f"成功导入 {module_name}.main")

        # 输出结果
        if module_names:
            logger.info(f"共加载 {len(module_names)} 个模块: {', '.join(module_names)}")
        else:
            logger.warning(f"{init_file} 未找到任何可用的 entrance_func")

    except Exception as e:
        logger.error(f"加载插件时出错: {str(e)}")
        traceback.print_exc(file=sys.stderr)

    return entrance_func