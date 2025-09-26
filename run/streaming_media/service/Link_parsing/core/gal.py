import gc

import httpx
import re
import copy
import asyncio

#from test1 import analyze_objects
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




URL_PATTERN = re.compile(r"https?://[^\s\]\)]+")
BRACKET_PATTERN = re.compile(r"\[(.*?)\]")
PAREN_PATTERN = re.compile(r'\((https?://[^\)]+)\)')

async def Galgame_manshuo(url, filepath=None):
    # 使用浅拷贝替代深拷贝，减少内存占用
    json_check = json_init.copy()
    json_check['status'] = True
    json_check['video_url'] = False

    if filepath is None:
        filepath = filepath_init

    # 使用预编译的正则表达式
    url_matches = URL_PATTERN.findall(url)
    if not url_matches:
        json_check['status'] = False
        return json_check

    link = url_matches[0]
    # 立即清理url_matches
    del url_matches

    if link == "https://gal.manshuo.ink":
        return json_check
    #analyze_objects(0.1) #通过，一切正常
    try:
        context = await html_read(link)
        if '请求发生错误：' in context:
            json_check['status'] = False
            return json_check

        #analyze_objects(0.2) #删除该对象后即可
        # 初始化变量
        context_check_middle = ''
        links_url = None
        Title = ''
        avatar_name_flag = 0
        time_flag = 0
        desc_flag = 0
        desc_parts = []  # 使用列表收集描述片段，最后一次性join
        desc_number = 0
        hikarinagi_flag = 0
        time_gal = '未知'

        # 根据URL确定软件类型
        if 'gal.manshuo.ink' in url:
            type_software = '世伊Galgame论坛'
            type_color = (251, 114, 153, 80)
            avatar_name = '世伊Galgame论坛'
            json_check['soft_type'] = '世伊Galgame论坛'
        elif 'www.hikarinagi.com' in url:
            type_software = 'Hikarinagi论坛'
            type_color = (102, 204, 255, 80)
            avatar_name = 'Hikarinagi社区'
            json_check['soft_type'] = 'Hikarinagi论坛'
        elif 'www.mysqil.com' in url:
            type_software = '有希日记'
            type_color = (241, 87, 178, 80)
            avatar_name = '有希日记 - 读书可以改变人生！'
            json_check['soft_type'] = '有希日记'


        # 使用迭代器处理行，避免一次性存储所有行
        context_lines = context.split("\n")
        del context

        gc.collect()
        #analyze_objects(1.1)
        # 主要解析循环
        for i, context_check in enumerate(context_lines):
            # 定期清理已处理的行（每100行清理一次）
            if i > 0 and i % 100 == 0:
                # 将已处理的行设置为None以释放内存
                for j in range(max(0, i - 100), i):
                    context_lines[j] = None
                gc.collect()

            # 处理时间标志
            if time_flag == 1:
                time_flag = 2
                time_gal = context_check.strip()  # 使用strip替代replace(" ", "")
                if '[' in context_check:
                    time_flag = 1

            # 处理标题
            if context_check_middle:
                if '发表于' in context_check:
                    Title = context_check_middle.strip()
                    time_flag = 1
                elif '[avatar]' in context_check and time_flag == 0:
                    Title = context_check_middle.strip()
                    time_flag = 1

            context_check_middle = context_check

            # 处理头像名称
            if ('作者:' in context_check or '[avatar]' in context_check) and avatar_name_flag == 0:
                avatar_name_flag = 1
                if 'https://www.manshuo.ink/img/' in context_check:
                    avatar_name_flag = 0
            elif avatar_name_flag == 1:
                avatar_name_flag = 2
                match = BRACKET_PATTERN.search(context_check)
                if match:
                    avatar_name = match.group(1).strip()
                    # 立即清理match对象
                    del match

            # 处理描述
            if '故事介绍' in context_check or '<img src="https://img-static.hikarinagi.com/uploads/2024/08/aca2d187ca20240827180105.jpg"' in context_check:
                if desc_flag == 0:
                    desc_flag = 1
            elif '[关于](' in context_check and time_flag == 2:
                desc_flag = 3
            elif 'Hello!有希日記へようこそ!' in context_check:
                desc_flag = 10
            elif 'Staff' in context_check:
                desc_flag = 0
            elif desc_flag == 1:
                context_check_clean = context_check.strip()
                if not any(keyword in context_check_clean for keyword in ['https:', 'data:image/svg+xml', '插画欣赏']):
                    desc_number += len(context_check_clean)

                    if any(keyword in context_check_clean for keyword in
                           ['ePub格式-连载', '作者:', '文章链接:', '游戏资源']):
                        desc_flag = 0
                    elif desc_number > 200 and desc_flag != 0:
                        desc_flag = 0
                        desc_parts.append(f'{context_check_clean}…')
                        # 立即清理临时变量
                        del context_check_clean
                        break
                    else:
                        desc_parts.append(context_check_clean)
                # 清理临时变量
                del context_check_clean
            elif desc_flag > 1:
                desc_flag -= 1

            # 处理链接URL
            if '登陆后才可以评论获取资源哦～～' in context_check:
                hikarinagi_flag = 1
            elif 'https://gal.manshuo.ink/usr/uploads/galgame/' in context_check and hikarinagi_flag == 0:
                if not any(name in context_check for name in ['chara', 'title_page', '图片']):
                    url_matches = URL_PATTERN.findall(context_check)
                    if url_matches:
                        potential_url = url_matches[0]
                        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp')
                        if not potential_url.lower().endswith(image_extensions):
                            paren_matches = PAREN_PATTERN.findall(context_check)
                            if paren_matches:
                                potential_url = paren_matches[0]
                                del paren_matches
                        links_url = potential_url
                        hikarinagi_flag = 1
                        # 清理临时变量
                        del url_matches, potential_url
            elif 'https://img-static.hikarinagi.com/uploads/' in context_check and hikarinagi_flag == 0:
                url_matches = URL_PATTERN.findall(context_check)
                if url_matches:
                    links_url = url_matches[0]
                    # 优化字符串处理
                    Title = context_check.replace(links_url, "").strip("[] () - Hikarinagi")
                    hikarinagi_flag = 1
                    del url_matches

        #analyze_objects(2)  #占用略微增加，删除context_lines后即可

        # 清理context_lines
        del context_lines
        # 强制垃圾回收
        gc.collect()

        # 如果没有找到链接，尝试备用搜索
        if links_url is None:
            try:
                context_backup = await html_read(link)
                backup_lines = context_backup.split("\n")
                # 立即删除备份context
                del context_backup

                for context_check in backup_lines:
                    if 'https://gal.manshuo.ink/usr/uploads/' in context_check:
                        if not any(name in context_check for name in ['chara', 'title_page', '图片']):
                            url_matches = URL_PATTERN.findall(context_check)
                            if url_matches:
                                links_url = url_matches[0]
                                del url_matches
                                break
                del backup_lines
                # 强制垃圾回收
                gc.collect()
            except Exception:
                pass

            # 设置默认链接
            if links_url is None:
                links_url = 'https://gal.manshuo.ink/usr/uploads/galgame/zatan.png'

        # 组装描述
        desc = '\n'.join(desc_parts) if desc_parts else ''
        del desc_parts  # 清理描述部分列表
        # 组装最终内容
        context_final = f'[title]{Title}[/title]\n[des]{desc}[/des]'
        # 处理头像路径
        if avatar_name in name_qq_list:
            for name_check in name_qq_list:
                if avatar_name in name_check:
                    qq_number = name_qq_list[name_check]
                    avatar_path_url = f"https://q1.qlogo.cn/g?b=qq&nk={qq_number}&s=640"
                    break
        elif 'www.mysqil.com' in url:
            avatar_path_url = "https://q1.qlogo.cn/g?b=qq&nk=3231515355&s=640"
        else:
            avatar_path_url = 'https://gal.manshuo.ink/usr/uploads/galgame/img_master.jpg'

        # 随机选择卡片URL
        # card_url = card_url_list[random.randint(0, len(card_url_list) - 1)]

        # 调用analyze_objects
        #analyze_objects(3) #此时占用已经正常

        # 生成图片
        json_check['pic_path'] = await manshuo_draw([
            {'type': 'avatar', 'subtype': 'common', 'img': [avatar_path_url], 'upshift_extra': 20,
             'content': [f"[name]{avatar_name}[/name]\n[time]{time_gal}[/time]"]},
            {'type': 'img', 'subtype': 'common_with_des_right', 'img': [links_url], 'content': [context_final]}
        ])

        # 在返回前进行最终的垃圾回收
        # 清理所有局部变量
        locals_to_clear = [
            'context_check_middle', 'Title', 'avatar_name_flag', 'time_flag', 'desc_flag',
            'desc_number', 'hikarinagi_flag', 'time_gal', 'type_software', 'type_color',
            'avatar_name', 'desc', 'avatar_path_url','context_final', 'links_url',
        ]

        for var_name in locals_to_clear:
            if var_name in locals():
                del locals()[var_name]

        # 强制进行两次垃圾回收
        gc.collect()
        gc.collect()

        return json_check

    except Exception as e:
        print(f"处理过程中发生错误: {e}")
        traceback.print_exc()
        json_check['status'] = False
        # 异常情况下也要进行垃圾回收
        gc.collect()
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
            avatar_name=author_data['name']
        author_url = "https://q1.qlogo.cn/g?b=qq&nk=3231515355&s=640"

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
        json_check['pic_path'] = await manshuo_draw([{'type': 'backdrop', 'subtype': 'one_color'},
                                                     {'type': 'img', 'subtype': 'common_with_des', 'img': img_context, 'content': [context],'max_des_length':2000}])
        return json_check

if __name__ == "__main__":#测试用，不用管


    asyncio.run(youxi_pil_new_text())