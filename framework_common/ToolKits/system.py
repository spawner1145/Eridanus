from .base import BaseTool

import importlib.util

from pip._internal.cli.main import main as pip_main

pip_main(['config', 'set', 'global.index-url', 'https://mirrors.aliyun.com/pypi/simple/'])
class SystemProcessor(BaseTool):
    def __init__(self):
        super().__init__(__class__.__name__)

    def install_and_import(self,package_name, import_name=None):
        """检测模块是否已安装，若未安装则通过 pip 安装"""
        if import_name is None:
            import_name = package_name

        spec = importlib.util.find_spec(import_name)
        if spec is None:
            self.logger.warning(f"{package_name} 未安装，正在安装...")
            pip_main(['install', package_name])
            spec = importlib.util.find_spec(import_name)
            if spec is None:
                self.logger.error(f"安装失败：无法找到 {import_name} 模块")
                return None

        return importlib.import_module(import_name)
