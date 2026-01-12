import random

import urllib.parse
import os
import shutil
import httpx
import re
import copy
import pprint
from framework_common.utils.install_and_import import install_and_import
from .login_core import ini_login_Link_Prising
from .common import json_init,filepath_init,COMMON_HEADER,GLOBAL_NICKNAME
from urllib.parse import urlparse
from urllib.parse import parse_qs
from datetime import datetime, timedelta
from developTools.utils.logger import get_logger
logger=get_logger()
import json
from framework_common.manshuo_draw.manshuo_draw import manshuo_draw

"""以下为抖音/TikTok类型代码/Type code for Douyin/TikTok"""
URL_TYPE_CODE_DICT = {
    # 抖音/Douyin
    2: 'image',
    4: 'video',
    68: 'image',
    # TikTok
    0: 'video',
    51: 'video',
    55: 'video',
    58: 'video',
    61: 'video',
    150: 'image'
}

"""
dy视频信息
"""
DOUYIN_VIDEO = "https://www.douyin.com/aweme/v1/web/aweme/detail/?device_platform=webapp&aid=6383&channel=channel_pc_web&aweme_id={}&pc_client_type=1&version_code=190500&version_name=19.5.0&cookie_enabled=true&screen_width=1344&screen_height=756&browser_language=zh-CN&browser_platform=Win32&browser_name=Firefox&browser_version=118.0&browser_online=true&engine_name=Gecko&engine_version=109.0&os_name=Windows&os_version=10&cpu_core_num=16&device_memory=&platform=PC"

"""
今日头条 DY API
"""
DY_TOUTIAO_INFO = "https://aweme.snssdk.com/aweme/v1/play/?video_id={}&ratio=1080p&line=0"

"""
tiktok视频信息
"""
TIKTOK_VIDEO = "https://api22-normal-c-alisg.tiktokv.com/aweme/v1/feed/"
"""
通用请求头
"""
COMMON_HEADER = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 '
                  'UBrowser/6.2.4098.3 Safari/537.36'
}


header = {
    'User-Agent': "Mozilla/5.0 (Linux; Android 8.0; Pixel 2 Build/OPD3.170816.012) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Mobile Safari/537.36 Edg/87.0.664.66"
}


def generate_x_bogus_url(url, headers):
    """
            生成抖音A-Bogus签名
            :param url: 视频链接
            :return: 包含X-Bogus签名的URL
            """
    # 调用JavaScript函数
    query = urllib.parse.urlparse(url).query
    abogus_file_path = f'{os.path.dirname(os.path.abspath(__file__))}/a-bogus.js'
    with open(abogus_file_path, 'r', encoding='utf-8') as abogus_file:
        abogus_file_path_transcoding = abogus_file.read()
    execjs=install_and_import("PyExecJS",'execjs')
    abogus = execjs.compile(abogus_file_path_transcoding).call('generate_a_bogus', query, headers['User-Agent'])
    #print('生成的A-Bogus签名为: {}'.format(abogus))
    return url + "&a_bogus=" + abogus


def generate_random_str(self, randomlength=16):
    """
    根据传入长度产生随机字符串
    param :randomlength
    return:random_str
    """
    random_str = ''
    base_str = 'ABCDEFGHIGKLMNOPQRSTUVWXYZabcdefghigklmnopqrstuvwxyz0123456789='
    length = len(base_str) - 1
    for _ in range(randomlength):
        random_str += base_str[random.randint(0, length)]
    return random_str


async def dou_transfer_other(dou_url):
    """
        图集临时解决方案
    :param dou_url:
    :return:
    """
    douyin_temp_data = httpx.get(f"https://api.xingzhige.com/API/douyin/?url={dou_url}").json()
    data = douyin_temp_data.get("data", { })
    item_id = data.get("jx", { }).get("item_id")
    item_type = data.get("jx", { }).get("type")

    if not item_id or not item_type:
        raise ValueError("备用 API 未返回 item_id 或 type")

    # 备用API成功解析图集，直接处理
    if item_type == "图集":
        item = data.get("item", { })
        cover = item.get("cover", "")
        images = item.get("images", [])
        # 只有在有图片的情况下才发送
        if images:
            #pprint.pprint(data)
            author = data.get("author", { }).get("name", "")
            title = data.get("item", { }).get("title", "")
            avatar_url = data.get("author", { }).get("avatar", "")
            video_time = data.get("stat", { }).get("time", "")
            dt = datetime.fromtimestamp(video_time)  # 本地时间，如果想要 UTC 时间用 utcfromtimestamp
            video_time = dt.strftime('%Y-%m-%d %H:%M:%S')
            return cover, author, title, images ,avatar_url, video_time

    return None, None, None, None, None, None



async def dy(url,filepath=None):
    """
        抖音解析
    :param bot:
    :param event:
    :return:
    """
    if filepath is None:filepath = filepath_init
    contents=[]
    # 消息
    msg=url
    json_check = copy.deepcopy(json_init)
    json_check['status'] = True
    json_check['video_url'] = False
    json_check['soft_type'] = 'dy'
    #logger.info(msg)
    # 正则匹配
    reg = r"(http:|https:)\/\/v.douyin.com\/[A-Za-z\d._?%&+\-=#]*"
    dou_url = re.search(reg, msg, re.I)[0]
    dou_url_2 = httpx.get(dou_url).headers.get('location')
    json_check['url'] = dou_url
    logger.info(f'dou_url:{dou_url}')
    logger.info(f'dou_url_2:{dou_url_2}')

    # 实况图集临时解决方案，eg.  https://v.douyin.com/iDsVgJKL/
    if "share/slides" in dou_url_2:
        cover, author, title, img_context,avatar_url, video_time = await dou_transfer_other(dou_url)
        # 如果第一个不为None 大概率是成功
        if author is not None:
            pass
            #logger.info(f"{GLOBAL_NICKNAME}识别：【抖音】\n作者：{author}\n标题：{title}")
            #logger.info(url for url in images)
            # 截断后续操作
            title = title.replace('#', '\n[tag]#', 1)
            if '#' in title: title += '[/tag]'

            if len(img_context) != 1:
                json_check['pic_path'] = await manshuo_draw([{'type': 'backdrop', 'subtype': 'one_color'},
                    {'type': 'avatar', 'subtype': 'common', 'img': [avatar_url], 'upshift_extra': 20,
                     'content': [f"[name]{author}[/name]\n[time]{video_time}[/time]"], 'type_software': 'dy'},
                    img_context, [title]])
            else:
                json_check['pic_path'] = await manshuo_draw([{'type': 'backdrop', 'subtype': 'one_color'},
                    {'type': 'avatar', 'subtype': 'common', 'img': [avatar_url], 'upshift_extra': 20,
                     'content': [f"[name]{author}[/name]\n[time]{video_time}[/time]"], 'type_software': 'dy', },
                    {'type': 'img', 'subtype': 'common_with_des_right', 'img': img_context, 'content': [title]}])
            json_check['pic_url_list'] = img_context
            return json_check
    # logger.error(dou_url_2)
    reg2 = r".*(video|note)\/(\d+)\/(.*?)"
    # 获取到ID
    dou_id = re.search(reg2, dou_url_2, re.I)[2]
    douyin_ck=ini_login_Link_Prising(type=2)
    if douyin_ck is None:
        logger.warning("无法获取到管理员设置的抖音ck！,启用默认配置，若失效请登录")
        douyin_ck='odin_tt=xxx;passport_fe_beating_status=xxx;sid_guard=xxx;uid_tt=xxx;uid_tt_ss=xxx;sid_tt=xxx;sessionid=xxx;sessionid_ss=xxx;sid_ucp_v1=xxx;ssid_ucp_v1=xxx;passport_assist_user=xxx;ttwid=1%7CKPNpSlm-sMOACobI2T3-9GpRhKYzXoy07j_S-KjqxBU%7C1737658644%7Cbec487261896df392f3fe61ed66fa449bbf3f6a88866a7185d2cb17bfc2b8397;'
    # API、一些后续要用到的参数
    headers = {
                  'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
                  'referer': f'https://www.douyin.com/video/{dou_id}',
                  'cookie': douyin_ck
              } | COMMON_HEADER
    api_url = DOUYIN_VIDEO.replace("{}", dou_id)
    #logger.info(f'api_url: {api_url}')
    api_url = generate_x_bogus_url(api_url, headers)  # 如果请求失败直接返回
    async with httpx.AsyncClient(headers=headers, timeout=10) as client:
        response = await client.get(api_url)
        detail=response.json()
        if detail is None:
            logger.info(f"{GLOBAL_NICKNAME}识别：抖音，解析失败！")
            # await douyin.send(Message(f"{GLOBAL_NICKNAME}识别：抖音，解析失败！"))
            return
        # 获取信息

        detail = detail['aweme_detail']
        formatted_json = json.dumps(detail, indent=4)
        #print(formatted_json)
        #print(detail['author']['signature'])
        # 判断是图片还是视频
        url_type_code = detail['aweme_type']
        url_type = URL_TYPE_CODE_DICT.get(url_type_code, 'video')
        # 根据类型进行发送
        avatar_url, cover_url = detail['author']['avatar_thumb']['url_list'][0], \
        detail['author']['cover_url'][0]['url_list'][1]
        owner_name = detail['author']['nickname']
        #logger.info(f'avatar_url: {avatar_url}\ncover_url: {cover_url}')
        video_time = datetime.utcfromtimestamp(detail['create_time']) + timedelta(hours=8)
        video_time = video_time.strftime('%Y-%m-%d %H:%M:%S')

        if url_type == 'video':
            # 识别播放地址
            player_uri = detail.get("video").get("play_addr")['uri']
            player_real_addr = DY_TOUTIAO_INFO.replace("{}", player_uri)
            cover_url = detail.get("video").get("dynamic_cover")['url_list'][0]
            img_context=[cover_url]
            context = detail.get("desc").replace('#', '\n[tag]#', 1)
            if '#' in context: context += '[/tag]'

            player_uri = detail.get("video").get("play_addr")['uri']
            player_real_addr = DY_TOUTIAO_INFO.replace("{}", player_uri)
            #print(player_real_addr)
            json_check['video_url'] = player_real_addr
            #video_path = await download_video(player_real_addr, filepath=filepath)

        elif url_type == 'image':
            # 无水印图片列表/No watermark image list
            no_watermark_image_list = []
            for i in detail['images']:
                no_watermark_image_list.append(i['url_list'][0])
            # logger.info(no_watermark_image_list)
            img_context=no_watermark_image_list

            # await send_forward_both(bot, event, make_node_segment(bot.self_id, no_watermark_image_list))
            context = detail.get("desc").replace('#', '\n[tag]#', 1)
            if '#' in context: context += '[/tag]'
        context += f"\n--------------\n作者简介：\n{detail['author']['signature']}"
        if len(img_context) != 1:
            json_check['pic_path'] = await manshuo_draw([{'type': 'backdrop', 'subtype': 'one_color'},
                            {'type': 'avatar', 'subtype': 'common', 'img': [avatar_url],'upshift_extra': 20,
                             'content': [f"[name]{owner_name}[/name]\n[time]{video_time}[/time]" ], 'type_software': 'dy'},img_context,[context]])
        else:
            json_check['pic_path'] = await manshuo_draw([{'type': 'backdrop', 'subtype': 'one_color'},
                            {'type': 'avatar', 'subtype': 'common', 'img': [avatar_url],'upshift_extra': 20,
                             'content': [f"[name]{owner_name}[/name]\n[time]{video_time}[/time]" ], 'type_software': 'dy', },
                            {'type': 'img', 'subtype': 'common_with_des_right', 'img': img_context, 'content': [context]}])
        #print(json_check['pic_path'])
        json_check['pic_url_list'] = img_context
        return json_check



if __name__ == '__main__':
    node_path = shutil.which("node")  # 自动查找 Node.js 可执行文件路径
    if not node_path:
        raise EnvironmentError("Node.js 未安装或未正确添加到系统 PATH 中!")

    import execjs
    # 强制使用 Node.js
    execjs._runtime = execjs.ExternalRuntime("Node.js", node_path)
    # 验证是否成功切换到 Node.js
    print(execjs.get().name)  # 应该输出 "Node.js"