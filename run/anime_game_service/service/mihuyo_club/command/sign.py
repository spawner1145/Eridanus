import asyncio
import threading
from typing import Union, Optional, Iterable, Dict
from pydantic import BaseModel
from framework_common.manshuo_draw import *
from ..api import BaseGameSign
from ..api import BaseMission, get_missions_state
from ..api.common import genshin_note, get_game_record, starrail_note
from ..model import (MissionStatus, PluginDataManager, plugin_config, UserData, CommandUsage, GenshinNoteNotice,
                     StarRailNoteNotice)
import pprint
from developTools.utils.logger import get_logger
logger=get_logger('MiHoYo')
from developTools.message.message_components import Text, Image, At
import traceback
from .config import game_name_list, game_all_list

async def change_default_sign_game(user_id,target,bot=None,event=None):
    user = PluginDataManager.plugin_data.users[str(user_id)]
    if not user or not user.accounts:
        msg = '此用户还未绑定，请发送 ‘米游社帮助’ 查看菜单'
        if bot and event: await bot.send(event, msg)
        else: print(msg)
    #print(user.target_sign_game)
    for item in game_name_list:
        if target in game_name_list[item]:
            target = item
            break
    user.target_sign_game = target
    PluginDataManager.write_plugin_data()
    if bot: await bot.send(event, f'您的默认签到游戏已更改为 {target}')


async def mys_game_sign(user_id,bot=None,event=None,target='all',type='game'):
    #pprint.pprint(PluginDataManager.plugin_data.users)
    user = PluginDataManager.plugin_data.users.get(str(user_id))
    return_json = {'message':'test','img_list':[],'text_list':[],'status':False,'text':'','manshuo_draw':[]}
    if not user or not user.accounts:
        msg = '此用户还未绑定，请发送 ‘米游社帮助’ 查看菜单'
        if bot and event: await bot.send(event, msg)
        else: print(msg)
        return_json['message'] = msg
        return return_json
    recall_id = None
    if bot and target == 'all': recall_id = await bot.send(event, '签到时间较长，请耐心等待喵')
    try:
        for item in game_name_list:
            if target in game_name_list[item]:
                target = [item]
                break
        sign_info = await perform_game_sign(user_id=user_id,bot=bot, user=user, event=event, target=str(target), type=type)

        return_json['img_list'], return_json['text_list'] = sign_info['img_list'], sign_info['text_list']

        if sign_info['status']:
            for item in sign_info['text_list']:
                return_json['text'] += f'{item}\n'
        else:
            return_json['text'] = '已尝试签到，但未获得签到数据，可自行前往米游社查看'
        #return_json['text'] += '[des]ps:为避签到时间过长，签到模块只会签到一个游戏\n请在菜单中自行更换默认签到游戏的说[/des]'
        return_json['text'] += '[des]ps:一次签到米游社所有游戏耗时很长，请耐心等待喵[/des]'
        return_json['status'] = True
        return_json['manshuo_draw'] = sign_info['manshuo_draw']
    except Exception as e:
        print(e)
        traceback.print_exc()
        msg = '签到失败，请稍后重试喵'
        #if bot: await bot.send(event, msg)
        return_json['message'] = msg
    finally:
        if recall_id: await bot.recall(recall_id['data']['message_id'])
        return return_json



async def perform_game_sign(user, user_id=None, bot = None, event = None, target='all',type='game'):
    """
    执行游戏签到函数，并发送给用户签到消息。
    target = [原神,崩坏：星穹铁道,绝区零,崩坏3]
    :param user: 用户数据
    :param event: 事件
    """
    return_json = {'status':False,'img_list':[],'text_list':[],'manshuo_draw':[]}
    if target in ['all']:target_list = game_all_list
    elif target in ['daily_sign']:
        if not user.target_sign_game: target_list = ['崩坏：星穹铁道']
        else:
            print(user.target_sign_game)
            target_list = [user.target_sign_game]
    else:target_list = target
    #直接签到所有
    target_list = game_all_list
    failed_accounts, img_list, text_list, pure_text_list, UID = [], [], [], [], '无法获取'
    for account in user.accounts.values():
        signed = False
        """是否已经完成过签到"""
        game_record_status, records = await get_game_record(account)
        UID = account.display_name
        if not game_record_status:
            msg = f" 获取游戏账号信息失败，请重新尝试"
            if bot: await bot.send(event, [At(qq=user_id), msg])
            else:print(msg)
            continue
        games_has_record = []

        for class_type in BaseGameSign.available_game_signs:
            signer = class_type(account, records)
            if signer.name not in target_list:continue
            if not signer.has_record:
                continue
            else:
                games_has_record.append(signer)
                #print(class_type.en_name)
                #print(account.game_sign_games)
                if class_type.en_name not in account.game_sign_games:
                    continue
            get_info_status, info = await signer.get_info(account.platform)
            if not get_info_status:
                msg = f" 获取签到记录失败"
                #if bot: await bot.send(event, msg)
                #else:  print(msg)
            else:
                signed = info.is_sign

            # 若没签到，则进行签到功能；若获取今日签到情况失败，仍可继续
            if (get_info_status and not info.is_sign) or not get_info_status:
                sign_status, mmt_data = await signer.sign(account.platform)
                #失败后重新延迟后重新签一次
                if not sign_status:
                    if not (sign_status.login_expired or sign_status.need_verify):
                        logger.info('第一次签到失败，延迟后第二次签到')
                        await asyncio.sleep(plugin_config.preference.sleep_time)
                        game_record_status, records = await get_game_record(account)
                        signer = class_type(account, records)
                        sign_status, mmt_data = await signer.sign(account.platform)


                #第二次签后获取不到数据则继续
                if not sign_status and user.enable_notice:
                    if sign_status.login_expired:
                        message = f" 签到时服务器返回登录失效，请尝试重新登录绑定账户"
                        per_msg = f'{signer.record.nickname} 签到时服务器返回登录失效，请尝试重新登录绑定账户'
                    elif sign_status.need_verify:
                        message = (f" 『{signer.name}』签到时可能遇到验证码拦截，"
                                   "请尝试使用命令『/账号设置』更改设备平台，若仍失败请手动前往米游社签到")
                        per_msg = f'{signer.record.nickname} 签到时可能遇到验证码拦截'
                    else:
                        message = f" 签到失败，请稍后再试"
                        per_msg = f'{signer.record.nickname} 签到失败，请稍后再试'
                    if bot: await bot.send(event, [At(qq=user_id), message])
                    else: print(message)
                    #await asyncio.sleep(plugin_config.preference.sleep_time)
                    return_json['text_list'].append(per_msg)
                    return_json['manshuo_draw'] = [
                       {'type': 'avatar', 'subtype': 'common',
                        'img': [f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"],
                        'upshift_extra': 15,'background':'run/manshuo_test/data/img/米游社.png',
                        'content': [f"[name]米游社签到[/name]\n[time]米游社id: {UID}[/time]"]},
                       {'type': 'text','content': [per_msg]}
                   ]
                    return return_json

                # asyncio.sleep(plugin_config.preference.sleep_time)

            if user.enable_notice:
                onebot_img_msg, saa_img, qq_guild_img_msg = "", "", ""
                get_info_status, info = await signer.get_info(account.platform)
                get_award_status, awards = await signer.get_rewards()
                if not get_info_status or not get_award_status:
                    msg = f"⚠️账户 {account.display_name} 🎮『{signer.name}』获取签到结果失败！请手动前往米游社查看"
                    #logger.error(msg)
                else:
                    award = awards[info.total_sign_day - 1]
                    #logger.info(f'{account.display_name} {signer.name} 访问成功！')
                    if info.is_sign:
                        status = "签到成功！" if not signed else "已签到"
                        msg = f"🪪账户 {account.display_name}" \
                              f"\n🎮『{signer.name}』" \
                              f"\n🎮状态: {status}" \
                              f"\n{signer.record.nickname}·{signer.record.level}" \
                              "\n\n🎁今日签到奖励：" \
                              f"\n{award.name} * {award.cnt}" \
                              f"\n\n📅本月签到次数：{info.total_sign_day}"
                        #img_file = await get_file(award.icon)
                        #print(img_file)
                        img_list.append(award.icon)
                        # text_list.append(f'[title]『{signer.name}』[/title]  {signer.record.nickname}·Lv{signer.record.level}\n'
                        #                       f'签到奖励：({status})\n{award.name} * {award.cnt}\n'
                        #                       f'本月签到次数：{info.total_sign_day}')
                        text_list.append(f'[title]『{signer.name}』[/title]  {signer.record.nickname}·Lv{signer.record.level}\n'
                                              f'签到奖励：(本月签到次数：{info.total_sign_day})\n{award.name} * {award.cnt}\n')
                        pure_text_list.append(f'『{signer.name}』\n{signer.record.nickname}·Lv{signer.record.level}\n'
                                              f'签到奖励：({status})\n{award.name} * {award.cnt}\n'
                                              f'本月签到次数：{info.total_sign_day}')
                    else:
                        msg = (f"⚠️账户 {account.display_name} 🎮『{signer.name}』签到失败！请尝试重新签到，"
                               "若多次失败请尝试重新登录绑定账户")
                    #print(msg)

            #await asyncio.sleep(plugin_config.preference.sleep_time)

        if not games_has_record:
            msg = f"⚠️您的米游社账户 {account.display_name} 下不存在任何游戏账号，已跳过签到"
            if bot: await bot.send(event, [At(qq=user_id), msg])
            else: print(msg)
    #print(target)

    if user_id is None:
        user_id = 1270858640
    draw_list = [
        {'type': 'basic_set', 'img_width': 1500},
        {'type': 'avatar', 'subtype': 'common', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"],
         'upshift_extra': 15,
         'content': [f"[name]米游社签到[/name]\n[time]米游社id: {UID}[/time]"]},
         {'type': 'img', 'subtype': 'common_with_des_right', 'img': img_list, 'content': text_list,'number_per_row':2}
         ]
    #pprint.pprint(draw_list)
    return_json = {'status':True,'img_list':img_list,'text_list':text_list,
                   'manshuo_draw':[
                       {'type': 'avatar', 'subtype': 'common',
                        'img': [f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"],
                        'upshift_extra': 15,'background':'run/manshuo_test/data/img/米游社.png',
                        'content': [f"[name]米游社签到[/name]\n[time]米游社id: {UID}[/time]"]},
                       {'type': 'img', 'subtype': 'common_with_des_right', 'img': img_list, 'content': text_list,
                        'number_per_row': 1}
                   ]}
    #若是每日签到则直接返回
    if target == 'daily_sign':
        return return_json
    if type == 'game':
        if len(img_list) not in [0,1]:
            img_path = await manshuo_draw(draw_list)
            if bot and event:
                await bot.send(event, [At(qq=user_id),f" 您当天的米游社签到如下", Image(file=img_path)])
            else:
                print(img_path)
        else:
            if bot and event and pure_text_list:
                await bot.send(event,pure_text_list[0])
            else:
                pprint.pprint(pure_text_list[0])
    return return_json

