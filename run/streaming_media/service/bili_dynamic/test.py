from run.streaming_media.service.bili_dynamic.commend import *
from run.streaming_media.service.bili_dynamic.data import *
import asyncio
import pprint
from bilibili_api import Credential,dynamic,user
from bilibili_api.user import create_subscribe_group, set_subscribe_group
from framework_common.manshuo_draw import *

async def test():
    info = await data_init()
    pprint.pprint(info)
    # info = await bili_up_dynamic_monitor_add(3546896452815007)
    # pprint.pprint(info)
    info = await bili_up_subscribe_group_all_ups_resub()
    pprint.pprint(info)

    # info = await bili_up_dynamic_monitor(161775300)
    # pprint.pprint(info)
    # path = await manshuo_draw(info)
    # print(path)

if __name__ == '__main__':
    asyncio.run(test())
