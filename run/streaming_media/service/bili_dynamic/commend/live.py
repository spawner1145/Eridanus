from bilibili_api import Credential,dynamic,user,live
from bilibili_api import select_client
select_client("httpx")
from ..data import *
from ..utils import *

async def bili_followers_live_get(target = None, bot = None, event = None):
    info = await data_init()
    live_list_result = {}
    credential = Credential(sessdata=info['cookies']['sessdata'], bili_jct=info['cookies']['bili_jct'],
                            buvid3=info['cookies']['buvid3'],dedeuserid=info['cookies']['dedeuserid'])

    live_list = await live.get_live_followers_info(False, credential)
    #pprint.pprint(live_list)
    for item in live_list['rooms']:
        #print(item.get_dynamic_id())
        live_list_result[item['uid']] = {'title':item['title'], 'roomid':item['roomid'], 'time':item['live_time']}
    return live_list_result