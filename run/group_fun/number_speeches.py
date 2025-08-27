from collections import defaultdict

from developTools.event.events import GroupMessageEvent
from framework_common.database_util.ManShuoDrawCompatibleDataBase import AsyncSQLiteDatabase
from framework_common.framework_util.yamlLoader import YAMLManager
from developTools.event.events import GroupMessageEvent,LifecycleMetaEvent
from developTools.message.message_components import Record, Node, Text, Image, At
from datetime import datetime, timedelta
from framework_common.utils.install_and_import import install_and_import
dateutil=install_and_import('python-dateutil', 'dateutil')
from dateutil.relativedelta import relativedelta
import time
from framework_common.manshuo_draw import *
import asyncio
from concurrent.futures import ThreadPoolExecutor

def main(bot, config):


    db=asyncio.run(AsyncSQLiteDatabase.get_instance())

    speech_cache = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    global batch_update_task
    batch_update_task = False


    async def batch_update_speeches():
        """优化后的批量更新函数 - 大幅减少数据库操作次数"""
        while True:
            try:
                await asyncio.sleep(300)

                if not speech_cache:
                    continue
                bot.logger.info(f"Start batch update speeches for {len(speech_cache)} users")

                current_batch = dict(speech_cache)

                await db.batch_update_speech_counts(current_batch)

                for user_id in current_batch.keys():
                    if user_id in speech_cache:
                        del speech_cache[user_id]

                bot.logger.info(f"Successfully batch updated {len(current_batch)} users")
            except Exception as e:
                bot.logger.error(f"Batch update error: {e}")

    @bot.on(GroupMessageEvent)
    async def on_start(event: GroupMessageEvent):
        """启动批量更新任务"""
        global batch_update_task
        if not batch_update_task:
            asyncio.create_task(batch_update_speeches())
            batch_update_task = True
            bot.logger.info("Batch update task started")

    @bot.on(GroupMessageEvent)
    async def number_speeches_count(event: GroupMessageEvent):
        """记录发言计数到内存缓存"""
        context = event.pure_text
        target_group = int(event.group_id)
        from_id = int(event.sender.user_id)
        today = datetime.now()
        year, month, day = today.year, today.month, today.day
        current_day = f'{year}_{month}_{day}'

        # 使用默认字典，自动创建嵌套结构
        speech_cache[from_id][target_group][current_day] += 1

    # 手动触发批量更新的函数（用于测试或特殊情况）
    async def manual_batch_update():
        """手动触发批量更新"""
        try:
            if speech_cache:
                current_batch = dict(speech_cache)
                await db.batch_update_speech_counts(current_batch)
                speech_cache.clear()
                bot.logger.info("Manual batch update completed")
            else:
                bot.logger.info("No data to update")
        except Exception as e:
            bot.logger.error(f"Manual batch update error: {e}")

    # 性能监控函数
    async def monitor_cache_performance():
        """监控缓存性能"""
        while True:
            await asyncio.sleep(60)  # 每分钟检查一次

            if speech_cache:
                total_users = len(speech_cache)
                total_records = sum(
                    len(groups) * len(days)
                    for groups in speech_cache.values()
                    for days in groups.values()
                )

                bot.logger.info(f"Cache stats - Users: {total_users}, Records: {total_records}")

                # 如果缓存过大，提前触发更新
                if total_records > 10000:  # 超过1万条记录时提前更新
                    bot.logger.warning("Cache size exceeded threshold, triggering early update")
                    await manual_batch_update()

    # 启动性能监控
    # asyncio.create_task(monitor_cache_performance())

    @bot.on(GroupMessageEvent)
    async def number_speeches_check(event: GroupMessageEvent):
        context = event.pure_text
        flag=True
        for i in ['发言排行','发言次数','bb次数','bb排行','b话王','逼话王','壁画王']:
            if i in context:
                context=context.replace(i,'')
                flag=False
        if flag:return
        if '今日' == context or '每日' == context:today = datetime.now()
        elif '昨日' == context:today =datetime.now() - timedelta(days=1)
        elif '明日' == context:
            await bot.send(event, '小南娘说话还挺逗')
            return
        else:return
        bot.logger.info(f"获取到发言排行榜查询需求")
        recall_id = await bot.send(event, f'收到查询指令，请耐心等待喵')
        year, month, day = today.year, today.month, today.day
        current_day = f'{year}_{month}_{day}'
        all_users =await db.read_all_users()
        target_group = int(event.group_id)
        number_speeches_check_list = []
        #处理得出本群的人员信息表
        for user in all_users:
            if 'number_speeches' in all_users[user] and f'{target_group}' in all_users[user]['number_speeches'] and current_day in all_users[user]['number_speeches'][f'{target_group}']:
                try:
                    target_name = (await bot.get_group_member_info(target_group, user))['data']['nickname']
                except:
                    target_name = '小壁画'
                number_speeches_check_list.append({'name':user,'nicknime':target_name,'number_speeches_count':all_users[user]['number_speeches'][f'{target_group}'][current_day]})
        number_speeches_check_list_nolimited = sorted(number_speeches_check_list, key=lambda x: x["number_speeches_count"], reverse=True)
        number_speeches_check_list=[]
        for item in number_speeches_check_list_nolimited:
            number_speeches_check_list.append(item)
            if len(number_speeches_check_list) >= 16: break
        for idx, item in enumerate(number_speeches_check_list, start=1):
            item["rank"] = idx
        bot.logger.info(f"进入图片制作")
        number_speeches_check_draw_list = [
            {'type': 'basic_set','img_width':1200,'auto_line_change':False},
            {'type': 'avatar', 'subtype': 'common', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={event.self_id}&s=640"],
             'content': [f"[name]{context}发言排行榜[/name]\n[time]{datetime.now().strftime('%Y年%m月%d日 %H:%M')}[/time]"]},
            {'type': 'avatar', 'subtype': 'common', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={list['name']}&s=640" for list in number_speeches_check_list],
             'content': [f"[name]{list['nicknime']}[/name]\n[time]发言次数：{list['number_speeches_count']}次 排名：{list['rank']}[/time]" for list in number_speeches_check_list], 'number_per_row': 2,
             'background': [f"https://q1.qlogo.cn/g?b=qq&nk={list['name']}&s=640" for list in number_speeches_check_list]},
        ]
        await bot.send(event, Image(file=(await manshuo_draw(number_speeches_check_draw_list))))
        await bot.recall(recall_id['data']['message_id'])


    @bot.on(GroupMessageEvent)
    async def number_speeches_check_month(event: GroupMessageEvent):
        context = event.pure_text
        flag=True
        for i in ['发言排行','发言次数','bb次数','bb排行','b话王','逼话王','壁画王']:
            if i in context:
                context=context.replace(i,'')
                flag=False
        if flag:return
        if '本月' == context or '当月' == context:today = datetime.now()
        elif '上个月' == context or '上月' == context:

            today =datetime.now() - relativedelta(months=1)
        elif '明月' == context:
            await bot.send(event, '小南娘说话还挺逗')
            return
        else:return
        bot.logger.info(f"获取到发言排行榜查询需求")
        recall_id = await bot.send(event, f'收到查询指令，请耐心等待喵')
        year, month, day = today.year, today.month, today.day
        current_month = f'{year}_{month}'
        all_users =await db.read_all_users()
        target_group = int(event.group_id)
        number_speeches_check_list = []
        #处理得出本群的人员信息表
        for user in all_users:
            if 'number_speeches' in all_users[user] and f'{target_group}' in all_users[user]['number_speeches']:
                count=0
                for count_check in all_users[user]['number_speeches'][f'{target_group}']:
                    if current_month in count_check: count += int(all_users[user]['number_speeches'][f'{target_group}'][count_check])
                target_name = (await bot.get_group_member_info(target_group, user))['data']['nickname']
                number_speeches_check_list.append({'name':user,'nicknime':target_name,'number_speeches_count':count})
        number_speeches_check_list_nolimited = sorted(number_speeches_check_list, key=lambda x: x["number_speeches_count"], reverse=True)
        number_speeches_check_list=[]
        for item in number_speeches_check_list_nolimited:
            number_speeches_check_list.append(item)
            if len(number_speeches_check_list) >= 16: break
        for idx, item in enumerate(number_speeches_check_list, start=1):
            item["rank"] = idx
        bot.logger.info(f"进入图片制作")
        number_speeches_check_draw_list = [
            {'type': 'basic_set','img_width':1400,'auto_line_change':False},
            {'type': 'avatar', 'subtype': 'common', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={event.self_id}&s=640"],
             'content': [f"[name]{context}发言排行榜[/name]\n[time]{datetime.now().strftime('%Y年%m月%d日 %H:%M')}[/time]"]},
            {'type': 'avatar', 'subtype': 'common', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={list['name']}&s=640" for list in number_speeches_check_list],
             'content': [f"[name]{list['nicknime']}[/name]\n[time]发言次数：{list['number_speeches_count']}次 排名：{list['rank']}[/time]" for list in number_speeches_check_list], 'number_per_row': 2,
             'background': [f"https://q1.qlogo.cn/g?b=qq&nk={list['name']}&s=640" for list in number_speeches_check_list]},
        ]
        await bot.send(event, Image(file=(await manshuo_draw(number_speeches_check_draw_list))))
        await bot.recall(recall_id['data']['message_id'])
