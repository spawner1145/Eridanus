import pprint
import random
import os
from developTools.message.message_components import Record, Node, Text, Image, At
from developTools.event.events import GroupMessageEvent
import re
from framework_common.manshuo_draw import *
from datetime import datetime, timedelta
# 构建分隔符正则表达式
separators_pattern = '|'.join(re.escape(sep) for sep in ["|", "｜"])

async def parse_message_segments(event,bot):
    """解析消息段，将图片正确分配到对应的消息段"""
    pure_text = ''
    # 处理图片并重新整合消息
    for obj in event.message_chain:
        if obj.comp_type == 'text':
            pure_text += f"{obj.text}"
        elif obj.comp_type == 'image':
            if pure_text == '':
                pure_text += f"[title][emoji]{obj.url}[/emoji][/title]"
            else:
                pure_text += f"\n[title][emoji]{obj.url}[/emoji][/title]"
        elif obj.comp_type == 'at':
            try:
                userid, target_group = event.sender.user_id, event.group_id
                target_name = (await bot.get_group_member_info(target_group, obj.qq))['data']['nickname']
            except:
                target_name = '未知用户'
            pure_text += f"@{target_name}"

    return [{'text':pure_text}]

def main(bot, config):

    @bot.on(GroupMessageEvent)
    async def today_message(event: GroupMessageEvent):
        context, userid, nickname, group_id, is_at = event.pure_text, str(event.sender.user_id), event.sender.nickname, int(event.group_id),False
        if event.message_chain.has(At) and event.message_chain.has(Text):
            is_at = True
            userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        if context.strip() not in ['今日怪话','今日语录','群友怪话','群友语录']:  return
        img_path_save = f'data/pictures/record_message/{group_id}'
        files = [f for f in os.listdir(img_path_save) if os.path.isfile(os.path.join(img_path_save, f))]
        if not files:
            await bot.send(event, '本群好像还没有群友的怪话呢\n发送“消息记录”来引用记录群友的怪话吧 ！')
            return
        if is_at:
            files_check = []
            for file in files:
                if file.startswith(f'{userid}_'):files_check.append(file)
            if files_check:files = files_check
            else:
                await bot.send(event, '这位群友还没有说过怪话呢\n发送“消息记录”来引用记录群友的怪话吧 ！')
                return
        random_file = random.choice(files)
        await bot.send(event, Image(file=f'{img_path_save}/{random_file}'))

    @bot.on(GroupMessageEvent)
    async def record_message_reply(event: GroupMessageEvent):
        if event.get("reply") and event.get("text"):
            context = event.get("text")[0].strip().replace(' ','')
            if context not in ['记录消息','消息记录']: return
        else:
            return
        event_obj = await bot.get_msg(int(event.get("reply")[0]["id"]))
        if event_obj.message[0]['type'] == 'forward': return
        check = await parse_message_segments(event_obj,bot)
        #print(check)
        context = check[0]["text"]
        parts = re.split(r'\[title\].*?\[/title\]', context)
        context_len = len("".join(parts))
        if '[title]' in context: context_len += 5
        img_width = 700
        userid, target_group = event_obj.sender.user_id, event.group_id
        try:
            target_name = (await bot.get_group_member_info(target_group, userid))['data']['nickname']
        except:
            target_name = '未知用户'
        check_name = f'                     --By {target_name}'
        #print(context_len)
        if 200 > context_len > 40:
            img_width = 1100
            check_name = f'                    {check_name}'
        elif 400 > context_len >= 200:
            img_width = 1500
            check_name = f'                                                  {check_name}'
        elif context_len >= 400:
            img_width = 2000
            check_name = f'                                                                                {check_name}'
        total_line_breaks = context.count('\n') + context.count('\r') + 1
        #print(total_line_breaks,total_line_breaks * 43,img_width / 3 - 40,context_len)
        if total_line_breaks * 43 > img_width / 3 - 40: img_width = total_line_breaks * 43 * 3 + 40
        if len(target_name) > 4:
            check_name = check_name[len(target_name)+3:]

        img_path_save = f'data/pictures/record_message/{target_group}'
        img_number = 0
        if os.path.exists(img_path_save):
            image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff'}
            file_list = os.listdir(img_path_save)
            for filename in file_list:
                if filename.startswith(f'{userid}'):
                    ext = os.path.splitext(filename)[1].lower()  # 获取扩展名并转小写
                    if ext in image_extensions:
                        img_number += 1
            if f'{userid}_{img_number}' in file_list:
                for i in range(len(file_list)):
                    if f'{userid}_{img_number}' in file_list: img_number += 1
                    else:break
        img_name_save = f'{userid}_{img_number}.png'
        # 保证存储文件夹存在
        if not os.path.exists(img_path_save):
            os.makedirs(img_path_save)
        draw_list = [
        {'type': 'basic_set', 'img_width': img_width, 'font_title_size':125,'img_path_save':img_path_save, 'img_name_save': img_name_save},
        {'type': 'img', 'subtype': 'common_with_des_right','img': [f"https://q1.qlogo.cn/g?b=qq&nk={userid}&s=640"],
         'content': [f'{context}\n{check_name}']},
        ]
        await bot.send(event, Image(file=(await manshuo_draw(draw_list))))



    @bot.on(GroupMessageEvent)
    async def record_message_reply_forword(event: GroupMessageEvent):
        if event.get("reply") and event.get("text"):
            context = event.get("text")[0].strip().replace(' ','')
            if context not in ['记录消息','消息记录']: return
        else:
            return
        event_obj = await bot.get_msg(int(event.get("reply")[0]["id"]))
        if event_obj.message[0]['type'] != 'forward': return

        message_check = event_obj.message[0]['data']['content']
        #pprint.pprint(message_check)
        #pprint.pprint(event_obj.processed_message)
        forward_list = []
        for item in message_check:
            time = datetime.utcfromtimestamp(item['time']) + timedelta(hours=8)
            per_item_check, per_result = item['message'], ''
            for per_msg in per_item_check:
                if per_msg['type'] == 'text':
                    per_result += per_msg['data']['text']
                elif per_msg['type'] == 'image':
                    if per_result == '': per_result += f"[title][emoji]{per_msg['data']['url']}[/emoji][/title]"
                    else: per_result += f"\n[title][emoji]{per_msg['data']['url']}[/emoji][/title]"
                elif per_msg['type'] == 'forward':
                    per_result += '这里是聊天记录喵'
            per_message = {'group_id': item['group_id'], 'user_id':item['user_id'], 'nickname':item['sender']['nickname'], 'avatar_img':f"https://q1.qlogo.cn/g?b=qq&nk={item['user_id']}&s=640",
                           'time':time.strftime('%Y-%m-%d %H:%M:%S'), 'content':per_result}
            forward_list.append(per_message)
        #pprint.pprint(forward_list)

        userid, target_group = event_obj.sender.user_id, event.group_id
        img_path_save = f'data/pictures/record_message/{target_group}'
        img_number = 0
        if os.path.exists(img_path_save):
            image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff'}
            file_list = os.listdir(img_path_save)
            for filename in file_list:
                if filename.startswith(f'{userid}'):
                    ext = os.path.splitext(filename)[1].lower()  # 获取扩展名并转小写
                    if ext in image_extensions:
                        img_number += 1
            if f'{userid}_{img_number}' in file_list:
                for i in range(len(file_list)):
                    if f'{userid}_{img_number}' in file_list: img_number += 1
                    else:break
        img_name_save = f'{userid}_{img_number}.png'
        # 保证存储文件夹存在
        if not os.path.exists(img_path_save):
            os.makedirs(img_path_save)
        draw_list, img_width = [], 700
        for item in forward_list:
            parts = re.split(r'\[title\].*?\[/title\]', item['content'])
            if 200 > len("".join(parts)) > 40: img_width = 1100
            elif 400 > len("".join(parts)) >= 200: img_width = 1500
            elif len("".join(parts)) >= 400: img_width = 2000
            draw_list.append(
                {'type': 'avatar', 'img': [item['avatar_img']],'content': [f"[name]{item['nickname']}[/name]   [time]{item['time']}[/time]"],'padding_up_bottom':8,'padding_up_font':10,'avatar_size':50,'font_name_size':28})
            draw_list.append(f'   {item['content']}')
        #print(f'final img width: {img_width}')；
        #pprint.pprint(draw_list)
        draw_list.append({'type': 'basic_set', 'img_width': img_width, 'font_title_size':125,'img_path_save':img_path_save, 'img_name_save': img_name_save, 'padding_up_layer':10})
        await bot.send(event, Image(file=(await manshuo_draw(draw_list))))



