from run.streaming_media.service.bili_dynamic.commend import *
from run.streaming_media.service.bili_dynamic.data import *
import asyncio
import pprint
from bilibili_api import Credential,dynamic,user
from bilibili_api.user import create_subscribe_group, set_subscribe_group
from framework_common.manshuo_draw import *

async def test():
    #await data_delete(7071924)
    info = await data_init()
    pprint.pprint(info['cookies'])
    # ccokies = {'SESSDATA':'58e68f79%2C1794278289%2C4da52%2A52',
    #            'bili_jct':'c9a6e5e8c58fea82484671e82da58cec',
    #            'buvid3':'0F8A09DC-F0A6-3969-887D-D7D122380DB579618infoc','DedeUserID':'3493087821170873',
    #            'ac_time_value':'6de37dd0b96491ecf588c242d63946c2'}
    # await bili_login(cookies=ccokies)
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

    # info = await bili_followers_live_get()
    # pprint.pprint(info)


if __name__ == '__main__':
    asyncio.run(test())
