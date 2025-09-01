from framework_common.manshuo_draw import *
import httpx
from .steam import (
    get_steam_id,
    get_user_data,
    STEAM_ID_OFFSET,
    get_steam_users_info,
)
import time
from developTools.event.events import GroupMessageEvent, LifecycleMetaEvent
from developTools.message.message_components import Text, Image, At
import asyncio
from concurrent.futures import ThreadPoolExecutor
import traceback
from datetime import datetime
from developTools.utils.logger import get_logger
logger=get_logger("SteamSnooping")

def url_main(bot, config, db,steam_api_key):
    global url_activate
    url_activate = False
    @bot.on(LifecycleMetaEvent)
    async def _(event):
        global url_activate
        if not url_activate:
            url_activate = True
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: asyncio.run(steamsnoopall(bot, config, db,steam_api_key))
            )

        else:
            bot.logger.info("Steam视奸检查已启动")




async def steamsnoopall(bot, config, db, steam_api_key):
    while True:
        logger.info("开始检查steam用户活动情况")
        try:
            all_snoop_ids, all_snoop_ids_send, all_snoop_ids_steamid = [], {}, {}
            replay_content, user_times = '', None

            ids_list = await db.read_user('SteamSnoopingList')
            if not ids_list:
                return

            # 数据准备阶段（保持原逻辑）
            for targetgruop in ids_list:
                if not targetgruop.isdigit():
                    continue
                for targetid in ids_list[targetgruop]:
                    if ids_list[targetgruop][targetid] is not True:
                        continue
                    if str(ids_list[targetgruop][f'{targetid}_steamid']) not in all_snoop_ids:
                        all_snoop_ids.append(str(ids_list[targetgruop][f'{targetid}_steamid']))
                    if targetid in all_snoop_ids_send:
                        all_snoop_ids_send[targetid].append(targetgruop)
                    else:
                        all_snoop_ids_send[targetid] = [targetgruop]
                    all_snoop_ids_steamid[targetid] = ids_list[targetgruop][f'{targetid}_steamid']

            proxy = config.common_config.basic_config['proxy']['http_proxy'] if \
            config.common_config.basic_config['proxy']['http_proxy'] else None
            steam_info = await get_steam_users_info(all_snoop_ids, steam_api_key, bot, proxy)

            # 处理 Steam 数据（保持原逻辑）
            new_players_dict = {}
            for item in steam_info["response"]["players"]:
                if 'gameextrainfo' not in item:
                    item['gameextrainfo'], item['game_start_time'] = None, None
                else:
                    if (item["steamid"] in ids_list['old_players_dict']
                        and 'game_start_time' in ids_list['old_players_dict'][item["steamid"]]) \
                            and ids_list['old_players_dict'][item["steamid"]]['game_start_time'] is not None:
                        item['game_start_time'] = ids_list['old_players_dict'][item["steamid"]]['game_start_time']
                    else:
                        item['game_start_time'] = int(time.time())
                new_players_dict[item["steamid"]] = item

            await db.write_user('SteamSnoopingList', {'old_players_dict': new_players_dict})

            # 数据对比和处理
            if 'old_players_dict' in ids_list:
                old_players_dict = ids_list['old_players_dict']
            else:
                return

            today = datetime.now()
            year, month, day = today.year, today.month, today.day
            current_day = f'{year}_{month}_{day}'

            # 🚀 优化1: 批量读取用户数据
            all_userids = list(all_snoop_ids_send.keys())
            all_user_data = await db.batch_read_users([str(uid) for uid in all_userids])

            # 准备批量更新数据
            batch_updates = {}
            notification_tasks = []

            for userid in all_snoop_ids_send:
                userid_str = str(userid)
                steamid = str(all_snoop_ids_steamid[f'{userid}'])
                user_info = all_user_data.get(userid_str, {})
                user_times = None

                # 获取当前用户时间
                if ('SteamSnooping' in user_info and 'times' in user_info["SteamSnooping"]
                        and current_day in user_info["SteamSnooping"]['times']):
                    user_times = int(user_info["SteamSnooping"]['times'][current_day])

                if steamid not in new_players_dict or steamid not in old_players_dict:
                    continue
                if old_players_dict[steamid]['gameextrainfo'] == new_players_dict[steamid]['gameextrainfo']:
                    continue
                if (new_players_dict[steamid]['gameextrainfo'] in config.anime_game_service.config['steamsnooping'][
                    'game_white'] or
                        old_players_dict[steamid]['gameextrainfo'] in config.anime_game_service.config['steamsnooping'][
                            'game_white']):
                    continue

                # 构建回复内容
                replay_content = ''
                if new_players_dict[steamid]['gameextrainfo'] is not None and old_players_dict[steamid][
                    'gameextrainfo'] is not None:
                    replay_content += f"([title]{new_players_dict[steamid]['personaname']}[/title]) 停止玩 {old_players_dict[steamid]['gameextrainfo']}，开始玩 [title]{new_players_dict[steamid]['gameextrainfo']}[/title] 了"
                elif new_players_dict[steamid]['gameextrainfo'] is not None:
                    replay_content += f"([title]{new_players_dict[steamid]['personaname']}[/title]) 开始玩 [title]{new_players_dict[steamid]['gameextrainfo']}[/title] 了"
                elif old_players_dict[steamid]['gameextrainfo'] is not None:
                    time_start, time_stop = int(old_players_dict[steamid]["game_start_time"]), int(time.time())
                    hours, minutes = int((time_stop - time_start) / 3600), int((time_stop - time_start) % 3600 / 60)
                    time_str = (f"{hours} 小时 {minutes} 分钟" if hours > 0 else f"{minutes} 分钟")

                    # 计算新的游戏时间
                    if user_times is not None:
                        user_times = user_times + int(time.time() - int(old_players_dict[steamid]["game_start_time"]))
                    else:
                        user_times = int(time.time()) - int(old_players_dict[steamid]["game_start_time"])

                    # 🚀 优化2: 准备批量更新数据而不是立即写入
                    batch_updates[userid_str] = {'SteamSnooping': {'times': {current_day: user_times}}}

                    replay_content += f"([title]{new_players_dict[steamid]['personaname']}[/title]) 玩了 [title]{time_str} {old_players_dict[steamid]['gameextrainfo']}[/title] 后不玩了"
                else:
                    continue

                if replay_content == '':
                    continue

                # 🚀 优化3: 创建并发任务而不是立即执行
                task = create_notification_task(
                    bot, config, userid, steamid, replay_content,
                    user_times, new_players_dict, all_snoop_ids_send
                )
                notification_tasks.append(task)

            # 🚀 优化4: 批量更新数据库
            if batch_updates:
                await db.write_multiple_users(batch_updates)

            # 🚀 优化5: 并发执行所有通知任务
            if notification_tasks:
                results = await asyncio.gather(*notification_tasks, return_exceptions=True)

                # 处理异常结果
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"Notification task {i} failed: {result}")

        except Exception as e:
            bot.logger.error(f"Steam视奸检测出错：{e}\n{traceback.format_exc()}")
            continue

        logger.info("steam用户活动检查完成")
        await asyncio.sleep(300)


async def create_notification_task(bot, config, userid, steamid, replay_content,
                                   user_times, new_players_dict, all_snoop_ids_send):
    """创建通知任务 - 真正的异步处理"""
    try:
        if user_times is None:
            user_times = 0
        hours, minutes = int(user_times / 3600), int(user_times % 3600 / 60)
        user_times_str = (f"{hours} 小时 {minutes} 分钟" if hours > 0 else f"{minutes} 分钟")

        # 🚀 优化6: 并发获取游戏数据和群成员信息
        game_task = get_user_data(int(steamid), config.common_config.basic_config['proxy']['http_proxy'])

        # 为每个群组创建获取用户昵称的任务
        member_info_tasks = []
        for group_id in all_snoop_ids_send[userid]:
            task = get_group_member_name(bot, group_id, userid)
            member_info_tasks.append((group_id, task))

        # 等待游戏数据
        game_data = await game_task
        game = game_data["game_data"][0]

        #替换被ban的steam cdn
        new_players_dict[steamid]['avatarfull'] = game_data['avatar_url']

        # 并发获取所有群组的用户昵称
        group_results = await asyncio.gather(
            *[task for _, task in member_info_tasks],
            return_exceptions=True
        )

        # 🚀 优化7: 为每个群组并发发送消息
        send_tasks = []
        for i, (group_id, _) in enumerate(member_info_tasks):
            user_name = group_results[i] if not isinstance(group_results[i], Exception) else '未知'

            task = send_notification_message(
                bot, config, group_id, userid, user_name, replay_content,
                user_times_str, new_players_dict, steamid, game
            )
            send_tasks.append(task)

        await asyncio.gather(*send_tasks, return_exceptions=True)

    except Exception as e:
        bot.logger.error(f"Notification task for user {userid} failed: {e}")
        raise

async def get_group_member_name(bot, group_id, userid):
    """安全获取群成员昵称"""
    try:
        result = await bot.get_group_member_info(group_id, userid)
        return result['data']['nickname']
    except Exception as e:
        bot.logger.warning(f"Failed to get member name for {userid} in group {group_id}: {e}")
        return '未知'

async def send_notification_message(bot, config, group_id, userid, user_name,
                                    replay_content, user_times_str, new_players_dict,
                                    steamid, game):
    """发送通知消息"""
    try:
        bot.logger.info(f"Steam视奸检测到新活动，开始制作图片并推送，用户：{userid}，昵称：{user_name}，群号：{group_id}")

        full_content = f'[title]{user_name}[/title]' + replay_content
        #print(f'Steam Avatar: {new_players_dict[steamid]["avatarfull"]}')
        draw_json = [
            {'type': 'basic_set', 'img_width': 1500, 'proxy': config.common_config.basic_config['proxy']['http_proxy']},
            {'type': 'avatar', 'subtype': 'common',
             'img': [f'https://q1.qlogo.cn/g?b=qq&nk={userid}&s=640', new_players_dict[steamid]['avatarfull']],
             'upshift_extra': 15, 'number_per_row': 2,
             'content': [
                 f"[name]qq昵称: {user_name}[/name]\n[time]qqid:{userid}[/time]",
                 f'[name]Steam昵称: {new_players_dict[steamid]["personaname"]}[/name]\n[time]steamid：{steamid}[/time]'],
             'is_rounded_corners_img': False, 'is_stroke_img': False, 'is_shadow_img': False},
            f'{full_content}\n今天一共玩了 {user_times_str} 了哦',
            {'type': 'img', 'subtype': 'common_with_des_right',
             'img': [f"{game['game_image_url']}"],
             'content': [
                 f"[title]{game['game_name']}[/title]\n游玩时间：{game['play_time']} 小时\n{game['last_played']}"
                 f"\n成就：{game.get('completed_achievement_number')} / {game.get('total_achievement_number')}"
             ], 'number_per_row': 1, 'is_crop': False}
        ]

        image = await manshuo_draw(draw_json)
        message = [f"{config.common_config.basic_config['bot']} 发现了群友的Steam动态了哦", Image(file=image)]

        await bot.send_group_message(group_id, message)

    except Exception as e:
        bot.logger.error(f"Failed to send message to group {group_id}: {e}")
        raise










if __name__ == "__main__":
    pass
    #asyncio.run(test())

