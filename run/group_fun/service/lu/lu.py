from framework_common.database_util.ManShuoDrawCompatibleDataBase import AsyncSQLiteDatabase
from run.anime_game_service.service.skland.core import *
import json
import time
import asyncio
from io import BytesIO
from datetime import datetime, timedelta
from PIL import Image as PImage
import base64
import pprint
from developTools.message.message_components import Text, Image, At
from framework_common.manshuo_draw import *
from run.group_fun.service.lu.core import *

db=asyncio.run(AsyncSQLiteDatabase.get_instance())



async def today_lu(userid,times,bot=None,event=None):
    day_info = await date_get()
    user_info =await data_init(userid,day_info)
    update_json = {'type':'lu_done','times':times}
    await data_update(user_info,update_json,day_info)
    if bot and event:target_name = (await bot.get_group_member_info(event.group_id, userid))['data']['nickname']
    else:target_name = '您'
    content = [f"{target_name} 的{day_info['today'].strftime('%Y年%m月')}的开🦌计划",
               f"今天🦌了 {user_info['lu_done']['data'][day_info['day']]} 次，牛牛可开心了，",
               f"今天牛牛一共变长了 {user_info['length']['data'][day_info['day']]} cm",
               f"您一共🦌了 {user_info['collect']['lu_done']} 次，现在牛牛一共 {user_info['collect']['length']} cm!!!"]
    img_path = await lu_img_maker(user_info,content,day_info)
    await db.write_user(userid, {'lu': user_info})
    if bot and event:
        recall_id = await bot.send(event, [At(qq=userid)," 今天🦌了！",Image(file=img_path)])
        return recall_id
    else:
        pprint.pprint('今天🦌了！')

async def supple_lu(userid,bot=None,event=None):
    day_info = await date_get()
    user_info =await data_init(userid,day_info)

    times_record = user_info['lu_supple']['record']
    times_record_check = int(times_record) // 3
    if times_record_check == 0:
        await bot.send(event, [At(qq=target_id),
                               f' 您的补🦌次数好像不够呢喵~~（已连续{times_record}天）(3天1次)'])
    update_json = {'type':'supple_lu'}
    await data_update(user_info,update_json,day_info)
    if bot and event:target_name = (await bot.get_group_member_info(event.group_id, userid))['data']['nickname']
    else:target_name = '您'
    content = [f"{target_name} 的{day_info['today'].strftime('%Y年%m月')}的开🦌计划",
               f"已成功补🦌! ",
               f"您一共🦌了 {user_info['collect']['lu_done']} 次，现在牛牛一共 {user_info['collect']['length']} cm!!!"]
    img_path = await lu_img_maker(user_info,content,day_info)
    await db.write_user(userid, {'lu': user_info})
    if bot and event:
        recall_id = await bot.send(event, [At(qq=userid)," 已成功补🦌了！",Image(file=img_path)])
        return recall_id
    else:
        pprint.pprint('已成功补🦌了！')

async def check_lu(userid,bot=None,event=None):
    day_info = await date_get()
    user_info =await data_init(userid,day_info)
    if bot and event:target_name = (await bot.get_group_member_info(event.group_id, userid))['data']['nickname']
    else:target_name = '您'
    content = [f"{target_name} 的{day_info['today'].strftime('%Y年%m月')}的开🦌计划",
               f"今天🦌了 {user_info['lu_done']['data'][day_info['day']]} 次，牛牛可开心了，",
               f"今天牛牛一共变长了 {user_info['length']['data'][day_info['day']]} cm",
               f"您一共🦌了 {user_info['collect']['lu_done']} 次，现在牛牛一共 {user_info['collect']['length']} cm!!!"]
    img_path = await lu_img_maker(user_info,content,day_info)
    await db.write_user(userid, {'lu': user_info})
    if bot and event:
        recall_id = await bot.send(event, [At(qq=userid)," 这是您的开🦌记录！",Image(file=img_path)])
        return recall_id
    else:
        pprint.pprint('今天🦌了！')


if __name__ == '__main__':
    start_time = time.time()
    target_id = 1270858640
    asyncio.run(supple_lu(target_id))
    end_time = time.time()  # 记录结束时间
    duration = end_time - start_time  # 计算持续时间，单位为秒

    print(f"程序运行了 {duration:.2f} 秒")