
import asyncio
import json
import os
import time
import httpx
import re
import copy
from run.streaming_media.service.Link_parsing.core.common import json_init
from urllib.parse import urlparse
from urllib.parse import parse_qs
from datetime import datetime, timedelta
from developTools.utils.logger import get_logger
logger=get_logger()
import json
from framework_common.manshuo_draw.manshuo_draw import manshuo_draw



async def claendar_bangumi_get_json(calender=None):
    async with httpx.AsyncClient() as client:
        url = "https://api.bgm.tv/calendar"
        response = await client.get(url)
        if response.status_code:
            data = response.json()
            if calender:
                weekday=calender
            else:
                weekday = datetime.today().weekday()
            #print(weekday)
            week=data[weekday]['weekday']['cn']
            calendar_json_init=data[weekday]['items']
            try:calendar_json_init = sorted(calendar_json_init, key=lambda x:x.get("rank", float("inf")))
            except TypeError:pass
            #print(week)
            #print(json.dumps(data, indent=4))
        return calendar_json_init,week

async def bangumi_subject_post_json(type=None,target=None):
    async with httpx.AsyncClient() as client:
        if type is not None:
            params = {
                "type": type,
            }
        else:
            params = {}
        try:
            url = f"https://api.bgm.tv/search/subject/{target}"
            response = await client.post(url, params=params)
            if response.status_code:
                data = response.json()
                #print(data)
                #print(json.dumps(data, indent=4))
            return data
        except Exception as e:
            return False

async def bangumi_subjects_get_json_PIL(subject_id=None):
    async with httpx.AsyncClient() as client:
        try:
            url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
            response = await client.get(url)
            if response.status_code:
                data = response.json()
                #print(data)
                #print(json.dumps(data, indent=4))
                #print(data["summary"])
                contents_other=''
                for subject in data['infobox']:
                    if subject['key'] == "放送星期":
                        week_fang=subject['value']
                    elif subject['key'] == "话数":
                        week_jishu=subject['value']
                    if subject['key'] not in {'中文名','放送开始','放送星期','别名'}:
                        contents_other+=f'·{subject["key"]}：{subject["value"]}\n'
                img_url=data["images"]['large']
                name_bangumi = data['name_cn']
                if '' == name_bangumi:
                    name_bangumi = data['name']
                if 'rating' in data:
                    score=data['rating']['score']
                contents=''
                text=f"{name_bangumi}\n"
                contents += f"[title]{name_bangumi}({score}☆)[/title]"
                contents += f"\n播出日期：{data['date']} | {week_fang}放送 | {week_jishu}话\n简介：\n{data['summary']}"
                tags='\n[tag]'
                for tag in data['tags']:
                    tags+=f"#{tag['name']}# "
                if tags!='[tag]':
                    tags+='[/tag]'
                    contents += tags


            return contents,img_url,contents_other
        except Exception as e:
            return False



async def bangumi_PILimg(text=None,img_context=None,filepath=None,proxy=None,type_soft='Bangumi 番剧',name=None,url=None,
                         type=None,target=None,search_type=None,config=None,bot_id=None):
    contents=[]
    json_check = copy.deepcopy(json_init)
    json_check['soft_type'] = 'bangumi'
    json_check['status'] = True
    json_check['video_url'] = False

    if type is None:
        count=0
        count_1=0
        text_add=''
        words = text.split("\n")  # 按换行符分割文本，逐行处理
        for line in words:  # 遍历每一行（处理换行符的部分）
            #print(line)
            count+=1
            text_add+=f'{line}\n'
            if count == len(words):break
            if count % 10 ==0 :
                contents.append(text_add)
                img_add_context =[]
                for i in range(10):
                    img_add_context.append(img_context[i+count_1])
                contents.append({'type': 'img', 'img': img_add_context, 'number_per_row': 5})
                text_add = ''
                count_1=count

        json_check['pic_path'] = await manshuo_draw(contents)
        return json_check
    elif type == 'calendar':
        calendar_json,week = await claendar_bangumi_get_json(target)
        #print(week)
        #print(json.dumps(calendar_json, indent=4))
        text_total=[]
        img_context=[]
        for calendar_item in calendar_json:
            name_bangumi = calendar_item['name_cn']
            if '' == name_bangumi:
                name_bangumi = calendar_item['name']
            try:
                img_context.append(calendar_item['images']['common'].replace('http', 'https'))
                if 'rating' in calendar_item:
                    text_total.append(f"{name_bangumi}\n{calendar_item['rating']['score']}☆")
                else:
                    text_total.append(f"{name_bangumi}\n未知")
            except:
                pass

        json_check['pic_path'] = await manshuo_draw([{'type': 'basic_set', 'img_width': 1500,'img_name_save':f'{name}.png'},
                            {'type': 'avatar', 'subtype': 'common', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={bot_id}&s=640"],'upshift_extra': 25,
                             'content': [f"[name]{name}[/name]\n[time]{datetime.now().strftime('%Y年%m月%d日 %H:%M')}[/time]" ], 'type_software': 'bangumi', },
                            {'type': 'img', 'subtype': 'common_with_des_right', 'img': img_context, 'content': text_total}])
        json_check['soft_type'] = 'bangumi_calendar'
        return json_check


    elif type == 'search':
        search_json_init = await bangumi_subject_post_json(type=search_type,target=target)
        if search_json_init is False:
            json_check['status'] = False
            return json_check
        search_json=search_json_init['list']

        if int(search_json_init['results']) == 1:
            id = search_json_init['list'][0]['id']
            contents,img_url,contents_other =await bangumi_subjects_get_json_PIL(subject_id=id)
            json_check['pic_path'] = await manshuo_draw([{'type': 'basic_set', 'img_width': 1500},
                {'type': 'avatar', 'subtype': 'common', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={bot_id}&s=640"],
                                                          'upshift': 25,'content': [f"[name]{name}[/name]\n[time]{datetime.now().strftime('%Y年%m月%d日 %H:%M')}[/time]"  ], 'type_software': 'bangumi', },
                                                         {'type': 'img', 'subtype': 'common_with_des_right','img': [img_url], 'content': [contents]},contents_other])
            json_check['next_choice'] = False
            json_check['soft_type'] = 'bangumi_search'
            return json_check


        id_collect={}
        text_total = ''
        img_context = []
        count = 0
        for search_item in search_json_init['list']:
            count += 1
            id_collect[count] = search_item['id']
            name_bangumi = search_item['name_cn']
            if '' == name_bangumi:
                name_bangumi = search_item['name']
            if 'rating' in search_item:
                text_total += f"{count}、 {name_bangumi}----{search_item['rating']['score']}☆\n"
            else:
                text_total += f"{count}、 {name_bangumi}\n"
            if int(search_json_init['results']) <= 5:
                img_context.append(search_item['images']['large'].replace('http', 'https'))
            else:
                img_context.append(search_item['images']['common_utils'].replace('http', 'https'))

        count = 0
        count_1 = 0
        text_add = ''
        words = text_total.split("\n")  # 按换行符分割文本，逐行处理
        for line in words:  # 遍历每一行（处理换行符的部分）
            if line == '': continue
            count += 1
            if text_add == '':text_add = f'{line}'
            else:text_add += f'\n{line}'
            if count % 10 == 0:
                contents.append(text_add)
                img_add_context = []
                for i in range(10):
                    img_add_context.append(img_context[i + count_1])
                contents.append({'type': 'img', 'img': img_add_context, 'number_per_row': 5})
                text_add = ''
                count_1 = count
        if count % 10 < 10  and count % 10 !=0 and text_add!='':
            img_add_context=[]
            contents.append(text_add)
            for i in range(count % 10):
                img_add_context.append(img_context[i + count_1])
            contents.append({'type': 'img', 'img': img_add_context, 'number_per_row': 5})

        json_check['pic_path'] = await manshuo_draw(contents)
        json_check['soft_type'] = 'bangumi_search'
        json_check['next_choice'] = True
        json_check['choice_contents'] = id_collect
        #print(id_collect)
        return json_check
    elif type == 'search_accurate':
        contents, img_url, contents_other = await bangumi_subjects_get_json_PIL(subject_id=target)
        json_check['pic_path'] = await manshuo_draw([{'type': 'basic_set', 'img_width': 1500},
            {'type': 'avatar', 'subtype': 'common', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={bot_id}&s=640"],'upshift': 25,
             'content': [f"[name]{config.common_config.basic_config['bot']}[/name]\n[time]{datetime.now().strftime('%Y年%m月%d日 %H:%M')}[/time]" ], 'type_software': 'bangumi', },
                                                     {'type': 'img', 'subtype': 'common_with_des_right','img': [img_url], 'content': [contents]},
                                                     contents_other])
        json_check['next_choice'] = False
        json_check['soft_type'] = 'bangumi_search'
        return json_check





async def main():
    #data = await bangumi_subject_post_json(target='败犬女主太多了',type=2)
    calendar_json_init,week=await claendar_bangumi_get_json()
    print(week)
    print(json.dumps(calendar_json_init, indent=4))

# 运行异步任务
if __name__ == "__main__":
    asyncio.run(main())