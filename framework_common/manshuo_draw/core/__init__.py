# __init__.py
from .deal_img import deal_img
from .db_core.RedisDatabase import *

# 定义 __all__ 列表，明确导出的内容
__all__ = ["deal_img",'RedisDatabase']