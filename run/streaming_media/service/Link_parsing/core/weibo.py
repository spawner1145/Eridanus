import math
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
import asyncio

# 定义 base62 编码字符表
ALPHABET = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
WEIBO_SINGLE_INFO = "https://m.weibo.cn/statuses/show?id={}"

def base62_encode(number):
    """将数字转换为 base62 编码"""
    if number == 0:
        return '0'

    result = ''
    while number > 0:
        result = ALPHABET[number % 62] + result
        number //= 62

    return result


def mid2id(mid):
    mid = str(mid)[::-1]  # 反转输入字符串
    size = math.ceil(len(mid) / 7)  # 计算每个块的大小
    result = []

    for i in range(size):
        # 对每个块进行处理并反转
        s = mid[i * 7:(i + 1) * 7][::-1]
        # 将字符串转为整数后进行 base62 编码
        s = base62_encode(int(s))
        # 如果不是最后一个块并且长度不足4位，进行左侧补零操作
        if i < size - 1 and len(s) < 4:
            s = '0' * (4 - len(s)) + s
        result.append(s)

    result.reverse()  # 反转结果数组
    return ''.join(result)  # 将结果数组连接成字符串

async def wb(url,filepath=None):
    json_check = copy.deepcopy(json_init)
    json_check['soft_type'] = 'wb'
    json_check['status'] = True
    json_check['video_url'] = False
    message = url
    weibo_id = None
    content=[]
    reg = r'(jumpUrl|qqdocurl)": ?"(.*?)"'
    if filepath is None: filepath = filepath_init
    # 处理卡片问题
    if 'com.tencent.structmsg' or 'com.tencent.miniapp' in message:
        match = re.search(reg, message)
        logger.info(match)
        if match:
            get_url = match.group(2)
            logger.info(get_url)
            if get_url:
                message = json.loads('"' + get_url + '"')
    else:
        message = message
    # logger.info(message)
    # 判断是否包含 "m.weibo.cn"
    if "m.weibo.cn" in message:
        # https://m.weibo.cn/detail/4976424138313924
        match = re.search(r'(?<=detail/)[A-Za-z\d]+', message) or re.search(r'(?<=m.weibo.cn/)[A-Za-z\d]+/[A-Za-z\d]+',
                                                                            message)
        weibo_id = match.group(0) if match else None

    # 判断是否包含 "weibo.com/tv/show" 且包含 "mid="
    elif "weibo.com/tv/show" in message and "mid=" in message:
        # https://weibo.com/tv/show/1034:5007449447661594?mid=5007452630158934
        match = re.search(r'(?<=mid=)[A-Za-z\d]+', message)
        if match:
            weibo_id = mid2id(match.group(0))

    # 判断是否包含 "weibo.com"
    elif "weibo.com" in message:
        # https://weibo.com/1707895270/5006106478773472
        match = re.search(r'(?<=weibo.com/)[A-Za-z\d]+/[A-Za-z\d]+', message)
        weibo_id = match.group(0) if match else None

    # 无法获取到id则返回失败信息
    if not weibo_id:
        logger.info("解析失败：无法获取到wb的id")
    # 最终获取到的 id
    weibo_id = weibo_id.split("/")[1] if "/" in weibo_id else weibo_id
    json_check['url'] = f"https://m.weibo.cn/detail/{weibo_id}"
    # 请求数据
    #print(WEIBO_SINGLE_INFO.replace('{}', weibo_id))
    resp = httpx.get(WEIBO_SINGLE_INFO.replace('{}', weibo_id), headers={
                                                                            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                                                                            "cookie": "_T_WM=40835919903; WEIBOCN_FROM=1110006030; MLOGIN=0; XSRF-TOKEN=4399c8",
                                                                            "Referer": f"https://m.weibo.cn/detail/{id}",
                                                                        } | COMMON_HEADER)
    #print(resp)
    resp = resp.json()
    weibo_data = resp['data']
    formatted_json = json.dumps(weibo_data, indent=4)
    #logger.info(formatted_json)
    text, status_title, source, region_name, pics, page_info = (weibo_data.get(key, None) for key in
                                                                ['text', 'status_title', 'source', 'region_name',
                                                                 'pics', 'page_info'])
    owner_name,avatar_hd,video_time=weibo_data['user']['screen_name'],weibo_data['user']['avatar_hd'],weibo_data['created_at']
    context=re.sub(r'<[^>]+>', '', text)


    if pics:
        formatted_json = json.dumps(pics, indent=4)
        #logger.info(formatted_json)
        pics = map(lambda x: x['url'], pics)
        img_context = [f'{item}' for item in pics]


    if page_info:
        #logger.info(page_info)
        formatted_json = json.dumps(page_info, indent=4)
        #logger.info(formatted_json)
        try:video_url = page_info.get('urls', '').get('mp4_720p_mp4', '') or page_info.get('urls', '').get('mp4_hd_mp4', '')
        except:video_url = ''
        if video_url:
            json_check['video_url'] = video_url
        if 'page_pic' in page_info:
            if page_info.get('type') != 'topic' and page_info.get('type') != 'place':
                page_pic=page_info.get('page_pic').get('url')
                img_context=[page_pic]
    if len(img_context) != 1:
        json_check['pic_path'] = await manshuo_draw([
            {'type': 'avatar', 'subtype': 'common', 'img': [avatar_hd], 'upshift_extra': 20,
             'content': [f"[name]{owner_name}[/name]\n[time]{video_time}[/time]"], 'type_software': 'wb', }, img_context, [context]])
    else:
        json_check['pic_path'] = await manshuo_draw([
            {'type': 'avatar', 'subtype': 'common', 'img': [avatar_hd], 'upshift_extra': 20,
             'content': [f"[name]{owner_name}[/name]\n[time]{video_time}[/time]"], 'type_software': 'wb', },
            {'type': 'img', 'subtype': 'common_with_des_right', 'img': img_context, 'content': [context]}])
    json_check['pic_url_list'] = img_context
    return json_check
