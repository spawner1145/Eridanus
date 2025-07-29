from developTools.event.events import GroupMessageEvent, LifecycleMetaEvent
from developTools.message.message_components import Text, Image, At
from framework_common.manshuo_draw import *
from run.anime_game_service.service.SteamSnooping import *
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
from datetime import datetime


def main(bot, config):
    # 初始化 Redis 数据库实例
    db_json=config.common_config.basic_config['redis']
    db = RedisDatabase(host=db_json['redis_ip'], port=db_json['redis_port'], db=db_json['redis_db'])
    steam_api_key=config.anime_game_service.config['steamsnooping']['steam_api_key']
    #print(steam_api_key)
    if config.anime_game_service.config['steamsnooping']['is_snooping']:
        bot.logger.info(f"bot开始视奸群友的Steam啦！")
        threading.Thread(target=url_main(bot, config, db,steam_api_key), daemon=True).start()

    #绑定一个steamid
    @bot.on(GroupMessageEvent)
    async def bind_steamid(event: GroupMessageEvent):
        context, userid=event.pure_text, str(event.sender.user_id)
        if event.message_chain.has(At):
            userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        if context.lower().startswith('steambind '):
            steamid=get_steam_id(context.replace('steambind ', ''))
            if not steamid:
                await bot.send(event, '请输入正确的 Steam ID 或 Steam好友代码，格式: steambind [Steam ID 或 Steam好友代码]')
                return
            db.write_user(userid, {'SteamSnooping':{'steamid':steamid}})
            await bot.send(event, ['成功绑定 ',At(qq=userid), f' 的steamid ({steamid}) 喵'])
        elif context.lower()=='steamunbind':
            db.write_user(userid, {'SteamSnooping': {'steamid': None}})
            await bot.send(event, ['成功解除 ', At(qq=userid), f' 的steamid绑定'])


    #查询一个人的steam信息
    @bot.on(GroupMessageEvent)
    async def info_steamid(event: GroupMessageEvent):
        context, steamid, steam_friend_code, userid = event.pure_text, None, None, None
        if event.message_chain.has(At):
            try:
                if 'steaminfo' == event.processed_message[0]['text']:userid=event.message_chain.get(At)[0].qq
                else:return
            except Exception as e:return
        elif context.lower().startswith('steaminfo '):
            steamid=get_steam_id(context.replace('steaminfo ', ''))
            steam_friend_code = int(steamid) - STEAM_ID_OFFSET
        elif context.lower() == 'steaminfo':
            userid = str(event.sender.user_id)
        else:return

        if not (steamid and steam_friend_code):
            steaminfodata = db.read_user(userid)
            if steaminfodata and  'SteamSnooping' in steaminfodata:
                #await bot.send(event, Image(file=(await manshuo_draw())))
                steamid = steaminfodata["SteamSnooping"]["steamid"]
                steam_friend_code = int(steamid) - STEAM_ID_OFFSET
            else:
                await bot.send(event, '此用户好像还未绑定，发送"steamhelp"来查看帮助哦')
                return

        #await bot.send(event, f'steamid: {steamid}, steam_friend_code: {steam_friend_code}')
        recall_id=await bot.send(event, f'开始查询您的最近steam动态，请耐心等待喵')
        proxy_config = config.common_config.basic_config['proxy']['http_proxy']
        proxy_config = proxy_config if proxy_config else None
        player_data = await get_user_data(steamid, proxy_config)
        
        # 根据是否有userid构建不同的绘图参数
        proxy_for_draw = config.common_config.basic_config['proxy']['http_proxy'] if config.common_config.basic_config['proxy']['http_proxy'] else None
        
        if userid:
            try:user_name = (await bot.get_group_member_info(event.group_id, userid))['data']['nickname']
            except:user_name='未知'
            # 有userid时显示QQ和Steam双头像
            #if len(user_name) > 10: user_name = user_name[:10]
            draw_json=[
                {'type': 'basic_set', 'img_width': 1500,'proxy': proxy_for_draw},
                {'type': 'avatar', 'subtype': 'common', 'img': [f'https://q1.qlogo.cn/g?b=qq&nk={userid}&s=640',player_data["avatar_url"]],'upshift_extra':15,'number_per_row': 2,
                 'content': [f"[name]qq昵称: {user_name}[/name]\n[time]游玩时间：{player_data['recent_2_week_play_time']}[/time]",f'[name]Steam昵称: {player_data["player_name"]}[/name]\n[time]好友代码：{steam_friend_code}[/time]'],
                 'is_rounded_corners_img':False,'is_stroke_img':False,'is_shadow_img':False},'[title]您的最近游戏动态：[/title]',
                {'type': 'img', 'subtype': 'common_with_des_right',
                 'img': [f"{game['game_image_url']}" for game in player_data["game_data"]],
                 'content': [
                     f"[title]{game['game_name']}[/title]\n游玩时间：{game['play_time']} 小时\n{game['last_played']}"
                     f"\n成就：{game.get('completed_achievement_number')} / {game.get('total_achievement_number')}"
                     for game in player_data["game_data"]], 'number_per_row': 1,'is_crop':False}
            ]
        else:
            # 无userid时只显示Steam头像
            draw_json=[
                {'type': 'basic_set', 'img_width': 1500,'proxy': proxy_for_draw},
                {'type': 'avatar', 'subtype': 'common', 'img': [player_data["avatar_url"]],'upshift_extra':15,
                 'content': [f'[name]Steam昵称: {player_data["player_name"]}[/name]\n[time]好友代码：{steam_friend_code}[/time]\n[time]游玩时间：{player_data["recent_2_week_play_time"]}[/time]'],
                 'is_rounded_corners_img':False,'is_stroke_img':False,'is_shadow_img':False},'[title]最近游戏动态：[/title]',
                {'type': 'img', 'subtype': 'common_with_des_right',
                 'img': [f"{game['game_image_url']}" for game in player_data["game_data"]],
                 'content': [
                     f"[title]{game['game_name']}[/title]\n游玩时间：{game['play_time']} 小时\n{game['last_played']}"
                     f"\n成就：{game.get('completed_achievement_number')} / {game.get('total_achievement_number')}"
                     for game in player_data["game_data"]], 'number_per_row': 1,'is_crop':False}
            ]
        
        #for item in draw_json:print(item)
        await bot.send(event, Image(file=(await manshuo_draw(draw_json))))
        await bot.recall(recall_id['data']['message_id'])

    #添加到视歼列表
    @bot.on(GroupMessageEvent)
    async def add_steamid_snoop(event: GroupMessageEvent):
        context, userid = event.pure_text, str(event.sender.user_id)
        target_group = str(event.group_id)
        if event.message_chain.has(At):
            userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        if context.lower().startswith('steamadd'):
            steaminfodata = db.read_user(userid)
            if not (steaminfodata and  'SteamSnooping' in steaminfodata):
                await bot.send(event, '此用户好像还未绑定，发送"steamhelp"来查看帮助哦')
                return
            db.write_user('SteamSnoopingList', {target_group:{userid:True,
                                                              f'{userid}_steamid':steaminfodata["SteamSnooping"]["steamid"],
                                                              }})
            await bot.send(event, [At(qq=userid), f' 已被加入视歼列表'])
        elif context.lower()=='steamremove':
            db.write_user('SteamSnoopingList', {target_group:{userid:False}})
            await bot.send(event, [At(qq=userid), f' 已被移除视歼列表'])

    #查看当前群的视奸列表
    @bot.on(GroupMessageEvent)
    async def group_check_steamid(event: GroupMessageEvent):
        if event.pure_text.lower() == 'steamcheck':
            ids_list = db.read_user('SteamSnoopingList')
            user_list, name_list = [],'当前群聊的 Steam视奸 列表为：\n'
            if not (ids_list and str(event.group_id) in ids_list) :
                await bot.send(event, '该群还没有绑定视奸用户哦')
            for user_id in ids_list[str(event.group_id)]:
                if ids_list[str(event.group_id)][user_id] is not True: continue
                user_list.append(user_id)
            if user_list == []:
                await bot.send(event, '该群还没有绑定视奸用户哦')
                return
            #print(user_list)
            for user_id in user_list :
                target_name = (await bot.get_group_member_info(event.group_id, user_id))['data']['nickname']
                name_list += f'@{target_name} '
            await bot.send(event, name_list)


    #菜单
    @bot.on(GroupMessageEvent)
    async def menu_steamid(event: GroupMessageEvent):
        if event.pure_text.lower() == 'steamhelp':
            draw_json=[{'type': 'avatar', 'subtype': 'common', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={event.self_id}&s=640"],'upshift_extra':15,
             'content': [f"[name]Steam视奸菜单[/name]\n[time]什么！你是怎么发现我可以视奸你的！！！！[/time]"]},
            '在这里你可以通过bot随时随地[title]视奸[/title]你朋友的steam状态\n[des]但是要小心使用，至少经过朋友同意或者不影响他人哦[/des]\n[title]指令菜单：[/title]'
            '\n- 绑定Steam账号：steambind [Steam ID 或 Steam好友代码]（可艾特） \n- 查询Steam最近游玩内容：steaminfo\n（可艾特或者直接发送Steam ID or Steam好友代码）'
            '\n- 添加到当前群进行视奸：steamadd（可艾特）\n- 取消视奸：steamremove（可艾特）\n- 查看当前群视奸列表：steamcheck\n'
            '[title]注意注意！[/title]要先绑定自身的steamid才能进行视奸哦～～\n[des]当然你也可以帮别人绑定哦（逃[/des]\n'
            '[des]                                             Function By 漫朔[/des]'
                       ]
            await bot.send(event, Image(file=(await manshuo_draw(draw_json))))




