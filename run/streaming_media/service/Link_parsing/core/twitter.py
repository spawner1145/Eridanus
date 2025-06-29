import httpx
import re
import copy
from .login_core import ini_login_Link_Prising
from .common import json_init,filepath_init,COMMON_HEADER,GLOBAL_NICKNAME,GENERAL_REQ_LINK
from urllib.parse import urlparse
from urllib.parse import parse_qs
from datetime import datetime, timedelta
from developTools.utils.logger import get_logger
logger=get_logger()
import json
from framework_common.manshuo_draw.manshuo_draw import manshuo_draw



async def twitter(url,filepath=None,proxy=None):
    """
        X解析
    :param bot:
    :param event:
    :return:
    """
    msg=url
    contents=[]
    json_check = copy.deepcopy(json_init)
    json_check['soft_type'] = 'x'
    json_check['status'] = True
    json_check['video_url'] = False
    if filepath is None: filepath = filepath_init
    x_url = re.search(r"https?:\/\/x.com\/[0-9-a-zA-Z_]{1,20}\/status\/([0-9]*)", msg)[0]

    x_url = GENERAL_REQ_LINK.replace("{}", x_url)

    # 内联一个请求
    def x_req(url):
        return httpx.get(url, headers={
            'Accept': 'ext/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,'
                      'application/signed-exchange;v=b3;q=0.7',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Host': '47.99.158.118',
            'Proxy-Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-User': '?1',
            **COMMON_HEADER
        })
    #print(x_req(x_url).json())
    x_data: object = x_req(x_url).json()['data']

    if x_data is None:
        x_url = x_url + '/photo/1'
        x_data = x_req(x_url).json()['data']
    #print(x_data)

    x_url_res = x_data['url']
    #print(x_url_res)
    #await twit.send(Message(f"{GLOBAL_NICKNAME}识别：小蓝鸟学习版"))

    # 海外服务器判断
    #proxy = None if IS_OVERSEA else resolver_proxy
    logger.info(x_url_res)
    # 图片
    if x_url_res.endswith(".jpg") or x_url_res.endswith(".png"):
        contents = [x_url_res]
        json_check['pic_path'] = await manshuo_draw(contents)
        return json_check
    else:
        # 视频
        json_check['video_url'] = x_url_res
        return json_check
        #res = await download_video(x_url_res, proxy)