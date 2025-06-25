import sys
import asyncio
import copy
from bilibili_api import video, live, article
from bilibili_api import dynamic
from bilibili_api.opus import Opus
from bilibili_api.video import VideoDownloadURLDataDetecter
import re
import httpx
from urllib.parse import urlparse
import time
import os.path
from urllib.parse import parse_qs
from datetime import datetime, timedelta
import json
import traceback
from developTools.utils.logger import get_logger
from run.streaming_media.service.Link_parsing.core.draw import draw_adaptive_graphic_and_textual
from run.streaming_media.service.Link_parsing.core.bili import bili_init,av_to_bv,download_b,info_search_bili
from run.streaming_media.service.Link_parsing.core.weibo import mid2id,WEIBO_SINGLE_INFO
from run.streaming_media.service.Link_parsing.core.common import download_video,download_img,add_append_img,GENERAL_REQ_LINK,get_file_size_mb
from run.streaming_media.service.Link_parsing.core.tiktok import generate_x_bogus_url, dou_transfer_other, \
    COMMON_HEADER,DOUYIN_VIDEO,URL_TYPE_CODE_DICT,DY_TOUTIAO_INFO
from run.streaming_media.service.Link_parsing.core.login_core import ini_login_Link_Prising
from run.streaming_media.service.Link_parsing.core.xhs import XHS_REQ_LINK
from run.streaming_media.service.Link_parsing.core.bangumi_core import claendar_bangumi_get_json,bangumi_subject_post_json,bangumi_subjects_get_json_PIL
import inspect
from asyncio import sleep
from framework_common.manshuo_draw.manshuo_draw import manshuo_draw

from .core import *

try:
    from bilibili_api import select_client
    select_client("httpx")
except ImportError:
    #旧版本兼容问题，整合包更新后删除此部分代码
    pass
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


import random
import os
from bs4 import BeautifulSoup


json_init={'status':False,'content':{},'reason':{},'pic_path':{},'url':{},'video_url':False,'soft_type':False}
filepath_init=f'{os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(bili_init))))}/data/cache/'
GLOBAL_NICKNAME='Bot'
if not os.path.exists(filepath_init):  # 初始化检测文件夹
    os.makedirs(filepath_init)

logger=get_logger()











async def download_video_link_prising(json,filepath=None,proxy=None):
    if filepath is None:filepath = filepath_init
    video_json={}
    if json['soft_type'] == 'bilibili':
        video_path=await download_b(json['video_url'], json['audio_url'], int(time.time()), filepath=filepath)
    elif json['soft_type'] == 'dy':
        video_path = await download_video(json['video_url'], filepath=filepath)
    elif json['soft_type'] == 'wb':
        video_path = await download_video(json['video_url'], filepath=filepath, ext_headers={
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                "referer": "https://weibo.com/"
            })
    elif json['soft_type'] == 'x':
        video_path = await download_video(json['video_url'], filepath=filepath,proxy=proxy)
    elif json['soft_type'] == 'xhs':
        video_path = await download_video(json['video_url'], filepath=filepath)
    video_json['video_path'] = video_path
    file_size_in_mb = get_file_size_mb(video_path)
    if file_size_in_mb < 10:
        video_type='video'
    elif file_size_in_mb < 30:
        video_type='video_bigger'
    elif file_size_in_mb < 100:
        video_type='file'
    else:
        video_type = 'too_big'
    video_json['type']=video_type
    return video_json


async def link_prising(url,filepath=None,proxy=None,type=None):
    json_check = copy.deepcopy(json_init)
    link_prising_json=None
    try:
        url_list = (re.findall(r"https?:[^\s\]\)]+", url))
        for url_check in url_list:
            url=url_check
            if 'b23' in url_check: break
        #print(url)
    except Exception as e:
        json_check['status'] = False
        return json_check
    #print(f'json_init:{json_init}\njson_check:{json_check}\nlink_prising_json:{link_prising_json}\n\n')
    try:
        match url:
            case url if 'bili' in url or 'b23' in url:
                link_prising_json = await bilibili(url, filepath=filepath)
            case url if 'douyin' in url:
                link_prising_json = await dy(url, filepath=filepath)
            case url if 'weibo' in url:
                link_prising_json = await wb(url, filepath=filepath)
            case url if 'xhslink' in url or 'xiaohongshu' in url:
                link_prising_json = await xiaohongshu(url, filepath=filepath)
            case url if 'x.com' in url:
                link_prising_json = await twitter(url, filepath=filepath, proxy=proxy)
            case url if 'gal.manshuo.ink/archives/' in url or 'www.hikarinagi.com' in url :
                link_prising_json = await Galgame_manshuo(url, filepath=filepath)
            case url if 'www.mysqil.com' in url:
                #link_prising_json = await youxi_pil(url, filepath=filepath)
                pass
            case _:
                pass

    except Exception as e:
        json_check['status'] = False
        json_check['reason'] = str(e)
        traceback.print_exc()
        return json_check
    if link_prising_json is not None:
        if type == 'dynamic_check':
            if '编辑于 ' in link_prising_json['time']:
                time_check=link_prising_json['time'].split("编辑于 ")[1].strip()
            else:
                time_check = link_prising_json['time']
            possible_formats = [
                "%Y年%m月%d日 %H:%M",
                "%Y/%m/%d %H:%M",
                "%Y-%m-%d %H:%M",
                "%d-%m-%Y %H:%M",
                "%Y.%m.%d %H:%M",
                "%Y年%m月%d日",
                "%Y/%m/%d",
                "%Y-%m-%d",
                "%d-%m-%Y",
                "%Y.%m.%d",
            ]

            for fmt in possible_formats:
                try:
                    # 尝试解析日期字符串
                    check_time=datetime.strptime(time_check, fmt).strftime("%Y-%m-%d")
                    #print(f"check_time:{check_time}\nnow:{datetime.now().date()}")
                    if str(check_time) != str(datetime.now().date()):
                        link_prising_json['status'] = False
                        link_prising_json['check_time']=check_time
                        #print(f"时间不匹配，拒绝发送 {link_prising_json['time']}\ncheck_time:{check_time}\ndatetime:{datetime.now().date()}")
                    break
                except ValueError:
                    # 如果解析失败，继续尝试下一个格式
                    #traceback.print_exc()
                    continue


        return link_prising_json
    else:
        json_check['status'] = False
        return json_check





#draw_video_thumbnail()
if __name__ == "__main__":#测试用，不用管
    url='https://t.bilibili.com/1032160407411752961?share_source=pc_native'
    #url='97 沉夕cxxx发布了一篇小红书笔记，快来看吧！ 😆 Kde9g1dqG8kAiaG 😆 http://xhslink.com/a/TOydUquIB8p5，复制本条信息，打开【小红书】App查看精彩内容！'
    url='【【温水和彦×八奈见杏菜】用心但不精致的礼物，却意外的收获了笑容-哔哩哔哩】 https://b23.tv/Zm7mYo0'
    #url='【34【PC+KR/gal推荐】《9nine》全系列分享-哔哩哔哩】 https://b23.tv/Um3ewuT'
    #url='https://www.bilibili.com/opus/975425280952762370?spm_id_from=main.mine-history.0.0.pv'
    #url='https://www.bilibili.com/opus/1031855559216726016?plat_id=186&share_from=dynamic&share_medium=iphone&share_plat=ios&share_session_id=3A30238A-7EFA-4778-9339-AEFC6E6BC886&share_source=COPY&share_tag=s_i&spmid=dt.opus-detail.0.0&timestamp=1739177704&unique_k=UfWkGLP'
    url='https://b23.tv/LELSW8u'
    url='https://b23.tv/MNARaEN'
    #url='https://b23.tv/umdU5bb'
    #url='https://b23.tv/waAdNuB'
    #url='https://b23.tv/bicqrKN'
    #url='https://b23.tv/t9YeH0m'
    url='【【明日方舟抽卡】王牌！主播在商店花300凭证单抽出了烛煌！黑子说话！】https://www.bilibili.com/video/BV1dYfUYDE96?vd_source=5e640b2c90e55f7151f23234cae319ec'
    url='https://v.douyin.com/iPhd561x'
    url='https://gal.manshuo.ink/archives/297/'
    url = 'https://www.hikarinagi.com/p/21338'
    url='https://live.bilibili.com/26178650'
    url='https://gal.manshuo.ink/archives/451/'
    url='https://t.bilibili.com/1056778966646390806'
    url='0.74 复制打开抖音，看看【齐木花卷的作品】好棒的版型.. # 穿搭 # dance # fy... https://v.douyin.com/OO5Ee2TV0a0/ 12/25 dnQ:/ o@q.Eu '
    #url='6 【如果在支援的路上碰到他们的话… - 流泪猫毛头 | 小红书 - 你的生活指南】 😆 tF8W8BXfdBxCnv4 😆 https://www.xiaohongshu.com/discovery/item/67e0146c000000000b016af1?source=webshare&xhsshare=pc_web&xsec_token=ABM5sWfqwfUeG8RzcI666DLkKic1rMvcV0DboQigwq3wY=&xsec_source=pc_share'

    asyncio.run(link_prising(url))
    #asyncio.run(youxi_pil_new_text())


    url='44 【来抄作业✨早秋彩色衬衫叠穿｜时髦知识分子风 - 杨意子_ | 小红书 - 你的生活指南】 😆 Inw56apL6vWYuoS 😆 https://www.xiaohongshu.com/discovery/item/64c0e9c0000000001201a7de?source=webshare&xhsshare=pc_web&xsec_token=AB8GfF7dOtdlB0n_mqoz61fDayAXpCqWbAz9xb45p6huE=&xsec_source=pc_share'
    url='79 【感谢大数据！椰青茉莉也太太太好喝了吧 - 胖琪琪 | 小红书 - 你的生活指南】 😆 78VORl9ln3YDBKi 😆 https://www.xiaohongshu.com/discovery/item/63dcee03000000001d022015?source=webshare&xhsshare=pc_web&xsec_token=ABJoHbAtOG98_7RnFR3Mf2MuQ1JC8tRVlzHPAG5BGKdCc=&xsec_source=pc_share'
    #asyncio.run(xiaohongshu(url))
    #asyncio.run(link_prising(url))

