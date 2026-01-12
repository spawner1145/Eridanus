import random
import string
import re
import os
import sys
from PIL import Image, ImageDraw, ImageFont, ImageOps,ImageFilter
import platform
import psutil
import math
from pathlib import Path

current_file = Path(__file__)
# 获取当前脚本文件所在的目录
plugin_dir = current_file.parent.parent.parent.parent
core_dir = plugin_dir / 'core'
data_dir = plugin_dir / 'data'
occupy_chart = data_dir / 'img' / 'main_chart' / 'mainchart.jpeg'
current_dir = Path.cwd()
difference_dir = plugin_dir.relative_to(current_dir)

debug_mode = False #设定全局变量，表示绘图是否开启调试功能


def printf(text):
    global debug_mode
    if debug_mode:
        print(text)

def printf_check(json_img):
    global debug_mode
    for key_json in json_img:
        #print(key_json)
        if key_json['type'] == 'basic_set':
            if 'debug' in key_json and key_json['debug'] is True:
                debug_mode = True
                print('本次绘图已开启调试功能')
                break

def random_str(length=10):
    characters = string.ascii_letters + string.digits
    # 生成随机字符串
    random_string = ''.join(random.choice(characters) for _ in range(length))
    return random_string

def add_append_img(contents,contents2,tag=None,tag_item=None,replace_item=None):

    for item in contents2:
        if isinstance(item, dict) and tag is not None and tag_item is not None:
            item[f'{tag}']=tag_item
            if replace_item is not None and item[f'tag']==replace_item: item[f'tag']=tag_item
        contents.append(item)
    return contents

def is_subpath(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False

#获取传入目录的绝对路径，若不是目录则直接返回
def get_abs_path(path,is_dir=False):
    #若是目录则单独判断返回
    if is_dir:
        # 判断是否为绝对路径
        if str(path).startswith('/') or str(path).startswith('\''):return path
        path = Path(path)  # 将其转化为Path对象
        #不是绝对目录则判断是否为插件内目录
        if (plugin_dir / path).exists():
            return plugin_dir / path
        # 不是插件内目录
        return current_dir / path

    #检查是否为str或Path对象
    if not (isinstance(path, str) or isinstance(path, Path)):
        return path
    #首先处理str部分
    if isinstance(path, str):
        str_check = os.path.splitext(path)[1].lower()
        if str_check == '' or isinstance(path, dict):return path
        if str_check not in [".jpg", ".png", ".jpeg", '.webp',".ttf",".yaml",".yml"]:
            return path
        if path.startswith('/') or path.startswith('\''): return path
        try:
            path = Path(path)   #将其转化为Path对象
        except TypeError:
            return path
    #接着处理Path对象部分
    if isinstance(path, Path):
        #通过工作目录判断是否为绝对路径
        if is_subpath(path,current_dir):
            return str(path)
        #判断是否在插件内部的文件,其相对路径为工作目录
        if is_subpath(path,difference_dir):
            return str(current_dir / path)
        # 判断是否在插件内部的文件,其相对路径为插件目录
        if (plugin_dir / path).exists():
            return str(plugin_dir / path)
        #不是插件内文件，是工作目录文件
        return str(current_dir / path)




async def crop_to_square(img_list):
    """
    将一个 Pillow 图像对象裁剪为居中的正方形。
    """
    img_processed_list = []
    for image in img_list:
        width, height = image.size
        # 计算短边的边长，即正方形的边长
        side_length = min(width, height)

        # 计算裁剪区域（左、上、右、下）
        left = (width - side_length) // 2
        top = (height - side_length) // 2
        right = left + side_length
        bottom = top + side_length

        # 裁剪图像
        cropped_image = image.crop((left, top, right, bottom))
        img_processed_list.append(cropped_image)

    return img_processed_list

async def math_convert_percent(values):
    """
    把一串正数映射到0~100的百分制，且满足对数增长趋势。
    """
    # 为了防止log(0)，先确保所有值都大于0
    min_val = min(values)
    if min_val <= 0:
        shift = 1 - min_val  # 让最小值变为1（或更大）
        values = [v + shift for v in values]
    else:
        shift = 0

    # 计算对数值
    log_values = [math.log(v) for v in values]

    # 线性归一化到0~100
    min_log = min(log_values)
    max_log = max(log_values)
    range_log = max_log - min_log if max_log - min_log != 0 else 1

    percents = [(lv - min_log) / range_log  for lv in log_values]

    return percents







if __name__ == '__main__':
    pass
    print(plugin_dir)
    print(current_dir)
    print(difference_dir)