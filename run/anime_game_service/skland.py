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
        if event.message_chain.has(At):
            userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        if context in order_list:
            await qrcode_get(userid, bot, event)


    #森空岛签到
    @bot.on(GroupMessageEvent)
    async def sing_sklandid(event: GroupMessageEvent):
        order_list=['sklandsign','森空岛签到']
        context, userid=event.pure_text, str(event.sender.user_id)
        if event.message_chain.has(At):userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        if context in order_list:await skland_signin(userid, bot, event)

    #森空岛信息查询
    @bot.on(GroupMessageEvent)
    async def sing_sklandid(event: GroupMessageEvent):
        order_list=['sklandinfo','森空岛info','森空岛信息','我的森空岛']
        context, userid=event.pure_text, str(event.sender.user_id)
        if event.message_chain.has(At):userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        if context in order_list:await skland_info(userid, bot, event)


    #菜单
    @bot.on(GroupMessageEvent)
    async def menu_steamid(event: GroupMessageEvent):
        order_list=['sklandhelp','森空岛帮助','森空岛help','明日方舟帮助','明日方舟help']
        if event.pure_text in order_list:
            draw_json=[{'type': 'avatar', 'subtype': 'common', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={event.self_id}&s=640"],'upshift_extra':15,
             'content': [f"[name]森空岛帮助菜单[/name]\n[time]各位博士们，欢迎使用森空岛功能～～[/time]"]},
            '[title]指令菜单：[/title]'
            '\n- 绑定森空岛账号：sklandbind, 森空岛绑定\n- 森空岛签到：sklandsign, 森空岛签到\n'
            '- 森空岛信息：sklandinfo, 森空岛info、森空岛信息、我的森空岛\n'
            '等待开发，欢迎催更（咕咕咕\n'
            '[des]                                             Function By 漫朔[/des]'
                       ]
            await bot.send(event, Image(file=(await manshuo_draw(draw_json))))




