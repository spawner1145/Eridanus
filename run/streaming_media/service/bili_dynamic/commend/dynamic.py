from bilibili_api import Credential,dynamic,user
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




#获取当前登录用户的关注动态页
async def bili_user_get_sub_up_dynamic(data_info = None, credential = None):
    if data_info is None: data_info = await data_init()
    return_json = {'status':True, 'msg':'', 'dynamic_id_list':[], 'dynamic_info_upid':{}}
    if credential is None: credential = Credential(sessdata=data_info['cookies']['sessdata'], bili_jct=data_info['cookies']['bili_jct'],
                            buvid3=data_info['cookies']['buvid3'], dedeuserid=data_info['cookies']['dedeuserid'])
    # 检测credential需不需要刷新，此处缺少相关值无法自动刷新，只能重新登录
    # if await credential.check_refresh():
    #     return_json['status'] = False
    #     return return_json

    dynamic_info_list = await dynamic.get_dynamic_page_info(credential)
    pprint.pprint(dynamic_info_list)
    for dynamic_info in dynamic_info_list['items']:
        dynamic_id = dynamic_info['id_str']
        dynamic_upid = dynamic_info['modules']['module_author']['mid']
        return_json['dynamic_id_list'].append(dynamic_id)
        if dynamic_upid not in return_json['dynamic_info_upid']:
            return_json['dynamic_info_upid'][dynamic_upid] = []
        return_json['dynamic_info_upid'][dynamic_upid].append(dynamic_id)
    return return_json