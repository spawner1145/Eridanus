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
import sys
import time
from bilibili_api import video, live, article
from bilibili_api import dynamic
from bilibili_api.opus import Opus
from bilibili_api.video import VideoDownloadURLDataDetecter
from .bili import bili_init,av_to_bv,download_b,info_search_bili
from .common import name_qq_list,card_url_list,add_append_img,download_video,get_file_size_mb,download_img
try:
    from bilibili_api import select_client
    select_client("httpx")
except ImportError:
    #旧版本兼容问题，整合包更新后删除此部分代码
    pass
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def bilibili(url,filepath=None,is_twice=None,type=None):
    """
        哔哩哔哩解析
    :param bot:
    :param event:
    :return:
    """
    # 消息
    #url: str = str(event.message).strip()
    BILIBILI_HEADER, credential,BILI_SESSDATA=await bili_init()#获取构建credential
    json_check = copy.deepcopy(json_init)
    json_check['soft_type'] = 'bilibili'
    json_check['status'] = True
    json_check['video_url'] = False
    #logger.info(f'credential: {credential}')
    if not ( 'bili' in url or 'b23' in url ):return
    #构建绘图消息链
    if filepath is None:
        filepath = filepath_init
    contents=[]
    contents_dy=[]
    emoji_list = []
    label_list,image_list,context=[],[],''
    orig_desc=None
    introduce=None
    desc=None
    avatar_json=None
    url_reg = r"(http:|https:)\/\/(space|www|live).bilibili.com\/[A-Za-z\d._?%&+\-=\/#]*"
    b_short_rex = r"(https?://(?:b23\.tv|bili2233\.cn)/[A-Za-z\d._?%&+\-=\/#]+)"
    # 处理短号、小程序问题
    if "b23.tv" in url or "bili2233.cn" in url or "QQ小程序" in url :
        b_short_url = re.search(b_short_rex, url.replace("\\", ""))[0]
        #logger.info(f'b_short_url:{b_short_url}')
        resp = httpx.get(b_short_url, headers=BILIBILI_HEADER, follow_redirects=True)
        url: str = str(resp.url)
        #print(f'url:{url}')
    # AV/BV处理
    if "av" in url:
        return
        url= 'https://www.bilibili.com/video/' + av_to_bv(url)
    if re.match(r'^BV[1-9a-zA-Z]{10}$', url):
        url = 'https://www.bilibili.com/video/' + url
    json_check['url'] = url
    # ===============发现解析的是动态，转移一下===============
    if ('t.bilibili.com' in url or '/opus' in url or '/space' in url ) and BILI_SESSDATA != '':
        # 去除多余的参数
        if '?' in url:
            url = url[:url.index('?')]
        dynamic_id = int(re.search(r'[^/]+(?!.*/)', url)[0])
        #logger.info(dynamic_id)
        dy = dynamic.Dynamic(dynamic_id, credential)
        is_opus =await dy.is_opus()#判断动态是否为图文
        json_check['url'] = f'https://t.bilibili.com/{dynamic_id}'
        #is_opus=True
        try:
            if not is_opus:#若判断为图文则换另一种方法读取
                logger.info('not opus')
                #print(dynamic_id)

                dynamic_info = await Opus(dynamic_id).get_info()
                #avatar_json = await info_search_bili(dynamic_info, is_opus,filepath=filepath,card_url_list=card_url_list)

                tags = ''
                number=0
                text_list_check=''
                if dynamic_info is not None:
                    title = dynamic_info['item']['basic']['title']
                    paragraphs = []
                    for module in dynamic_info['item']['modules']:
                        if 'module_content' in module:
                            paragraphs = module['module_content']['paragraphs']
                            break
                    #print(json.dumps(paragraphs, indent=4))
                    for desc_check in paragraphs[0]['text']['nodes']:
                        if 'word' in desc_check:
                            desc = desc_check['word']['words']
                            if f'{desc}' not in {'',' '}:
                                text_list_check+=f"{desc}"

                        elif desc_check['type'] =='TEXT_NODE_TYPE_RICH':
                            if desc_check['rich']['type'] =='RICH_TEXT_NODE_TYPE_EMOJI':
                                text_list_check += f"[emoji]{desc_check['rich']['emoji']['icon_url']}[/emoji]"
                                number += 1
                            else:
                                tags+=desc_check['rich']['text'] + ' '
                    if text_list_check != '':context += text_list_check
                    if tags != '':context += f'\n[tag]{tags}[/tag]'

                    #获取头像以及名字
                    for module in dynamic_info['item']['modules']:
                        if 'module_author' in module:
                            modules = module['module_author']
                            owner_cover,owner_name,pub_time = modules['face'],modules['name'],modules['pub_time']
                            break
                    try:
                        pics_context=paragraphs[1]['pic']['pics']
                    except :
                        pics_context=dynamic_info['item']['modules'][0]['module_top']['display']['album']['pics']
                    image_list=[item['url'] for item in pics_context]


                    if len(image_list) != 1:
                        manshuo_draw_json=[
                            {'type': 'avatar', 'subtype': 'common', 'img': [owner_cover], 'upshift_extra': 20,
                             'content': [f"[name]{owner_name}[/name]\n[time]{pub_time}[/time]"],
                             'type_software': 'bilibili', 'label': label_list}, {'type': 'text','content': [context]},{'type': 'img','img': image_list}]
                    else:
                        manshuo_draw_json=[
                            {'type': 'avatar', 'subtype': 'common', 'img': [owner_cover], 'upshift_extra': 20,
                             'content': [f"[name]{owner_name}[/name]\n[time]{pub_time}[/time]"],
                             'type_software': 'bilibili', },
                            {'type': 'img', 'subtype': 'common_with_des_right', 'img': image_list,
                             'content': [context]}]
                    if is_twice is not True:
                        json_check['pic_path'] = await manshuo_draw(manshuo_draw_json)
                        json_check['time'] = pub_time
                        json_check['pic_url_list'] = image_list
                        return json_check
                    return manshuo_draw_json

        except Exception as e:
            logger.error(f"{e}, 尝试使用其他方式解析")
            is_opus=True


        if is_opus:
            dynamic_info = await dy.get_info()
            logger.info('is opus')
            #print(json.dumps(dynamic_info, indent=4))
            orig_check=1        #判断是否为转发，转发为2
            type_set=None
            if dynamic_info is not None:
                paragraphs = []
                for module in dynamic_info['item']:
                    if 'orig' in module:
                        orig_check=2
                        orig_context=dynamic_info['item'][module]
                for module in dynamic_info['item']['modules']:
                    if 'module_dynamic' in module:
                        if orig_check==1:
                            type_set=13
                        elif orig_check==2:
                            paragraphs = dynamic_info['item']['modules']['module_dynamic']
                            type_set=14
                        break
                #获取头像以及名字
                owner_cover=dynamic_info['item']['modules']['module_author']['face']
                owner_name=dynamic_info['item']['modules']['module_author']['name']
                pub_time=dynamic_info['item']['modules']['module_author']['pub_time']
                if orig_check ==1:
                    #avatar_json = await info_search_bili(dynamic_info, is_opus, filepath=filepath,card_url_list=card_url_list)
                    #print('非转发')
                    type_software='bilibili 动态'
                    if 'opus' in dynamic_info['item']['modules']['module_dynamic']['major']:
                        opus_paragraphs = dynamic_info['item']['modules']['module_dynamic']['major']['opus']
                        text_list_check = ''
                        pics_context=[]
                        #print(json.dumps(opus_paragraphs, indent=4))


                        for text_check in opus_paragraphs['summary']['rich_text_nodes']:
                            #print('\n\n')
                            if 'emoji' in text_check:
                                text_list_check += f"[emoji]{text_check['emoji']['icon_url']}[/emoji]"
                            elif 'orig_text' in text_check:
                                text_list_check += text_check['orig_text']
                        #print(text_list_check)
                        if dynamic_info['item']['type'] == 'DYNAMIC_TYPE_ARTICLE':
                            type_software = 'BiliBili 专栏'
                            context += f"[title]{opus_paragraphs['title']}[/title]\n"
                            context += text_list_check
                            for pic_check in opus_paragraphs['pics']:
                                pics_context.append(pic_check['url'])
                            image_list = [item for item in pics_context]
                        else:
                            context += text_list_check
                            for pic_check in opus_paragraphs['pics']:
                                pics_context.append(pic_check['url'])
                            image_list = [item for item in pics_context]
                    elif 'live_rcmd' in dynamic_info['item']['modules']['module_dynamic']['major']:
                        live_paragraphs = dynamic_info['item']['modules']['module_dynamic']['major']['live_rcmd']
                        content = json.loads(live_paragraphs['content'])
                        #print(json.dumps(content['live_play_info'], indent=4))
                        title,cover,pub_time = content['live_play_info']['title'],content['live_play_info']['cover'],content['live_play_info']['live_start_time']
                        parent_area_name,area_name=content['live_play_info']['parent_area_name'],content['live_play_info']['area_name']
                        image_list = [cover]
                        context += f"[title]{title}[/title]\n[des]{parent_area_name} {area_name}[/des]"
                        pub_time = datetime.fromtimestamp(pub_time).astimezone().strftime("%Y-%m-%d %H:%M:%S")
                        type_software = '直播'
                    else:
                        paragraphs = dynamic_info['item']['modules']['module_dynamic']['major']['archive']
                        title,desc,cover,bvid=paragraphs['title'],paragraphs['desc'],paragraphs['cover'],paragraphs['bvid']
                        image_list = [cover]
                        context += f"[title]{title}[/title]\n[des]{desc}[/des]"
                        type_software = 'BiliBili 投稿'
                    if len(image_list) == 1 and type_software in {'直播',}:
                        manshuo_draw_json=[
                                {'type': 'avatar', 'subtype': 'common', 'img': [owner_cover], 'upshift_extra': 20,
                                 'content': [f"[name]{owner_name}[/name]\n[time]{pub_time}[/time]"],
                                 'type_software': 'bilibili', },
                                {'type': 'img', 'subtype': 'common_with_des_right', 'img': image_list, 'label': [type_software],
                                 'content': [context]}]
                    elif len(image_list) == 1 and type_software in {'BiliBili 投稿'}:
                        manshuo_draw_json=[
                                {'type': 'avatar', 'subtype': 'common', 'img': [owner_cover], 'upshift_extra': 20,
                                 'content': [f"[name]{owner_name}[/name]\n[time]{pub_time}[/time]"],
                                 'type_software': 'bilibili', },
                                {'type': 'img', 'subtype': 'common_with_des', 'img': image_list, 'label': [type_software],
                                 'content': [context]}]
                    else:
                        manshuo_draw_json=[
                            {'type': 'avatar', 'subtype': 'common', 'img': [owner_cover], 'upshift_extra': 20,
                             'content': [f"[name]{owner_name}[/name]\n[time]{pub_time}[/time]"],
                             'type_software': 'bilibili'},{'type': 'text','content': [context]},{'type': 'img','img': image_list}]

                    if is_twice is not True:
                        json_check['pic_path'] = await manshuo_draw(manshuo_draw_json)
                        json_check['time'] = pub_time
                        json_check['pic_url_list'] = image_list
                        return json_check
                    return manshuo_draw_json
                elif orig_check ==2:
                    #print(json.dumps(paragraphs, indent=4))
                    text_list_check = ''
                    for text_check in paragraphs['desc']['rich_text_nodes']:
                        if 'emoji' in text_check:
                            text_list_check += f"[emoji]{text_check['emoji']['icon_url']}[/emoji]"
                        elif 'orig_text' in text_check:
                            text_list_check += text_check['orig_text']
                    #contents.append(text_list_check)
                    #print(text_list_check)

                    for module in orig_context['modules']:
                        if 'module_dynamic' in module:
                            if 'opus' in orig_context['modules']['module_dynamic']['major']:
                                opus_orig_paragraphs=orig_context['modules']['module_dynamic']['major']['opus']
                                orig_title=opus_orig_paragraphs['summary']['text']
                                context += f"{orig_title}"
                                #logger.info(opus_orig_paragraphs)
                                image_list = [item['url'] for item in opus_orig_paragraphs['pics']]
                            else:
                                orig_paragraphs = orig_context['modules']['module_dynamic']['major']['archive']
                                orig_title, orig_desc, orig_cover, orig_bvid = orig_paragraphs['title'], orig_paragraphs['desc'], orig_paragraphs['cover'], orig_paragraphs['bvid']
                                image_list=[orig_cover]
                                context += f"[title]{orig_title}[/title]\n{orig_desc}"
                                try:
                                    pics_context = paragraphs[1]['pic']['pics']
                                except KeyError:
                                    pics_context = []
                                image_list = await add_append_img(image_list,[item['url'] for item in pics_context])

                    orig_pub_time=orig_context['modules']['module_author']['pub_time']
                    orig_owner_name = orig_context['modules']['module_author']['name']
                    orig_owner_cover = orig_context['modules']['module_author']['face']


                    if is_twice is True:
                        if orig_pub_time == '': orig_pub_time = pub_time
                        if len(image_list) != 1:
                            manshuo_draw_json = [
                                {'type': 'avatar', 'subtype': 'common', 'img': [orig_owner_cover], 'upshift_extra': 20,
                                 'content': [f"[name]{orig_owner_name}[/name]\n[time]{orig_pub_time}[/time]"],
                                 'type_software': 'bilibili', 'label': label_list},{'type': 'text','content': [context]},{'type': 'img','img': image_list}]
                        else:
                            manshuo_draw_json = [
                                {'type': 'avatar', 'subtype': 'common', 'img': [orig_owner_cover], 'upshift_extra': 20,
                                 'content': [f"[name]{orig_owner_name}[/name]\n[time]{orig_pub_time}[/time]"],
                                 'type_software': 'bilibili', },
                                {'type': 'img', 'subtype': 'common_with_des_right', 'img': image_list,
                                 'content': [context]}]
                        return manshuo_draw_json

                    orig_url= 'orig_url:'+'https://t.bilibili.com/' + orig_context['id_str']
                    manshuo_draw_json2=await bilibili(orig_url,f'{filepath}orig_',is_twice=True)

                    manshuo_draw_json = [
                        {'type': 'avatar', 'subtype': 'common', 'img': [owner_cover], 'upshift_extra': 20,
                         'content': [f"[name]{owner_name}[/name]  [time]{pub_time}[/time]"],'avatar_size':50,
                         'label': label_list}, {'type': 'text','content': [text_list_check]}]

                    json_check['pic_path'] = await manshuo_draw(await add_append_img(manshuo_draw_json,manshuo_draw_json2,layer=2))
                    json_check['time'] = pub_time
                    return json_check

        return None

    # 直播间识别
    if 'live' in url:
        room_id = re.search(r'\/(\d+)$', url).group(1)
        room = live.LiveRoom(room_display_id=int(room_id))
        data_get_url_context=await room.get_room_info()

        room_info = data_get_url_context['room_info']
        title, cover, keyframe = room_info['title'], room_info['cover'], room_info['keyframe']
        owner_name,owner_cover = data_get_url_context['anchor_info']['base_info']['uname'], data_get_url_context['anchor_info']['base_info']['face']
        area_name,parent_area_name=room_info['area_name'],room_info['parent_area_name']

        #print(f'owner_cover:{owner_cover}\ncover:{cover}')

        if cover =='':
            cover='https://gal.manshuo.ink/usr/uploads/galgame/img/bili-logo.webp'
        context += f'[title]{title}[/title]\n[des]{parent_area_name} {area_name}[/des]'

        if f'{room_info["live_status"]}' == '1':
            live_status, live_start_time = room_info['live_status'], room_info['live_start_time']
            pub_time = datetime.fromtimestamp(live_start_time).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        else:pub_time='暂未开启直播'
        manshuo_draw_json = [
            {'type': 'avatar', 'subtype': 'common', 'img': [owner_cover], 'upshift_extra': 20,
             'content': [f"[name]{owner_name}[/name]\n[time]{pub_time}[/time]"],
             'type_software': 'bilibili', },
            {'type': 'img', 'subtype': 'common_with_des_right', 'img': [cover],'label': ['直播'],
             'content': [context]}]

        if is_twice is not True:
            json_check['pic_path'] = await manshuo_draw(manshuo_draw_json)
            json_check['pic_url_list'].append(cover)
            return json_check
        return manshuo_draw_json
    # 专栏识别
    if 'read' in url:
        read_id = re.search(r'read\/cv(\d+)', url).group(1)
        ar = article.Article(read_id)
        # 如果专栏为公开笔记，则转换为笔记类
        # NOTE: 笔记类的函数与专栏类的函数基本一致
        if ar.is_note():
            ar = ar.turn_to_note()
        # 加载内容
        await ar.fetch_content()
        #print(ar.markdown())
        markdown_path = f'{filepath}{read_id}.md'
        with open(markdown_path, 'w', encoding='utf8') as f:
            f.write(ar.markdown())
        logger.info('专栏未做识别，跳过，欢迎催更')

        return None
    # 收藏夹识别
    if 'favlist' in url and BILI_SESSDATA != '':
        logger.info('收藏夹未做识别，跳过，欢迎催更')
        return None



    try:
        video_id = re.search(r"video\/[^\?\/ ]+", url)[0].split('/')[1]
        v = video.Video(video_id, credential=credential)
        video_info = await v.get_info()
    except Exception as e:
        logger.info('无法获取视频内容，该进程已退出')
        json_check['status'] = False
        return json_check
    #print(json.dumps(video_info, indent=4))
    owner_cover_url=video_info['owner']['face']
    owner_name = video_info['owner']['name']
    #logger.info(owner_cover)
    if video_info is None:
        logger.info(f"识别：B站，出错，无法获取数据！")
        return None
    video_title, video_cover, video_desc, video_duration = video_info['title'], video_info['pic'], video_info['desc'], \
        video_info['duration']
    pub_time = datetime.utcfromtimestamp(video_info['pubdate']) + timedelta(hours=8)
    pub_time=pub_time.strftime('%Y-%m-%d %H:%M:%S')
    # 校准 分p 的情况
    page_num = 0
    if 'pages' in video_info:
        # 解析URL
        parsed_url = urlparse(url)
        # 检查是否有查询字符串
        if parsed_url.query:
            # 解析查询字符串中的参数
            query_params = parse_qs(parsed_url.query)
            # 获取指定参数的值，如果参数不存在，则返回None
            page_num = int(query_params.get('p', [1])[0]) - 1
        else:
            page_num = 0
        if 'duration' in video_info['pages'][page_num]:
            video_duration = video_info['pages'][page_num].get('duration', video_info.get('duration'))
        else:
            # 如果索引超出范围，使用 video_info['duration'] 或者其他默认值
            video_duration = video_info.get('duration', 0)
    download_url_data = await v.get_download_url(page_index=page_num)
    detecter = VideoDownloadURLDataDetecter(download_url_data)
    streams = detecter.detect_best_streams()
    try:
        video_url, audio_url = streams[0].url, streams[1].url
        json_check['video_url']=video_url
        json_check['audio_url']=audio_url
    except Exception as e:
        json_check['video_url'] = False
    context += f'[title]{video_title}[/title]\n[des]{video_desc} [/des]'
    manshuo_draw_json = [
        {'type': 'avatar', 'subtype': 'common', 'img': [owner_cover_url], 'upshift_extra': 20,
         'content': [f"[name]{owner_name}[/name]\n[time]{pub_time}[/time]"],
         'type_software': 'bilibili', },
        {'type': 'img', 'subtype': 'common_with_des', 'img': [video_cover],'label': ['视频'],
         'content': [context]}]

    if is_twice is not True:
        if type != 'QQ_Check':
            json_check['pic_path'] = await manshuo_draw(manshuo_draw_json)
        json_check['pic_url_list'].append(video_cover)
        return json_check
    return manshuo_draw_json



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