import json
import asyncio
from io import BytesIO
from datetime import datetime, timedelta
from PIL import Image as PImage
import base64
import pprint
from developTools.message.message_components import Text, Image, At
from framework_common.manshuo_draw import *
from run.anime_game_service.service.epicfree.core import *
from developTools.utils.logger import get_logger
logger=get_logger()

async def epic_free_game_get(bot=None,event=None,proxy_for_draw='http://127.0.0.1:7890'):
    """epic免费游戏获取"""

    result = await get_epic_free()
    #pprint.pprint(result)
    if result['status'] is not True:
        if bot and event:await bot.send(event, result['msg'])
        else:print(result['msg'])
        return
    if bot:
        self_id=bot.id if bot.id else 2319804644
    elif event:
        self_id=event.self_id
    else:self_id=2319804644
    formatted_date = datetime.now().strftime("%Y年%m月%d日")
    draw_json = [
        {'type': 'basic_set', 'img_width': 1500, 'proxy': proxy_for_draw},
        {'type': 'avatar', 'subtype': 'common', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={self_id}&s=640"],
         'upshift_extra': 15, 'content': [f"[name]Epic游戏喜加一！！！！！！[/name]\n[time]当前时间：{formatted_date}   快来领取吧～[/time]"]},
    ]
    for content in result['content']:
        draw_json.append({'type': 'text','content':[f"[title]{content['game_name']} (原价{content['original_price']}) 正在喜加一！[/title]"]})
        draw_json.append(
               {'type': 'img', 'subtype': 'common_with_des_right',
                'img': [content['img']],
                'content': [f"[title]{content['game_name']}[/title]\n{content['companies']}\n将在 {content['end_date']} 结束免费游玩\n[des]{content['description']}[/des]"]},
               )
        print(content['img'])
    img_path = await manshuo_draw(draw_json)
    if bot and event:
        await bot.send(event, [f"{result['msg']}",Image(file=img_path)])
    else:
        return img_path
        #print(f"{result['msg']}")



if __name__ == '__main__':
    pass
    asyncio.run(epic_free_game_get())
    #asyncio.run(self_info(1270858640))
    #asyncio.run(rouge_info(1667962668,'水月'))
    #asyncio.run(rouge_detailed_info(1667962668,'界园'))