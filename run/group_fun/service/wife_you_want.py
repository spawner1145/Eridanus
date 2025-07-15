import asyncio
import calendar
import time

from framework_common.manshuo_draw.manshuo_draw import manshuo_draw

from datetime import datetime
from framework_common.manshuo_draw import *
import aiosqlite
import requests
from PIL import Image, ImageDraw, ImageFont
from framework_common.framework_util.yamlLoader import YAMLManager

db_json=YAMLManager("run").common_config.basic_config['redis']
db = RedisDatabase(host=db_json['redis_ip'], port=db_json['redis_port'], db=db_json['redis_db'])



# 添加或更新用户数据
async def add_or_update_user(category_name, group_name, username, times):
    global db
    db.write_user("WifeYouWant", {category_name:{group_name:{username:times}}})

# 添加或更新整组用户数据
async def add_or_update_user_collect(queue_check_make):
    for user_info in queue_check_make:
        category_name, group_name, username, times=user_info[2], user_info[1], user_info[0], user_info[3]
        await add_or_update_user(category_name, group_name, username, times)

# 查询某个小组的用户数据，按照次数排序
async def query_group_users(category_name, group_name):
    global db
    content = db.read_user("WifeYouWant")
    if content and f'{category_name}' in content and f'{group_name}' in content[f'{category_name}']:
        content_dict = content[f'{category_name}'][f'{group_name}']
    else:
        return [(1,1)]
    sorted_data = sorted(content_dict.items(), key=lambda item: item[1], reverse=True)
    return sorted_data



# 查询某个小组下特定用户的数据
async def query_user_data(category_name, group_name, username):
    global db
    content = db.read_user("WifeYouWant")
    if content and f'{category_name}' in content and f'{group_name}' in content[f'{category_name}'] and f'{username}' in content[f'{category_name}'][f'{group_name}']:
        user_data = content[f'{category_name}'][f'{group_name}'][f'{username}']
        return user_data
    else:
        return None



# 删除类别及其关联数据
async def delete_category(category_name):
    global db
    db.delete_user_field("WifeYouWant", f'{category_name}')



# 删除组别及其关联用户
async def delete_group(category_name, group_name):
    global db
    db.delete_user_field("WifeYouWant", "category_name.group_name")







async def manage_group_status(user_id, group_id,type,status=None):#顺序为：个人，组别和状态
    if status is None:
        context = await query_user_data(f'{type}', f'{group_id}', f"{user_id}")
        if context is None :
            await add_or_update_user(f'{type}', f'{group_id}', f"{user_id}", 0)
        return await query_user_data(f'{type}', f'{group_id}', f"{user_id}")
    else:
        await add_or_update_user(f'{type}', f'{group_id}', f"{user_id}", status)
        return await query_user_data(f'{type}', f'{group_id}', f"{user_id}")

async def manage_group_add(from_id, target_id, target_group):
    times_from=await manage_group_status(from_id, target_group, 'wife_from_Year')
    times_target=await manage_group_status(target_id, target_group, 'wife_target_Year')
    await manage_group_status(from_id, target_group, 'wife_from_Year',times_from+1)
    await manage_group_status(target_id, target_group, 'wife_target_Year',times_target+1)

    times_from=await manage_group_status(from_id, target_group, 'wife_from_month')
    times_target=await manage_group_status(target_id, target_group, 'wife_target_month')
    await manage_group_status(from_id, target_group, 'wife_from_month',times_from+1)
    await manage_group_status(target_id, target_group, 'wife_target_month',times_target+1)

    times_from=await manage_group_status(from_id, target_group, 'wife_from_week')
    times_target=await manage_group_status(target_id, target_group, 'wife_target_week')
    await manage_group_status(from_id, target_group, 'wife_from_week',times_from+1)
    await manage_group_status(target_id, target_group, 'wife_target_week',times_target+1)

    times_from=await manage_group_status(from_id, target_group, 'wife_from_day')
    times_target=await manage_group_status(target_id, target_group, 'wife_target_day')
    await manage_group_status(from_id, target_group, 'wife_from_day',times_from+1)
    await manage_group_status(target_id, target_group, 'wife_target_day',times_target+1)

async def manage_group_check(target_group,type):

    times_from= await query_group_users(f'wife_from_{type}', target_group)
    times_target=await query_group_users(f'wife_target_{type}', target_group)
    return times_from,times_target

async def PIL_lu_maker(today , target_id,target_name,type='lu',contents=None):
    #print('进入图片制作')
    year, month,day= today.year, today.month ,today.day
    current_year_month = f'{year}_{month}'
    lu_list=await query_group_users(target_id, current_year_month)
    lu_content={}
    for lu in lu_list:
        if lu[1] == 1:
            times = await manage_group_status('lu', f'{year}_{month}_{lu[0]}', target_id)
            lu_content[f'{int(lu[0])-1}']={'type':'lu','times':times}
        elif lu[1] == 2:
            lu_content[f'{int(lu[0])-1}'] = {'type': 'nolu', 'times':1}

    if type == 'lu':
        length_today = await manage_group_status('lu_length', f'{year}_{month}_{day}',target_id)
        length_total = await manage_group_status('lu_length_total', f'basic_info', target_id)
        times_total = await manage_group_status('lu_times_total', f'basic_info', target_id)
        today_times = lu_content[f'{day-1}']['times']
        content=f"[title]{today.strftime('%Y年%m月')}的开🦌计划[/title]\n今天🦌了{today_times}次，牛牛可开心了.今天牛牛一共变长了{length_today}cm\n您一共🦌了{times_total}次，现在牛牛一共{length_total}cm!!!"
    elif type == 'supple_lu':
        length_today = await manage_group_status('lu_length', f'{year}_{month}_{day}',target_id)
        length_total = await manage_group_status('lu_length_total', f'basic_info', target_id)
        times_total = await manage_group_status('lu_times_total', f'basic_info', target_id)
        content=f"[title]{today.strftime('%Y年%m月')}的开🦌计划[/title]\n您补🦌了！！！！！，今天牛牛一共变长了{length_today}cm\n您一共🦌了{times_total}次，现在牛牛一共{length_total}cm!!!"
    elif type == 'nolu':
        content = f"[title]{today.strftime('%Y年%m月')}的开🦌计划[/title]\n您今天戒鹿了，非常棒！"

    formatted_time = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    draw_content=[
        {'type': 'avatar', 'subtype': 'common', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={target_id}&s=640"],'upshift_extra': 25,
         'content': [f"[name]{target_name}[/name]\n[time]{formatted_time}[/time]" ], 'type_software': 'lu', },
        str(content),
        {'type': 'games', 'subtype': 'LuRecordMake','content_list': lu_content},
    ]
    img_path=await manshuo_draw(draw_content)
    return img_path



async def daily_task():
    today = datetime.today()
    weekday = today.weekday()
    month = datetime.now().month
    day = datetime.now().day
    await delete_category('wife_from_day')
    await delete_category('wife_target_day')
    if int(weekday) == 0:
        await delete_category('wife_from_week')
        await delete_category('wife_target_week')
    if int(day) == 1:
        await delete_category('wife_from_month')
        await delete_category('wife_target_month')
    print(f"每日今日老婆已重置")

# 包装一个同步任务来调用异步任务
def run_async_task():
    asyncio.run(daily_task())

def today_check_api(today_wife_api,header,num_check=None):
    if num_check is None:
        num_check=0
    headers = {'Referer': header}
    try:
        response=requests.get(today_wife_api[num_check], headers=headers)
        return response
    except:
        return None  #接口寄了是


if __name__ == '__main__':
    DATABASE = "wifeyouwant.db"  # 修改路径为小写
    target_id=1270858640
    current_date=datetime.today()
    asyncio.run(PIL_lu_maker(current_date, target_id,'manshuo'))
