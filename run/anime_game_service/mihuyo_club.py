from developTools.event.events import GroupMessageEvent, LifecycleMetaEvent
from developTools.message.message_components import Text, Image, At
from framework_common.manshuo_draw import *
from run.anime_game_service.service.mihuyo_club import *


def main(bot, config):


    #绑定米游社
    @bot.on(GroupMessageEvent)
    async def bind_sklandid(event: GroupMessageEvent):
        context, userid=event.pure_text, str(event.sender.user_id)
        order_list = ['mihuyobind', '米游社绑定','米游社登录','绑定米游社']
        if event.message_chain.has(At) and event.message_chain.has(Text):
            userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        if context.lower() in order_list:
            await mys_login(userid, bot, event)

    #米游社签到
    @bot.on(GroupMessageEvent)
    async def sing_sklandid(event: GroupMessageEvent):
        order_list=['mihuyosign','米游社签到']
        context, userid=event.pure_text, str(event.sender.user_id)
        if event.message_chain.has(At) and event.message_chain.has(Text):
            userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        if context.strip() in order_list:
            await mys_game_sign(userid, bot, event)

    #游戏别名签到
    @bot.on(GroupMessageEvent)
    async def sing_sklandid(event: GroupMessageEvent):
        order_list=['签到']
        target_list = ['原神','崩铁','绝区零','崩坏三','崩坏3','崩三','崩崩崩','未定事件簿','崩坏学园2','未定','崩2','zzz','ZZZ']
        context, userid=event.pure_text, str(event.sender.user_id)
        if event.message_chain.has(At) and event.message_chain.has(Text):
            userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        if not any(context.endswith(word) for word in order_list): return
        target_games = next((t for t in target_list if t in context), None)
        if target_games is None:return
        else:target_games = target_games.strip()
        await mys_game_sign(userid, bot, event, target_games)

    #更改默认签到游戏
    @bot.on(GroupMessageEvent)
    async def change_default_game(event: GroupMessageEvent):
        order_list=['mysgamechange']
        target_list = ['原神','崩铁','绝区零','崩坏三','未定事件簿','崩坏学园2']
        context, userid=event.pure_text, str(event.sender.user_id)
        if event.message_chain.has(At) and event.message_chain.has(Text):
            userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        if not any(context.startswith(word) for word in order_list): return
        target_games = next((t for t in target_list if t in context), None)
        if target_games is None:
            await bot.send(event, f'当前可更改的游戏别名如下：\n{target_list}')
            return
        else:target_games = target_games.strip()
        await change_default_sign_game(userid, target_games, bot, event)

    #菜单
    @bot.on(GroupMessageEvent)
    async def menu_steamid(event: GroupMessageEvent):
        order_list=['米游社帮助','mihuyohelp']
        if event.pure_text.lower() in order_list:
            await help_menu(bot,event)