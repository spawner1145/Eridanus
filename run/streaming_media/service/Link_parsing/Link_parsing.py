import sys
import asyncio
import copy
import re
from bilibili_api.exceptions import ResponseCodeException
from datetime import datetime
import traceback
from developTools.utils.logger import get_logger
import pprint
from run.streaming_media.service.Link_parsing.core import *
import os
try:
    from bilibili_api import select_client
    select_client("httpx")
except ImportError:
    #旧版本兼容问题，整合包更新后删除此部分代码
    pass
logger=get_logger("Link_parsing")
linking_cache = {}
import time
from run.streaming_media.service.Link_parsing.core.common import json_init

async def link_prising(url,filepath=None,proxy=None,type=None,credential_bili=None,re_prising=False):
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
    #为链接解析添加缓存
    url = str(url)
    global linking_cache
    #pprint.pprint(linking_cache)

    if re_prising is True and url in linking_cache:
        linking_cache.pop(url)
    if url in linking_cache:
        #代表有缓存，开始判断返回
        try:
            if type != 'QQ_Check' and os.path.exists(linking_cache[url]['path']):
                return linking_cache[url]['info']
        except:pass
        if type == 'QQ_Check':
            return linking_cache[url]['info']
        linking_cache.pop(url)
    try:
        match url:
            case url if 'bili' in url or 'b23' in url:
                logger.info(f"解析bilibili链接:{url}")
                link_prising_json = await bilibili(url, filepath=filepath,type=type,credential_bili=None)
            case url if 'douyin' in url:
                logger.info(f"解析抖音链接:{url}")
                link_prising_json = await dy(url, filepath=filepath,type_check=type)
            case url if 'weibo' in url:
                logger.info(f"解析微博链接:{url}")
                link_prising_json = await wb(url, filepath=filepath,type_check=type)
            case url if 'xhslink' in url or 'xiaohongshu' in url:
                logger.info(f"解析小红书链接:{url}")
                link_prising_json = await xiaohongshu(url, filepath=filepath,type_check=type)
            case url if 'x.com' in url:
                logger.info(f"解析x链接:{url}")
                link_prising_json = await twitter(url, filepath=filepath, proxy=proxy,type_check=type)
            case url if 'gal.manshuo.ink/archives/' in url or 'www.hikarinagi.com' in url :
                logger.info(f"解析Galgame链接:{url}")
                link_prising_json = await Galgame_manshuo(url, filepath=filepath)
            case url if 'www.mysqil.com' in url:
                #link_prising_json = await youxi_pil(url, filepath=filepath)
                pass
            case _:
                pass
        if link_prising_json is not None and link_prising_json['status'] is True and 'pic_path' in link_prising_json:
            linking_cache[url] = {'info':copy.deepcopy(link_prising_json), 'time':time.time(), 'path':link_prising_json['pic_path']}
    except ResponseCodeException as e:
        print(f"B站解析接口返回错误代码: {e.code}")
        json_check['status'] = False
        json_check['reason'] = str(e)
        json_check['code'] = e.code
        #traceback.print_exc()
        return json_check
    except Exception as e:
        json_check['status'] = False
        json_check['reason'] = str(e)
        #traceback.print_exc()
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

        logger.info(f"解析完成，返回识别结果")
        return link_prising_json
    else:
        json_check['status'] = False
        return json_check





#draw_video_thumbnail()
if __name__ == "__main__":#测试用，不用管

    url='https://gal.manshuo.ink/archives/297/'
    url = 'https://www.hikarinagi.com/p/21338'
    url='https://live.bilibili.com/26178650'
    url='https://gal.manshuo.ink/archives/451/'
    url='https://t.bilibili.com/1056778966646390806'
    #url='0.74 复制打开抖音，看看【齐木花卷的作品】好棒的版型.. # 穿搭 # dance # fy... https://v.douyin.com/OO5Ee2TV0a0/ 12/25 dnQ:/ o@q.Eu '
    url='https://www.xiaohongshu.com/discovery/item/67e0146c000000000b016af1?source=webshare&xhsshare=pc_web&xsec_token=ABM5sWfqwfUeG8RzcI666DLkKic1rMvcV0DboQigwq3wY=&xsec_source=pc_share'
    url='http://xhslink.com/a/HoZpetY3jCUfb'
    url='【【绫地宁宁 / 手书预告】恋爱裁判】https://www.bilibili.com/video/BV1JBMVzVEZr?vd_source=5e640b2c90e55f7151f23234cae319ec'
    url='https://live.bilibili.com/1947172143'
    url='https://t.bilibili.com/1082791822623768624?share_source=pc_native'
    url = 'https://gal.manshuo.ink/archives/746/'
    url = 'https://weibo.com/6625787085/5245617985290482'
    url = 'https://x.com/hn_luotianyi712/status/2003787316100509941?s=46'
    url = 'https://x.com/h_ta6_h_h_ta6_h/status/2004134080229908552?s=46'
    url = 'https://live.bilibili.com/32461978'
    info = asyncio.run(link_prising(url))
    pprint.pprint(info)
    #asyncio.run(youxi_pil_new_text())


    url='44 【来抄作业✨早秋彩色衬衫叠穿｜时髦知识分子风 - 杨意子_ | 小红书 - 你的生活指南】 😆 Inw56apL6vWYuoS 😆 https://www.xiaohongshu.com/discovery/item/64c0e9c0000000001201a7de?source=webshare&xhsshare=pc_web&xsec_token=AB8GfF7dOtdlB0n_mqoz61fDayAXpCqWbAz9xb45p6huE=&xsec_source=pc_share'
    url='79 【感谢大数据！椰青茉莉也太太太好喝了吧 - 胖琪琪 | 小红书 - 你的生活指南】 😆 78VORl9ln3YDBKi 😆 https://www.xiaohongshu.com/discovery/item/63dcee03000000001d022015?source=webshare&xhsshare=pc_web&xsec_token=ABJoHbAtOG98_7RnFR3Mf2MuQ1JC8tRVlzHPAG5BGKdCc=&xsec_source=pc_share'
    #asyncio.run(xiaohongshu(url))
    #asyncio.run(link_prising(url))

