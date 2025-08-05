
import importlib
import inspect
import os
import traceback

from developTools.utils.logger import get_logger

logger = get_logger()
PLUGIN_DIR = "run"
dynamic_imports = {}

# 加载 __init__.py 中的 dynamic_imports
for root, dirs, files in os.walk(PLUGIN_DIR):
    if "service" in root.split(os.sep):
        continue

    if "__init__.py" in files:
        module_name = root.replace(os.sep, ".")
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, "dynamic_imports"):
                dynamic_imports[module_name] = module.dynamic_imports
                logger.info(f"✅ 函数调用映射加载成功: {module_name}.dynamic_imports")
            else:
                logger.warning(f"⚠️ {module_name} 未定义 dynamic_imports")
        except Exception as e:
            logger.error(f"❌ 无法导入 {module_name}: {e}")
            traceback.print_exc()

loaded_functions = {}

# 处理 dynamic_imports（支持字典和列表两种格式）
for module_name, imports in dynamic_imports.items():
    try:
        # 情况 1: dynamic_imports 是字典+字符串，旧导入方式。
        if isinstance(imports, dict):
            for sub_module_name, functions in imports.items():
                try:
                    module = importlib.import_module(sub_module_name)
                    for func_name in functions:
                        if hasattr(module, func_name):
                            loaded_functions[func_name] = getattr(module, func_name)
                            logger.info(f"✅ 成功加载 {sub_module_name}.{func_name}")
                        else:
                            logger.warning(f"⚠️ {sub_module_name} 中不存在 {func_name}")
                except Exception as e:
                    logger.error(f"❌ 无法导入模块 {sub_module_name}: {e}")
                    traceback.print_exc()

        # 情况 2: dynamic_imports 是列表（新格式，函数对象）
        elif isinstance(imports, list):
            for func in imports:
                if callable(func):
                    func_name = func.__name__
                    loaded_functions[func_name] = func
                    logger.info(f"✅ 成功加载 {module_name}.{func_name}")
                else:
                    logger.warning(f"⚠️ {module_name} 中的 {func} 不是可调用对象")
        else:
            logger.warning(f"⚠️ {module_name} 的 dynamic_imports 格式不正确")
    except Exception as e:
        logger.error(f"❌ 处理模块 {module_name} 时出错: {e}")
        traceback.print_exc()

async def call_quit_chat(bot, event, config):
    return False

async def call_func(bot, event, config, func_name, params):
    """
    动态调用已导入的函数。

    参数:
        func_name (str): 函数名。
        params (dict): 函数参数字典。

    返回:
        异步函数的返回值。
    """
    print(f"Calling function '{func_name}' with parameters: {params}")

    func = loaded_functions.get(func_name)
    if func is None:
        raise ValueError(f"Function '{func_name}' not found in loaded_functions.")

    if not callable(func):
        raise TypeError(f"'{func_name}' is not callable.")

    if not inspect.iscoroutinefunction(func):
        raise TypeError(f"'{func_name}' is not an async function.")

    return await func(bot, event, config, **params)
