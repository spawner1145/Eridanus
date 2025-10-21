from developTools.event.events import GroupMessageEvent, LifecycleMetaEvent
from developTools.message.message_components import Text, Image, At
from framework_common.manshuo_draw import *
from run.anime_game_service.service.epicfree import *


def main(bot, config):

    #绑定一个steamid
    @bot.on(GroupMessageEvent)
    async def epic_free_get(event: GroupMessageEvent):
        context, userid=event.pure_text, str(event.sender.user_id)
        if context.lower() not in ['epicfree','epic喜加一']:return
        recall_id = await bot.send(event, f'开始查询最近的Epic喜加一，请耐心等待喵')
        proxy = config.common_config.basic_config['proxy']['http_proxy'] if config.common_config.basic_config['proxy'][
            'http_proxy'] else None
        await epic_free_game_get(bot, event, proxy)
        await bot.recall(recall_id['data']['message_id'])

    #菜单
    @bot.on(GroupMessageEvent)
    async def menu_steamid(event: GroupMessageEvent):
        if event.pure_text.lower() in ['epichelp','epic帮助']:
            draw_json=[
                {'type': 'basic_set', 'img_name_save': 'epichelp.png'},
                {'type': 'avatar', 'subtype': 'common', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={event.self_id}&s=640"],'upshift_extra':15,
                        'content': [f"[name]Epic菜单[/name]\n[time]咕咕咕[/time]"]},
                       '[title]指令菜单：[/title]'
                       '\n- Epic喜加一：epicfree、epic喜加一\n其他功能亟待开发，咕咕咕~~~~\n'
                       '[des]                                             Function By 漫朔[/des]'
                       ]
            await bot.send(event, Image(file=(await manshuo_draw(draw_json))))