from run.streaming_media.service.bili_dynamic.commend import *
from run.streaming_media.service.bili_dynamic.data import *
import asyncio
import pprint
from bilibili_api import Credential,dynamic,user
from bilibili_api.user import create_subscribe_group, set_subscribe_group
from framework_common.manshuo_draw import *

async def test():
    await data_delete(7071924)
    info = await data_init()
    pprint.pprint(info)

    # data_info = await data_init()
    # credential = Credential(sessdata=data_info['cookies']['sessdata'], bili_jct=data_info['cookies']['bili_jct'],
    #                         buvid3=data_info['cookies']['buvid3'], dedeuserid=data_info['cookies']['dedeuserid'])
    # cookies_info = credential.get_cookies()
    # cookies_check = ''
    # for item in cookies_info:
    #     cookies_check += f'{item}={cookies_info[item]};'
    # pprint.pprint(cookies_info)
    # pprint.pprint(cookies_check)

    # await data_save(info)
    # info = await bili_up_dynamic_monitor_add(3546896452815007)
    # pprint.pprint(info)
    # info = await bili_followers_live_get()
    # pprint.pprint(info)

    # info = await bili_up_dynamic_monitor(161775300)
    # pprint.pprint(info)
    # path = await manshuo_draw(info)
    # print(path)

if __name__ == '__main__':
    asyncio.run(test())
