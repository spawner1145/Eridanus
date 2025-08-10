import asyncio
import threading
import traceback
from asyncio import sleep, Lock
from concurrent.futures import ThreadPoolExecutor
from developTools.event.events import GroupMessageEvent, LifecycleMetaEvent
from developTools.message.message_components import Image
from run.streaming_media.service.Link_parsing.Link_parsing import link_prising
from run.streaming_media.service.bilibili.bili import fetch_latest_dynamic_id, fetch_dynamic
import sys
from run.streaming_media.service.bilibili.BiliCooikeManager import BiliCookieManager

from run.system_plugin.func_collection import operate_group_push_tasks

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

bili_task = None
bili_task_lock = asyncio.Lock()
async def check_bili_dynamic(bot, config):
    bot.logger.info_func("开始检查 B 站动态更新")

    # 锁
    config_lock = Lock()

    async def check_single_uid(target_uid, bilibili_type_draw):
        try:
            latest_dynamic_id1, latest_dynamic_id2 = await fetch_latest_dynamic_id(int(target_uid), bot)

            # 使用锁保护配置读取
            async with config_lock:
                dy_store = [config.streaming_media.bili_dynamic[target_uid]["latest_dynamic_id"][0],
                            config.streaming_media.bili_dynamic[target_uid]["latest_dynamic_id"][1]]
                groups = config.streaming_media.bili_dynamic[target_uid]["push_groups"].copy()  # 创建副本避免引用问题

            if latest_dynamic_id1 not in dy_store or latest_dynamic_id2 not in dy_store:
                if latest_dynamic_id1 != dy_store[0]:
                    latest_dynamic_id = latest_dynamic_id1
                else:
                    latest_dynamic_id = latest_dynamic_id2

                bot.logger.info_func(
                    f"发现新的动态 群号:{groups} 关注id: {target_uid} 最新动态id: {latest_dynamic_id}")

                try:
                    dynamic = None
                    if bilibili_type_draw == 1:
                        try:
                            dynamic = await fetch_dynamic(latest_dynamic_id,
                                                          config.streaming_media.config["bili_dynamic"][
                                                              "screen_shot_mode"])
                        except:
                            bilibili_type_draw = 2

                    if bilibili_type_draw == 2:
                        linking_prising_json = await link_prising(f'https://t.bilibili.com/{latest_dynamic_id}',
                                                                  filepath='data/pictures/cache/',
                                                                  type='dynamic_check')
                        if linking_prising_json['status']:
                            dynamic = linking_prising_json['pic_path']
                        else:
                            return  # 如果获取失败，直接返回，不更新配置

                except Exception as e:
                    bot.logger.error(f"动态获取失败 :{e} 关注id: {target_uid} 最新动态id: {latest_dynamic_id}")
                    return  # 获取动态失败时直接返回，不更新配置

                # 只有成功获取到动态内容才推送消息
                if dynamic:
                    for group_id in groups:
                        bot.logger.info_func(
                            f"推送动态 群号:{group_id} 关注id: {target_uid} 最新动态id: {latest_dynamic_id}")
                        try:
                            await bot.send_group_message(group_id, [Image(file=dynamic),
                                                                    f'\nhttps://t.bilibili.com/{latest_dynamic_id}'])
                        except:
                            bot.logger.error(
                                f"推送动态失败 群号:{group_id} 关注id: {target_uid} 最新动态id: {latest_dynamic_id}")

                    # 使用锁保护配置写入，只有成功推送后才更新配置
                    async with config_lock:
                        config.streaming_media.bili_dynamic[target_uid]["latest_dynamic_id"] = [latest_dynamic_id1,
                                                                                                latest_dynamic_id2]
                        config.save_yaml("bili_dynamic", plugin_name="streaming_media")

        except Exception as e:
            bot.logger.error(f"动态抓取失败{e} uid: {target_uid}")

    bilibili_type_draw = config.streaming_media.config["bili_dynamic"]["draw_type"]

    if config.streaming_media.config["bili_dynamic"]["并发模式"]:
        # 创建 target_uid 列表的副本，避免在迭代时字典被修改
        target_uids = list(config.streaming_media.bili_dynamic.keys())
        tasks = [check_single_uid(target_uid, bilibili_type_draw) for target_uid in target_uids]
        await asyncio.gather(*tasks)
    else:
        # 非并发模式使用副本，确保安全
        target_uids = list(config.streaming_media.bili_dynamic.keys())
        for target_uid in target_uids:
            await check_single_uid(target_uid, bilibili_type_draw)
            await sleep(10)

    bot.logger.info_func("完成 B 站动态更新检查")


async def bili_dynamic_loop(bot, config):
    """B站动态检查的主循环"""
    bot.logger.info_func("B站动态监控循环启动")
    while True:
        try:
            if not config.streaming_media.config["bili_dynamic"]["enable"]:
                bot.logger.info_func("B站动态监控已被禁用，退出循环")
                break
            await check_bili_dynamic(bot, config)

        except Exception as e:
            bot.logger.error(f"B站动态检查出错：{e}")

        interval = config.streaming_media.config["bili_dynamic"]["dynamic_interval"]
        await asyncio.sleep(interval)


def main(bot, config):
    """插件主入口，不需要创建线程"""

    @bot.on(LifecycleMetaEvent)
    async def start_bili_monitor(event):
        """生命周期事件处理"""
        if not config.streaming_media.config["bili_dynamic"]["enable"]:
            return

        global bili_task, bili_task_lock

        async with bili_task_lock:
            # 检查是否已有任务在运行
            if bili_task is not None and not bili_task.done():
                bot.logger.info("B站动态监控已在运行中")
                return

            # 创建新的监控任务
            bili_task = asyncio.create_task(bili_dynamic_loop(bot, config))
            bot.logger.info_func("B站动态监控任务已启动")

    @bot.on(GroupMessageEvent)
    async def _(event):
        if event.pure_text.startswith("看看动态"):
            target_id = event.pure_text.split("看看动态")[1]
            bot.logger.info(f"Fetching dynamic id of {target_id}")
            dynamic_id1, dynamic_id2 = await fetch_latest_dynamic_id(target_id,bot)
            bot.logger.info(f"Dynamic id of {target_id} is {dynamic_id1} {dynamic_id2}")
            p = await fetch_dynamic(dynamic_id1, config.streaming_media.config["bili_dynamic"]["screen_shot_mode"])
            await bot.send(event, Image(file=p))
            p = await fetch_dynamic(dynamic_id2, config.streaming_media.config["bili_dynamic"]["screen_shot_mode"])
            await bot.send(event, Image(file=p))

    @bot.on(GroupMessageEvent)
    async def _(event):
        if event.pure_text.startswith("/bili add "):
            target_id = event.pure_text.split("/bili add ")[1]  # 注意是str
            try:
                target_id = int(target_id)
            except ValueError:
                await bot.send(event, "无效的uid")
                return
            bot.logger.info_func(f"添加动态关注 群号：{event.group_id} 关注id: {target_id}")
            await operate_group_push_tasks(bot, event, config, task_type="bilibili", operation=True,
                                           target_uid=int(target_id))
        elif event.pure_text.startswith("/bili remove "):
            target_id = event.pure_text.split("/bili remove ")[1]  # 注意是str
            try:
                target_id = int(target_id)
            except ValueError:
                await bot.send(event, "无效的uid")
                return
            bot.logger.info_func(f"取消动态关注 群号：{event.group_id} 关注id: {target_id}")
            await operate_group_push_tasks(bot, event, config, task_type="bilibili", operation=False,
                                           target_uid=int(target_id))

    @bot.on(GroupMessageEvent)
    async def _(event):
        if event.pure_text == "/bili login":
            async with BiliCookieManager() as manager:
                await manager.get_cookies(auto_login=True,bot=bot,group_id=event.group_id)
                await manager._cleanup()
