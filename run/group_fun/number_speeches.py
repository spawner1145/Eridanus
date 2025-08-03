from developTools.event.events import GroupMessageEvent
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
    # 初始化 Redis 数据库实例
    db_json=config.common_config.basic_config['redis']
    db = RedisDatabase(host=db_json['redis_ip'], port=db_json['redis_port'], db=db_json['redis_db'])

    @bot.on(GroupMessageEvent)
    async def number_speeches_count(event: GroupMessageEvent):

        context=event.pure_text
        target_group = int(event.group_id)
        from_id = int(event.sender.user_id)
        user_data = db.read_user(f'{from_id}')
        today = datetime.now()
        year, month, day = today.year, today.month, today.day
        current_day= f'{year}_{month}_{day}'
        if user_data == {} or 'number_speeches' not in user_data or f'{target_group}' not in user_data['number_speeches'] or current_day not in user_data['number_speeches'][f'{target_group}']:
            db.write_user(f'{from_id}', {'number_speeches': {f'{target_group}': {current_day: 1}}})
        elif current_day in user_data['number_speeches'][f'{target_group}']:
            db.update_user_field(f'{from_id}', f"number_speeches.{target_group}.{current_day}", int(user_data['number_speeches'][f'{target_group}'][current_day])+1)

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
        all_users = db.read_all_users()
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
        all_users = db.read_all_users()
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
