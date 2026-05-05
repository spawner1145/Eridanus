from bilibili_api import Credential,dynamic,user,select_client
select_client("httpx")
from ..data import *
from ..utils import *



async def bili_dynamic_group_show_ups(groupid):
    data_info = await data_init()
    ups_info, num = {}, 0
    for up_id in data_info['dynamic_info']:
        if data_info['dynamic_info'][up_id]['enable'] and groupid in data_info['dynamic_info'][up_id]['push_groups'] :
            ups_info[up_id] = {'name': data_info['dynamic_info'][up_id]['up_name'],}
    if ups_info == {}:
        return '本群好像没有订阅ap喵'
    msg = f'本群共订阅了 {len(ups_info)} 个up主喵：\n'
    for up_id in ups_info:
        num += 1
        msg += f'{num}、{ups_info[up_id]["name"]} ({up_id})\n'
    if msg.endswith('\n'): msg = msg[:-1]
    return msg
