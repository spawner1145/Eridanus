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

#米游币签到
async def mys_coin_sign(user_id,bot=None,event=None):
    #pprint.pprint(PluginDataManager.plugin_data.users)
    user = PluginDataManager.plugin_data.users.get(str(user_id))
    if not user or not user.accounts:
        msg = '此用户还未绑定，请发送 ‘米游社帮助’ 查看菜单'
        if bot and event: await bot.send(event, msg)
        else: print(msg)
        return msg
    #开始进行米游币签到
    try:
        msg = await perform_bbs_sign(user, user_id, bot=bot, event=event)
    except Exception as e:
        print(e)
        traceback.print_exc()
        msg = '签到失败，请稍后重试喵'
        if bot: await bot.send(event, msg)
        else:print(msg)
    return msg




async def perform_bbs_sign(user, user_id, bot = None,event = None):
    """
    执行米游币任务函数，并发送给用户任务执行消息。

    :param user: 用户数据
    :param user_ids: 发送通知的所有用户ID
    """
    failed_accounts = []
    msg = '签到失败喵'
    for account in user.accounts.values():
        missions_state_status, missions_state = await get_missions_state(account)
        if not missions_state_status:
            if missions_state_status.login_expired:
                msg = f" 登录失效，请重新登录"
                if bot:
                    await bot.send(event, [At(qq=user_id), msg])
                else:
                    print(msg)
            continue

        myb_before_mission = missions_state.current_myb
        # 在此处进行判断。因为如果在多个分区执行任务，会在完成之前就已经达成米游币任务目标，导致其他分区任务不会执行。
        finished = all(current == mission.threshold for mission, current in missions_state.state_dict.values())
        if not finished:
            if not account.mission_games:
                msg = f" 未设置米游币任务目标分区，将跳过执行"
                if bot:
                    await bot.send(event, [At(qq=user_id), msg])
                else:
                    print(msg)
            for class_name in account.mission_games:
                class_type = BaseMission.available_games.get(class_name)
                if not class_type:
                    msg = f" 米游币任务目标分区『{class_name}』未找到，将跳过该分区"
                    if bot:
                        await bot.send(event, [At(qq=user_id), msg])
                    else:
                        print(msg)
                    continue
                mission_obj = class_type(account)
                msg = f" 开始在分区『{class_type.name}』执行米游币任务..."
                if bot:
                    recall_id = await bot.send(event, [At(qq=user_id), msg])
                else:
                    print(msg)
                # 执行任务
                sign_status, read_status, like_status, share_status = (
                    MissionStatus(),
                    MissionStatus(),
                    MissionStatus(),
                    MissionStatus()
                )
                sign_points: Optional[int] = None
                for key_name in missions_state.state_dict:
                    if key_name == BaseMission.SIGN:
                        sign_status, sign_points = await mission_obj.sign(user)
                    elif key_name == BaseMission.VIEW:
                        read_status = await mission_obj.read()
                    elif key_name == BaseMission.LIKE:
                        like_status = await mission_obj.like()
                    elif key_name == BaseMission.SHARE:
                        share_status = await mission_obj.share()
                msg = (f" 『{class_type.name}』米游币任务执行情况：\n"
                        f"签到：{'✓' if sign_status else '✕'}  +{sign_points or '未知'} 米游币\n"
                        f"阅读：{'✓' if read_status else '✕'}  "
                        f"点赞：{'✓' if like_status else '✕'}  "
                        f"分享：{'✓' if share_status else '✕'}"
                    )
                if bot:
                    await bot.send(event, [At(qq=user_id), msg])
                    await bot.recall(recall_id['data']['message_id'])
                else:
                    print(msg)
    return msg