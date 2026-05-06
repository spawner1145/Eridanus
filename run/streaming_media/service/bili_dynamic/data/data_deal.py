import asyncio
import datetime
import os
import random
import re
import traceback
from asyncio import sleep
from datetime import datetime, timedelta
import pprint
import gc
import httpx
from framework_common.database_util.ManShuoDrawCompatibleDataBase import AsyncSQLiteDatabase
db=asyncio.run(AsyncSQLiteDatabase.get_instance())

async def date_get():
    current_date = datetime.now()
    timestamp = int(current_date.timestamp())
    current_year = current_date.year
    current_month = current_date.month
    current_day = current_date.day
    day = f'{current_year}_{current_month}_{current_day}'
    month = f'{current_year}_{current_month}'
    year = f'{current_year}'
    return_json = {'day':day, 'month':month, 'year':year,'today':current_date,'time':timestamp}
    return return_json

async def data_init(upid='up_info',day_info=None):
    user_info = await db.read_user('bili_dynamic')
    upid = str(upid)
    if day_info is None:day_info = await date_get()
    user_info.setdefault('info', {})
    for key in ['cookies','dynamic_info']:
        user_info['info'].setdefault(key, {})
    for key in ['sessdata','bili_jct','buvid3','dedeuserid','ac_time_value','subscribe_group_id']:
        user_info['info']['cookies'].setdefault(key, '')
    user_info['info']['cookies'].setdefault('login_time', day_info['time'])
    user_info['info']['dynamic_info'].setdefault(upid, {})
    for key in ['check_time', 'enable', 'up_name','new_dynamic_id','is_push']:
        user_info['info']['dynamic_info'][upid].setdefault(key, '')
    for key in ['dynamic_id', 'push_groups']:
        user_info['info']['dynamic_info'][upid].setdefault(key, [])
    user_info['info']['dynamic_info'][upid].setdefault('living_info', {})
    for key in ['room_id', 'time', 'title', 'is_push', 'msg']:
        user_info['info']['dynamic_info'][upid]['living_info'].setdefault(key, '')
    # if user_info['info']['dynamic_info'][upid]['push_groups'] == '':
    #     user_info['info']['dynamic_info'][upid]['push_groups'] = []
    return user_info['info']

#检测是否需要启动的函数，距离bot启动一分钟后就不允许重新启动循环
async def dynamic_run_is_enable(up_type='check'):
    user_info = await db.read_user('bili_dynamic')
    upid = 'up_info'
    is_enable = True
    day_info = await date_get()
    user_info.setdefault(upid, {})
    if up_type == 'bot_up':
        user_info[upid]['computer_up_time'] = day_info['time']
        await db.write_user('bili_dynamic', user_info)
        return
    if day_info['time'] - user_info[upid]['computer_up_time'] > 60:
        is_enable = False
    return is_enable


#将数据保存到数据库中
async def data_save(user_info):
    await db.write_user('bili_dynamic', {f'info': user_info})