import os
import shutil
from .old_remain import copy_yaml
from .new_convert import menu_convert_draw

async def menu_maker():
    menu_statue = await copy_yaml()
    if menu_statue['status'] is False: return
    menu_draw_info = await menu_convert_draw(menu_statue['menu'])
    return menu_draw_info