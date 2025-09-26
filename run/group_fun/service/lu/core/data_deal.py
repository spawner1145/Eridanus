import asyncio
import datetime
import os
import random
import re
import traceback
from asyncio import sleep
from datetime import datetime
import pprint
import gc
import httpx
from framework_common.database_util.ManShuoDrawCompatibleDataBase import AsyncSQLiteDatabase
db=asyncio.run(AsyncSQLiteDatabase.get_instance())

async def data_init(userid,day_info=None):
    user_info = await db.read_user(userid)
    if day_info is None:day_info = await date_get()
    first_read = False
    if 'lu' not in user_info:first_read=True
    user_info.setdefault('lu', {})
    #初始化变量
    for key in ['lu_done', 'lu_no', 'times', 'length', 'lu_supple', 'others', 'collect']:
        user_info['lu'].setdefault(key, {})
    user_info['lu']['lu_supple'].setdefault('record', {})
    for item in ['lu_done', 'lu_no', 'length']:
        for key in ['data']:
            user_info['lu'][item].setdefault(key, {})
            user_info['lu'][item][key].setdefault(day_info['day'], 0)
    for key in ['year','month']:
        user_info['lu']['times'].setdefault(key, {})
        user_info['lu']['times'][key].setdefault(day_info[key], 0)
    for key in ['lu_done', 'lu_no', 'length']:
        user_info['lu']['collect'].setdefault(key, 0)

    #这里加入旧数据库读取合并函数
    if first_read:
        old_data = await db.read_user("WifeYouWant")
        #pprint.pprint(old_data[f'{userid}'])
        if old_data and f'{userid}' in old_data and f'basic_info' in old_data[f'{userid}'] :
            if f'lu_times_total' in old_data[f'{userid}'][f'basic_info']:
                user_info['lu']['collect']['lu_done'] = old_data[f'{userid}'][f'basic_info']['lu_times_total']
            if f'lu_length_total' in old_data[f'{userid}'][f'basic_info']:
                user_info['lu']['collect']['length'] = old_data[f'{userid}'][f'basic_info']['lu_length_total']
        if old_data and f'{userid}' in old_data and f'lu_others' in old_data[f'{userid}'] and f'lu_record' in old_data[f'{userid}'][f'lu_others']:
            user_info['lu']['lu_supple']['record'] = old_data[f'{userid}'][f'lu_others']['lu_record']
        month_data, year_data = 0, 0
        if f'{userid}' in old_data:
            for data in old_data[f'{userid}']:
                if not ('lu' in old_data[f'{userid}'][data] and 'lu_length' in old_data[f'{userid}'][data]): continue
                user_info['lu']['lu_done']['data'][data] = old_data[f'{userid}'][data]['lu']
                user_info['lu']['length']['data'][data] = old_data[f'{userid}'][data]['lu_length']
                if day_info['year'] in data: year_data += old_data[f'{userid}'][data]['lu']
                if day_info['month'] in data: month_data += old_data[f'{userid}'][data]['lu']
            user_info['lu']['times']['month'][day_info['month']], user_info['lu']['times']['year'][
                day_info['year']] = month_data, year_data

    #pprint.pprint(user_info['lu'])
    return user_info['lu']


async def date_get():
    current_date = datetime.now()
    current_year = current_date.year
    current_month = current_date.month
    current_day = current_date.day
    day = f'{current_year}_{current_month}_{current_day}'
    month = f'{current_year}_{current_month}'
    year = f'{current_year}'
    return_json = {'day':day, 'month':month, 'year':year,'today':current_date}
    return return_json


async def data_update(user_info,update_json,day_info=None):
    if day_info is None:day_info = await date_get()
    if update_json['type'] == 'lu_done':
        length_add = sum(random.randint(1, 10) for _ in range(update_json['times']))
        #更新每日的lu数据
        user_info['lu_done']['data'][f"{day_info['day']}"] = user_info['lu_done']['data'][f"{day_info['day']}"] + update_json['times']
        user_info['length']['data'][f"{day_info['day']}"] = user_info['length']['data'][f"{day_info['day']}"] + length_add
        user_info['collect']['lu_done'], user_info['collect']['length'] = user_info['collect']['lu_done'] + update_json['times'], user_info['collect']['length'] + length_add
        #更新位于times的年度记录数据
        user_info['times']['month'][f"{day_info['month']}"] = user_info['times']['month'][f"{day_info['month']}"] + update_json['times']
        user_info['times']['year'][f"{day_info['year']}"] = user_info['times']['year'][f"{day_info['year']}"] + update_json['times']
    elif update_json['type'] == 'lu_no':
        user_info['lu_no']['data'][f"{day_info['day']}"] = user_info['lu_no']['data'][f"{day_info['day']}"] + update_json['times']
        user_info['collect']['lu_no'] = user_info['collect']['lu_no'] + update_json['times']
    elif update_json['type'] == 'supple_lu':
        user_info['lu_supple']['record'] -= 3
        for i in range(day_info['today'].day):
            day = day_info['today'].day - i
            today = f"{day_info['month']}_{day}"
            if today not in user_info['lu_done']['data']:
                length_add = random.randint(1, 10)
                user_info['lu_done']['data'][today] = 1
                user_info['length']['data'][today] = length_add
                user_info['collect']['lu_done'], user_info['collect']['length'] = user_info['collect']['lu_done'] + 1, user_info['collect']['length'] + length_add
                # 更新位于times的年度记录数据
                user_info['times']['month'][f"{day_info['month']}"] = user_info['times']['month'][f"{day_info['month']}"] + 1
                user_info['times']['year'][f"{day_info['year']}"] = user_info['times']['year'][f"{day_info['year']}"] + 1
                break

async def user_list_get(user_list,day_info=None,type='month'):
    if day_info is None: day_info = await date_get()
    deal_user_list = []
    for userid in user_list:
        data_info = await data_init(userid)
        if type == 'month':
            data = data_info['times']['month'][day_info['month']]
        elif type == 'year':
            data = data_info['times']['year'][day_info['year']]
        elif type == 'total':
            data = data_info['collect']['lu_done']
        deal_user_list.append({'times':data,'userid':userid})
    deal_user_list.sort(key=lambda x: list(x.values())[0], reverse=True)
    deal_user_list = deal_user_list[:10]

    return deal_user_list


if __name__ == '__main__':
    target_id = 1270858640
    #asyncio.run(data_init(target_id))
    asyncio.run(user_list_get([1270858640,2191331427]))