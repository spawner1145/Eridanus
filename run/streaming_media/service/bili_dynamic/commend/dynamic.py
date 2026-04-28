from bilibili_api import Credential,dynamic
from bilibili_api import select_client
select_client("httpx")
from ..data import *
from ..utils import *

async def bili_up_dynamic_get(target = None, bot = None, event = None):
    info = await data_init()
    dynamic_list_result = []
    credential = Credential(sessdata=info['cookies']['sessdata'], bili_jct=info['cookies']['bili_jct'],
                            buvid3=info['cookies']['buvid3'],dedeuserid=info['cookies']['dedeuserid'])

    dynamic_list = await dynamic.get_dynamic_page_list(credential, host_mid=int(target))
    #pprint.pprint(dynamic_list)
    for item in dynamic_list:
        #print(item.get_dynamic_id())
        dynamic_list_result.append(item.get_dynamic_id())
    return dynamic_list_result
