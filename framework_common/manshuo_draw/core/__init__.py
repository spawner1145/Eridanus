# __init__.py
from .deal_img import deal_img
from .db_core.RedisDatabase import *
from .classic_collection import json_check
from .menu_maker import menu_maker

# 定义 __all__ 列表，明确导出的内容
__all__ = ["deal_img",'RedisDatabase','json_check','menu_maker']