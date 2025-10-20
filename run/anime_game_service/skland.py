from developTools.event.events import GroupMessageEvent, LifecycleMetaEvent
from developTools.message.message_components import Text, Image, At
from framework_common.manshuo_draw import *
from run.anime_game_service.service.skland import *
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
from datetime import datetime


def main(bot, config):


    #绑定森空岛
    @bot.on(GroupMessageEvent)
    async def bind_sklandid(event: GroupMessageEvent):
        context, userid=event.pure_text, str(event.sender.user_id)
        order_list = ['sklandbind', '森空岛绑定']
        if event.message_chain.has(At) and event.message_chain.has(Text):
            userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        if context in order_list:
            await qrcode_get(userid, bot, event)


    #森空岛签到
    @bot.on(GroupMessageEvent)
    async def sing_sklandid(event: GroupMessageEvent):
        order_list=['sklandsign','森空岛签到']
        context, userid=event.pure_text, str(event.sender.user_id)
        if event.message_chain.has(At) and event.message_chain.has(Text):
            userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        if context in order_list:await skland_signin(userid, bot, event)

    #森空岛信息查询
    @bot.on(GroupMessageEvent)
    async def sing_sklandid(event: GroupMessageEvent):
        order_list=['sklandinfo','森空岛info','森空岛信息','我的森空岛']
        context, userid=event.pure_text, str(event.sender.user_id)
        if event.message_chain.has(At) and event.message_chain.has(Text):
            userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        if context in order_list:
            recall_id = await bot.send(event, f'开始查询您的森空岛信息，请耐心等待喵')
            await skland_info(userid, bot, event)
            await bot.recall(recall_id['data']['message_id'])

    #森空岛肉鸽战绩查询
    @bot.on(GroupMessageEvent)
    async def sing_rouge_info(event: GroupMessageEvent):
        order_list=['sklandrogue','sklandrg','肉鸽信息']
        context, userid, flag=event.pure_text, str(event.sender.user_id), True
        if event.message_chain.has(At) and event.message_chain.has(Text):
            userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        for order_check in order_list:
            if order_check in context:
                flag=False
                context = context.replace(' ', '').replace(order_check, '')
        if flag is True or context not in ["傀影","水月", "萨米", "萨卡兹",'界园']:return
        recall_id = await bot.send(event, f'开始查询您的{context}肉鸽信息，请耐心等待喵')
        await rouge_info(userid, context,bot=bot, event=event)
        await bot.recall(recall_id['data']['message_id'])

    ##森空岛肉鸽详细战绩查询
    @bot.on(GroupMessageEvent)
    async def sing_sklandid(event: GroupMessageEvent):
        order_list=['sklandrogueinfo','sklandrginfo','肉鸽查询','查询肉鸽']
        context, userid, flag, game_count = event.pure_text, str(event.sender.user_id), True, None
        if event.message_chain.has(At) and event.message_chain.has(Text):
            userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        for order_check in order_list:
            if order_check in context:
                flag=False
                context = context.replace(order_check, '').replace(' ', '')
        if flag is True :return
        flag=True
        for check in ["傀影","水月", "萨米", "萨卡兹",'界园']:
            if check in context:
                flag = False
                rg_type = check
                try:game_count=int(context.replace(check,''))
                except:pass
        if flag is True :return
        recall_id = await bot.send(event, f'开始查询您的{rg_type}肉鸽信息，请耐心等待喵')
        await rouge_detailed_info(userid, rg_type,game_count,bot=bot, event=event)
        await bot.recall(recall_id['data']['message_id'])


    #菜单
    @bot.on(GroupMessageEvent)
    async def menu_steamid(event: GroupMessageEvent):
        order_list=['sklandhelp','森空岛帮助','森空岛help','明日方舟帮助','明日方舟help']
        if event.pure_text in order_list:
            draw_json=[
            {'type': 'basic_set', 'img_name_save': 'sklandhelp.png'},
            {'type': 'avatar', 'subtype': 'common', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={event.self_id}&s=640"],'upshift_extra':15,
             'content': [f"[name]森空岛帮助菜单[/name]\n[time]各位博士们，欢迎使用森空岛功能～～[/time]"]},
            '[title]指令菜单：[/title]'
            '\n- 绑定森空岛账号：sklandbind, 森空岛绑定\n- 森空岛签到：sklandsign, 森空岛签到\n'
            '- 森空岛信息：sklandinfo, 森空岛info、森空岛信息、我的森空岛\n'
            '- 森空岛肉鸽战绩查询：sklandrogue, sklandrg、肉鸽信息 + 傀影or水月or萨米or萨卡兹or界园\n'
            '- 森空岛肉鸽详细战绩查询：sklandrogueinfo, sklandrginfo、肉鸽查询、查询肉鸽 + 傀影or水月or萨米or萨卡兹or界园 + 你想查询的最近场次\n'
            'eg: 水月肉鸽查询1 or 肉鸽查询水月3\n'
            '等待开发，欢迎催更（咕咕咕\n'
            '[des]                                             Function By 漫朔[/des]'
                       ]
            await bot.send(event, Image(file=(await manshuo_draw(draw_json))))




