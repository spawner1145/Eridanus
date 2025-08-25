import pprint
import psutil

from framework_common.database_util.ManShuoDrawCompatibleDataBase import AsyncSQLiteDatabase
from run.basic_plugin.service.self_condition.core import *
import asyncio
from datetime import datetime, timedelta
import os
from developTools.message.message_components import Text, Image, At
from framework_common.manshuo_draw import *
from PIL import Image as PImage
from framework_common.framework_util.yamlLoader import YAMLManager
try:config = YAMLManager.get_instance()
except Exception as e:config = YAMLManager("run")
db=asyncio.run(AsyncSQLiteDatabase.get_instance())
botname = config.common_config.basic_config["bot"]
import gc

async def get_cpu_percent(process):
    # 在独立线程中调用阻塞的cpu_percent(interval=1.0)
    return await asyncio.to_thread(process.cpu_percent, interval=5.0)

async def get_process_info(sync=False):
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    total_memory_info = psutil.virtual_memory()
    total_memory = psutil.virtual_memory().total
    # 计算内存占比
    memory_percent = memory_info.rss / total_memory * 100
    cpu_percent = await get_cpu_percent(process)

    disk_usage = psutil.disk_usage('/')
    del process

    return {
        "memory_rss_MB": memory_info.rss / (1024 ** 2),
        "memory_percent": memory_percent,
        'total_memory_rss_MB':f'{total_memory_info.used / (1024 ** 3):.2f} GB',
        'total_memory_percent':total_memory_info.percent,
        "cpu_percent": cpu_percent,
        "disk_total_GB": disk_usage.total / (1024 ** 3),
        "disk_used_GB": disk_usage.used / (1024 ** 3),
        "disk_free_GB": disk_usage.free / (1024 ** 3),
        "disk_percent": disk_usage.percent
    }


async def self_info_core(bot=None,event=None,status=None):
    if event is not None:
        bot_id=event.self_id
        recall_id = await bot.send(event, f'开始查询bot的自身信息，请耐心等待喵')
        group_num = len((await bot.get_group_list())["data"])
        friend_num = len((await bot.get_friend_list())["data"])
    else:bot_id,group_num,friend_num=2319804644, 0, 0
    gc.collect()
    info = await get_process_info()
    info_data =await db.read_user(f'self_info')
    today = datetime.now()
    current_day = f'{today.year}_{today.month}_{today.day}'
    yesterday = f'{today.year}_{today.month}_{today.day-1}'
    memory_info,cpu_info,max_memory,max_cpu='未成功记录喵','未成功记录喵',False,False
    if current_day in info_data:
        today_info_data=info_data[current_day]
        info_list = sorted(today_info_data, key=lambda d: (int(d['time'].split('_')[0]), int(d['time'].split('_')[1])))
        if len(info_list) < 20 and yesterday in info_data:
            yesterday_info_list = sorted(info_data[yesterday],
                               key=lambda d: (int(d['time'].split('_')[0]), int(d['time'].split('_')[1])))
            for item in info_list: yesterday_info_list.append(item)
            info_list = yesterday_info_list
        if len(info_list) > 20: info_list = info_list[-20:]
        for info_check in info_list:
            if info_check['self_info']['memory_rss_MB'] > max_memory: max_memory = info_check['self_info']['memory_rss_MB']
            if info_check['self_info']['cpu_percent'] > max_cpu: max_cpu = info_check['self_info']['cpu_percent']
        memory_info={'type': 'math', 'subtype': 'bar_chart_vertical','content': [info_check['self_info']['memory_rss_MB'] for info_check in info_list],
                     'max':max_memory,'x_des':[info_check['time'].replace('_',':') for info_check in info_list],'y_des':[f'{max_memory:.2f}']}
        cpu_info={'type': 'math', 'subtype': 'bar_chart_vertical','content': [info_check['self_info']['cpu_percent'] for info_check in info_list],
                  'max':max_cpu,'x_des':[info_check['time'].replace('_',':') for info_check in info_list],'y_des':[f'{max_cpu}']}
    status_info = ''
    if status is not None:
        #pprint.pprint(status)
        status_info,cunt = f'',1
        for info_name in status['main_bot']:
            if '__pycache__' == info_name: continue
            elif status['main_bot'][info_name]['loaded'] is True:
                status_info += (f' {cunt}. 模块 {info_name} 已加载，'
                                f'函数入口：{status["main_bot"][info_name]["entrance_func_count"]} 个，'
                                f'加载功能：{status["main_bot"][info_name]["event_handlers_count"]} 个\n')
                cunt+=1
        status_info = f'[title]\n插件管理器[/title]\n  当前共有 {len(status["main_bot"])-1} 个插件, 其中 {cunt-1} 个插件成功加載\n' + status_info
    draw_info=[
        {'type': 'basic_set', 'img_width': 1000,'img_height':3000},
        {'type': 'avatar', 'subtype': 'common', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={bot_id}&s=640"],'upshift_extra': 20,
                             'content': [f"[name]{botname}的状态信息[/name]\n[time]{datetime.now().strftime('%Y年%m月%d日 %H:%M')}[/time]" ], },
        f'{botname} 当前共有群聊： {group_num} 组,   好友： {friend_num} 位',
        f'当前进程 内存 占用：{info["memory_rss_MB"]:.2f} MB (占比 {info["memory_percent"]:.2f} %)',
        {'type': 'math', 'subtype': 'bar_chart', 'content': [info["memory_percent"] / 100]},
        f'当前 内存 占用：{info["total_memory_rss_MB"]}  (占比 {info["total_memory_percent"]:.2f} %)',
        {'type': 'math', 'subtype': 'bar_chart', 'content': [info['total_memory_percent'] / 100]},
        f'当前 CPU 占用：{info["cpu_percent"]:.2f} %',
        {'type': 'math', 'subtype': 'bar_chart', 'content': [info['cpu_percent'] / 100]},
        f'当前 磁盘 使用：{info["disk_used_GB"]:.2f} GB（总 {info["disk_total_GB"]:.2f} GB，占比 {info["disk_percent"]} %）',
        {'type': 'math', 'subtype': 'bar_chart', 'content': [info["disk_percent"] / 100]},
        f'历史进程 内存 占用图（Max：{max_memory:.2f} MB）：',memory_info,f'历史进程 cpu 占用图：（Max：{max_cpu:.2f} %）',cpu_info,status_info,
    ]
    #pprint.pprint(draw_info)
    image_path = await manshuo_draw(draw_info)
    if bot and event:
        await bot.send(event, [f"当前 {botname} 的状态信息如下：",Image(file=image_path)])
        await bot.recall(recall_id['data']['message_id'])
    else:
        PImage.open(image_path).show()
    gc.collect()


async def self_info_record():
    gc.collect()
    #print('自身状态记录一次')
    info = await get_process_info()
    today = datetime.now()
    current_day = f'{today.year}_{today.month}_{today.day}'
    now = datetime.now()  # 获取当前时间
    current_time=f'{now.hour}_{now.minute}'
    info_data =await db.read_user(f'self_info')
    if info_data == {} or current_day not in info_data or info_data[current_day] is None:
        await db.write_user(f'self_info', { current_day : [{f'self_info': info, 'time': current_time}]})
    else:
        info_data[current_day].append({f'self_info': info, 'time': current_time})
        await db.write_user(f'self_info', {current_day: info_data[current_day]})

def self_info_record_sync():
    asyncio.run(self_info_record())




if __name__ == '__main__':
    asyncio.run(self_info_core())