import httpx
import re
import copy
from .login_core import ini_login_Link_Prising
from .common import json_init,filepath_init,COMMON_HEADER,GLOBAL_NICKNAME
from urllib.parse import urlparse
from urllib.parse import parse_qs
from datetime import datetime, timedelta
from developTools.utils.logger import get_logger
logger=get_logger()
import json
from framework_common.manshuo_draw.manshuo_draw import manshuo_draw





async def majsoul_PILimg(text=None,img_context=None,filepath=None,type_soft='雀魂牌谱屋',canvas_width=1200):
    contents=[]
    json_check = copy.deepcopy(json_init)
    json_check['soft_type'] = '雀魂牌谱屋'
    json_check['status'] = True
    json_check['video_url'] = False
    if filepath is None: filepath = filepath_init

    text_total = ''
    words = text.split("\n")  # 按换行符分割文本，逐行处理
    for line in words:  # 遍历每一行（处理换行符的部分）
        if '昵称：' in line:
            title = line.split("当前段位")[0]
            rating=line.replace(title,'').split('当前pt')[0].replace('当前段位：','').replace(' ','')
            if '当前pt' in line:
                pt_check=line.split('当前pt')[1]
            else:pt_check='未知'
            contents.append(f"title:{title.replace('昵称：','玩家：')}")
            contents.append(f"段位：【{rating}】当前pt{pt_check}")
        elif '查询到多条角色昵称呢~，若输出不是您想查找的昵称，请补全查询昵称' in line:
            contents.append(f'tag:{line}')
        else:
            text_total += f"{line}\n"

    if img_context is None:img_context=[]
    json_check['pic_path'] = await manshuo_draw([text_total,img_context])
    return json_check