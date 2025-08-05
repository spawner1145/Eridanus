import httpx
import re
import copy
import asyncio
from .login_core import ini_login_Link_Prising
from .common import json_init,filepath_init,COMMON_HEADER,GLOBAL_NICKNAME
from urllib.parse import urlparse
from urllib.parse import parse_qs
from datetime import datetime, timedelta
from developTools.utils.logger import get_logger
logger=get_logger()
import json
from framework_common.manshuo_draw.manshuo_draw import manshuo_draw
from run.resource_collector.service.engine_search import html_read
import traceback
import random
from bs4 import BeautifulSoup
import os
import time
from .common import name_qq_list,card_url_list






async def Galgame_manshuo(url,filepath=None):
    contents=[]
    json_check = copy.deepcopy(json_init)
    json_check['status'] = True
    json_check['video_url'] = False
    if filepath is None: filepath = filepath_init
    link = (re.findall(r"https?://[^\s\]\)]+", url))[0]
    if link =="https://gal.manshuo.ink":return
    context = await html_read(link)
    if '请求发生错误：' in context:
        #print(context)
        json_check['status'] = False
        return json_check
    context = context.split("\n")
    context_check_middle=''
    links_url = None
    Title=''
    avatar_name_flag=0
    time_flag=0
    desc_flag=0
    desc=''
    desc_number=0
    hikarinagi_flag=0
    time_gal='未知'

    if 'gal.manshuo.ink' in url:
        type_software='世伊Galgame论坛'
        type_color=(251, 114, 153, 80)
        avatar_name = '世伊Galgame论坛'
        json_check['soft_type'] = '世伊Galgame论坛'
    elif'www.hikarinagi.com' in url:
        type_software = 'Hikarinagi论坛'
        type_color = (102, 204, 255, 80)
        avatar_name = 'Hikarinagi社区'
        json_check['soft_type'] = 'Hikarinagi论坛'
    elif 'www.mysqil.com' in url:
        type_software = '有希日记'
        type_color = (241, 87, 178, 80)
        avatar_name = '有希日记 - 读书可以改变人生！'
        json_check['soft_type'] = '有希日记'
        try:
            #from plugins.streaming_media_service.Link_parsing.core.selenium_core import scrape_images_get_url
            #links_url_list = scrape_images_get_url(url)
            #links_url = links_url_list[0]
            pass
        except Exception as e:
            links_url = None
            traceback.print_exc()
            print(f"链接获取失败，错误: {e}")


    for context_check in context:
        #print(context_check)
        if time_flag ==1:
            time_flag=2
            time_gal=context_check.replace(" ", "")
            if '[' in context_check:
                time_flag = 1
        if context_check_middle !='':
            if '发表于' in context_check :
                Title=context_check_middle.replace(" ", "")
                time_flag=1
            elif ('[avatar]' in context_check) and time_flag==0:
                Title=context_check_middle.replace(" ", "")
                time_flag=1
        context_check_middle=context_check

        if ('作者:' in context_check or '[avatar]' in context_check) and avatar_name_flag==0:
            avatar_name_flag=1
            if 'https://www.manshuo.ink/img/' in context_check:
                avatar_name_flag = 0
        elif avatar_name_flag==1:
            avatar_name_flag=2
            match = re.search(r"\[(.*?)\]", context_check)
            if match:
                avatar_name=match.group(1).replace(" ", "")

        if '故事介绍' in context_check or '<img src="https://img-static.hikarinagi.com/uploads/2024/08/aca2d187ca20240827180105.jpg"' in context_check:
            if desc_flag == 0:
                desc_flag=1
        elif '[关于](' in context_check and time_flag==2:
            desc_flag=3
        elif 'Hello!有希日記へようこそ!' in context_check:
            #print('检测到标志')
            desc_flag= 10
        elif 'Staff' in context_check:
            desc_flag=0
        elif desc_flag==1:
            context_check=context_check.replace(" ", "")
            if not ('https:'in context_check or 'data:image/svg+xml' in context_check or '插画欣赏' in context_check):
                for i in context_check:
                    desc_number+=1
                if 'ePub格式-连载' in context_check or '作者:' == context_check or '文章链接:' == context_check or '游戏资源' in context_check:
                    desc_flag = 0
                #print(context_check,desc_flag)
                if desc_number > 200 and desc_flag != 0:
                    desc_flag = 0
                    desc +=f'{context_check}…\n'
                else:
                    desc += f'{context_check}\n'
        elif desc_flag != 1:
            desc_flag-=1
        flag = 0
        #print(desc_flag)
        if '登陆后才可以评论获取资源哦～～' in context_check:
            hikarinagi_flag = 1
        elif 'https://gal.manshuo.ink/usr/uploads/galgame/' in context_check:
            if hikarinagi_flag == 0:
                for name_check in {'chara', 'title_page', '图片'}:
                    if f'{name_check}' in context_check: flag = 1
                if flag == 1: continue
                links_url = (re.findall(r"https?://[^\s\]\)]+", context_check))[0]
                image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp')
                if not links_url.lower().endswith(image_extensions):
                    links = re.findall(r'\((https?://[^\)]+)\)', context_check)
                    links_url=links[0]
                hikarinagi_flag = 1
        elif 'https://img-static.hikarinagi.com/uploads/' in context_check:
            if hikarinagi_flag == 0:
                links_url = (re.findall(r"https?://[^\s\]\)]+", context_check))[0]
                Title = context_check.replace(" ", "").replace(f"{links_url}", "").replace("[", "").replace("]", "").replace(" - Hikarinagi", "").replace("(", "").replace(")", "")
                hikarinagi_flag=1

    #print(f'links_url:{links_url}')
    if links_url is None:
        try:
            for context_check in context:
                flag = 0
                if 'https://gal.manshuo.ink/usr/uploads/' in context_check:
                    for name_check in {'chara', 'title_page', '图片'}:
                        if f'{name_check}' in context_check: flag = 1
                    if flag == 1: continue
                    #print(f'context_check:{context_check}')
                    links = re.findall(r"https?://[^\s\]\)]+", context_check)
                    #print(f'links:{links}')
                    links_url = links[0]
                    break
        except:
            pass
        finally:
            if links_url is None:
                links_url='https://gal.manshuo.ink/usr/uploads/galgame/zatan.png'
    contents.append(f"title:{Title}")
    contents.append(desc)
    context=f'[title]{Title}[/title]\n{desc}'
    #print(f'final links_url:{links_url}')
    if avatar_name in name_qq_list:
        for name_check in name_qq_list:
            if avatar_name in name_check:
                qq_number=name_qq_list[name_check]
        avatar_path_url=f"https://q1.qlogo.cn/g?b=qq&nk={qq_number}&s=640"
    elif 'www.mysqil.com' in url:
        avatar_path_url = f"https://q1.qlogo.cn/g?b=qq&nk=3231515355&s=640"
    else:
        avatar_path_url='https://gal.manshuo.ink/usr/uploads/galgame/img_master.jpg'

    card_url=card_url_list[random.randint(0,len(card_url_list)-1)]

    json_check['pic_path'] = await manshuo_draw([
        {'type': 'avatar', 'subtype': 'common', 'img': [avatar_path_url], 'upshift_extra': 20,
         'content': [f"[name]{avatar_name}[/name]\n[time]{time_gal}[/time]"]},
        {'type': 'img', 'subtype': 'common_with_des_right', 'img': [links_url], 'content': [context]}])
    return json_check

async def youxi_pil_new_text(filepath=None):
    contents=[]
    json_check = copy.deepcopy(json_init)
    json_check['status'] = True
    json_check['video_url'] = False
    if filepath is None: filepath = filepath_init
    async with httpx.AsyncClient() as client:
        try:
            url_rss = f"https://www.mysqil.com/wp-json/wp/v2/posts"
            response = await client.get(url_rss)
            if response.status_code:
                data = response.json()
                #print(data)
                #print(json.dumps(data[0], indent=4))
                rss_context=data[0]
        except Exception as e:
            json_check['status'] = False
            return json_check
        for rss_text in rss_context:
            #print(rss_text,rss_context[rss_text])
            pass
        #print(rss_context['_links']['author'][0]['href'])
        Title=rss_context['title']['rendered']
        desc = BeautifulSoup(rss_context['excerpt']['rendered'], 'html.parser').get_text().replace(" [&hellip;]", "")
        desc=desc.replace("插画欣赏 作品简介 ", "")
        truncated_text = desc[:200]
        if len(desc) > 200:truncated_text += "..."
        words = truncated_text.split(' ')
        desc_result=''
        for word in words:
            if word !='':
                desc_result+=f'{word}\n'
        context = f'[title]{Title}[/title]\n{desc_result}'

        soup = BeautifulSoup(rss_context['content']['rendered'], 'html.parser')
        data_src_values = [img['data-src'] for img in soup.find_all('img', {'data-src': True})]

        time_gal=rss_context['date']
        type_software = '有希日记'
        type_color = (241, 87, 178, 80)
        json_check['soft_type'] = '有希日记'
        response = await client.get(rss_context['_links']['author'][0]['href'])
        if response.status_code:
            author_data = response.json()
            #print(json.dumps(author_data, indent=4))
            author_url=author_data['avatar_urls']['96']
            #print(author_url)
            avatar_name=author_data['name']

        json_dy = {'status': False, 'pendant_path': False, 'card_path': False, 'card_number': False,
                   'card_color': False,
                   'card_is_fan': False}

        #card_url = card_url_list[random.randint(0, len(card_url_list) - 1)]

        json_check['pic_path'] = await manshuo_draw([
            {'type': 'avatar', 'subtype': 'common', 'img': [author_url], 'upshift_extra': 20,
             'content': [f"[name]{avatar_name}[/name]\n[time]{time_gal}[/time]"]},
            {'type': 'img', 'subtype': 'common_with_des_right', 'img': [data_src_values[0]], 'content': [context]}])

        #print(json.dumps(json_check, indent=4))
        return json_check



async def gal_PILimg(text=None,img_context=None,filepath=None,proxy=None,type_soft='Bangumi 番剧',name=None,url=None,
                         type=None,target=None,search_type=None):
    contents=[]
    json_check = copy.deepcopy(json_init)
    json_check['soft_type'] = 'Galgame'
    json_check['status'] = True
    json_check['video_url'] = False
    if filepath is None: filepath = filepath_init
    if name is not None:
        if os.path.isfile(f'{filepath}{name}.png'):
            json_check['pic_path'] = f'{filepath}{name}.png'
            return json_check
    else:
        name = f'{int(time.time())}'
    if type is None:
        title=text.split("gid")[0]
        contents.append(f"title:{title}")
        desc=text.split("简介如下：")[1]
        if '开发商：' in text:
            developer=text.split("开发商：")[1].replace(desc,'').replace('简介如下：','')
            title +=f'\n开发商：{developer}'
        context = f'[title]{title}[/title]\n{desc}'
        json_check['pic_path'] = await manshuo_draw([{'type': 'img', 'subtype': 'common_with_des', 'img': img_context, 'content': [context],'max_des_length':2000}])
        return json_check