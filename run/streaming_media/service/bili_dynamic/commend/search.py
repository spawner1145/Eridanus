from bilibili_api import login_v2, sync, search, user
import time
from bilibili_api import select_client
select_client("httpx")
from ..data import *
from ..utils import *


async def bili_up_name_search(target = None):
    result = await search.search_by_type(
        str(target),
        search_type=search.SearchObjectType.USER,
        order_type=search.OrderUser.FANS,
        order_sort=0,
    )
    user_info = {}
    num = 0
    for item in result['result']:
        num += 1
        hit_columns = item['hit_columns']
        user_info[num] = {'name':item['uname'],'id':item['mid'],'fans':item['fans'],'gender':item['gender'],
                          'sign':item['usign'],'room_id':item['room_id'],'pic':'https:' + item['upic'],'level':item['level']}
    #pprint.pprint(result)
    return user_info

async def bili_up_search(target = None, bot = None, event = None):
    u = user.User(target)
    user_info = {}
    info = await u.get_user_info()
    user_info['birthday'] = info['birthday']
    user_info['pic'] = info['face']
    user_info['name'] = info['name']
    user_info['sign'] = info['sign']
    return user_info

async def bili_up_name_search_msg(target = None):
    result = await search.search_by_type(
        str(target),
        search_type=search.SearchObjectType.USER,
        order_type=search.OrderUser.FANS,
        order_sort=0,
    )
    user_info, num, msg = {}, 0, '搜索到的结果如下：\n'
    if 'result' not in result:
        return '没有搜索到相关up喵'
    for item in result['result']:
        num += 1
        hit_columns = item['hit_columns']
        user_info[num] = {'name':item['uname'],'id':item['mid'],'fans':item['fans'],'gender':item['gender'],
                          'sign':item['usign'],'room_id':item['room_id'],'pic':'https:' + item['upic'],'level':item['level']}
        msg += f"{num}、{item['uname']} (Fans：{item['fans']})\n       id: {item['mid']}\n"
        if num > 4:break
    #pprint.pprint(result)
    if msg.endswith('\n'): msg = msg[:-1]
    return msg

async def bili_up_search_msg(target = None, bot = None, event = None):
    target = int(target)
    u = user.User(target)
    info = await u.get_user_info()
    relation_info = await u.get_relation_info()
    top_videos_info = await u.get_top_videos()
    #pprint.pprint(info)
    school = info['school'].get('name','')
    right_icon = info['vip']['label'].get('img_label_uri_hans_static',None)
    manshuo_draw_json = [{'type': 'backdrop', 'subtype': 'one_color'},
                         {'type': 'avatar', 'subtype': 'common', 'img': [info['face']], 'upshift_extra': 20,
                          'content': [f"[name]{info['name']}[/name] Lv.{info['level']} {school}\n[time]{info['sign']}[/time]"],
                          'background': ['https://i1.hdslb.com/' + info['top_photo']]},
                         f"关注数：{relation_info['following']}     粉丝数：{relation_info['follower']}" ,
                         {'type': 'img', 'subtype': 'common_with_des', 'img': [top_videos_info['pic']],
                          'label': ['代表作'],
                          'content': [f"{top_videos_info['title']}\n播放量：{top_videos_info['stat']['view']}\n"
                                      f"[des]点赞数：{top_videos_info['stat']['like']}  "
                                      f"投币数：{top_videos_info['stat']['coin']}  "
                                      f"收藏数：{top_videos_info['stat']['favorite']}[/des]"]}]

    return manshuo_draw_json