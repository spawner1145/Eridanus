import importlib.util
import os
import sys

from developTools.utils.logger import get_logger

logger=get_logger()

def install_and_import(package_name, import_name=None):
    """检测模块是否已安装，若未安装则通过 pip 安装"""
    if import_name is None:
        import_name = package_name

    spec = importlib.util.find_spec(import_name)
    if spec is None:
        logger.warning(f"{package_name} 未安装，正在安装...")
        os.system(f"{sys.executable} -m pip install {package_name}")

        spec = importlib.util.find_spec(import_name)
        if spec is None:
            logger.error(f"安装失败：无法找到 {import_name} 模块")
            return None

    return importlib.import_module(import_name)