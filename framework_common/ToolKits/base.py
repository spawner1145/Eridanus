
from abc import ABC, abstractmethod
from .logger import get_logger

class BaseTool(ABC):
    """工具基类"""
    def __init__(self,ToolClsName=None):
        self._initialized = False
        cls_name = ToolClsName if ToolClsName else self.__class__.__name__
        self.logger=get_logger(cls_name)




