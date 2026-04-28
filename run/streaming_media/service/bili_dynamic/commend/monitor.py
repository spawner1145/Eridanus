from bilibili_api import Credential,dynamic,user
from bilibili_api import select_client
import asyncio
import gc
import requests

from bilibili_api.user import create_subscribe_group, set_subscribe_group,get_self_info,RelationType

select_client("httpx")
from datetime import datetime, timedelta
from ..data import *
from ..utils import *
from run.streaming_media.service.Link_parsing.Link_parsing import link_prising
from developTools.utils.logger import get_logger
logger=get_logger('bili_dynamic_monitor')

async def bili_up_dynamic_monitor_is_enable(target = None):
    data_info = await data_init(upid=target)
    user_info = data_info['dynamic_info'][f'{target}']
    if user_info['enable'] == '':user_info['enable'] = True
    return user_info['enable']

async def bili_up_subscribe_group_all_ups_resub():
    data_info = await data_init()
    user_info = data_info['dynamic_info'][f'up_info']
    user_info['status'] = True
    #创建一个up主分类并将其up设定在此分类里
    credential = Credential(sessdata=data_info['cookies']['sessdata'], bili_jct=data_info['cookies']['bili_jct'],
                            buvid3=data_info['cookies']['buvid3'], dedeuserid=data_info['cookies']['dedeuserid'])
    # 检测credential需不需要刷新，此处缺少相关值无法自动刷新，只能重新登录
    if await credential.check_refresh():
        user_info['status'] = False
        return user_info
    #获取所有关注的up主
    up_lists = [int(item) for item in data_info['dynamic_info'] if item.isdigit() and data_info['dynamic_info'][item]['enable'] and str(item) != str(data_info['cookies']['dedeuserid'])]
    for up in up_lists:
        up_info = user.User(up, credential)
        info_get_relation = await up_info.get_relation()
        #pprint.pprint(info_get_relation)
        if info_get_relation['relation']['attribute'] not in [2,6]:
            await up_info.modify_relation(RelationType(1))
        del up_info
    #将所有订阅up主都添加到相应分组中
    info = await set_subscribe_group(up_lists,[data_info['cookies']['subscribe_group_id']],credential)
    #pprint.pprint(info)
    del credential
    return user_info

#将一个up添加到订阅列表的同时将其添加到关注分组中
async def bili_up_dynamic_monitor_add(target = None,group = None, status = True, group_status = True):
    data_info = await data_init(upid=target)
    user_info = data_info['dynamic_info'][f'{target}']
    user_info['status'] = True
    user_info['enable'] = status
    up_info = user.User(target)
    info = await up_info.get_user_info()
    user_info['up_name'] = info['name']
    if group:
        if group_status and group not in user_info['push_groups']: user_info['push_groups'].append(group)
        elif group_status is False and group in user_info['push_groups']:
            user_info['push_groups'].remove(group)
    await data_save(data_info)
    #创建一个up主分类并将其up设定在此分类里
    credential = Credential(sessdata=data_info['cookies']['sessdata'], bili_jct=data_info['cookies']['bili_jct'],
                            buvid3=data_info['cookies']['buvid3'], dedeuserid=data_info['cookies']['dedeuserid'])
    # 检测credential需不需要刷新，此处缺少相关值无法自动刷新，只能重新登录
    if await credential.check_refresh():
        user_info['status'] = False
        return user_info
    # 要先关注才行（汗
    up_info = user.User(target,credential)
    # 先查看其与本人的关系，避免重复关注
    info_get_relation = await up_info.get_relation()
    if info_get_relation['relation']['attribute'] != 2:
        await up_info.modify_relation(RelationType(1))
    #将一个up添加至相应关注分组中
    info_set_subscribe_group = await set_subscribe_group([int(target)], [int(data_info['cookies']['subscribe_group_id'])], credential)
    #pprint.pprint(info_set_subscribe_group)
    return user_info

#检测一个up的最新动态
async def bili_up_dynamic_monitor(target = None, data_info = None, day_info = None, credential = None, data_is_save = True):
    if data_info is None: data_info = await data_init(upid=target)
    if day_info is None: day_info = await date_get()
    if credential is None: credential = Credential(sessdata=data_info['cookies']['sessdata'], bili_jct=data_info['cookies']['bili_jct'],
                            buvid3=data_info['cookies']['buvid3'],dedeuserid=data_info['cookies']['dedeuserid'])
    dynamic_list_result = []
    dynamic_list = await dynamic.get_dynamic_page_list(credential, host_mid=int(target))
    #pprint.pprint(dynamic_list)
    for item in dynamic_list:
        #print(item.get_dynamic_id())
        dynamic_list_result.append(item.get_dynamic_id())
    user_info = data_info['dynamic_info'][f'{target}']
    user_info['status'] = True
    if not dynamic_list_result:
        logger.error(f"未获取到动态id列表 up_name:{user_info['up_name']}  up_id: {target}")
        user_info['status'] = False
        return user_info
    #pprint.pprint(user_info)
    user_info['new_dynamic_id'] = dynamic_list_result[0]
    if user_info['new_dynamic_id'] in user_info['dynamic_id']:
        user_info['is_push'] = False
    else:
        user_info['is_push'] = True
    for item in dynamic_list_result:
        if item not in user_info['dynamic_id']:
            user_info['dynamic_id'].append(item)
    while len(user_info['dynamic_id']) > 20:
        user_info['dynamic_id'].pop(0)
    user_info['check_time'] = day_info['time']
    #若传入了data_info，则此处不做保存，由后面统一保存一次
    if data_is_save: await data_save(data_info)
    for item in dynamic_list:
        del item
    return user_info


async def bili_dynamic_loop(bot, config):
    """B站动态检查的主循环"""
    subscribe_group_id_flag, notice_flag = True, True
    while True:
        logger.info_func("开始检测B站动态喵")
        #await bot.send_friend_message(config.common_config.basic_config["master"]['id'], f"开始检测B站动态喵")
        day_info = await date_get()
        """获取当前bot列表，避免检测多余up"""
        group_list = []
        try:
            group_info = (await bot.get_group_list())["data"]
            for item in group_info:
                if 'group_id' in item: group_list.append(item['group_id'])
        except:
            pass
        up_list = []
        #构建出需要检测的ups
        data_info = await data_init()
        for up_id in data_info['dynamic_info']:
            if data_info['dynamic_info'][up_id]['enable'] is False:continue
            group_push_list = data_info['dynamic_info'][up_id]['push_groups']
            for group_id_check in group_push_list:
                if group_id_check in group_list:
                    up_list.append(up_id)
                    break
        #当需要订阅列表不为空再执行
        if up_list != []:
            credential = Credential(sessdata=data_info['cookies']['sessdata'],
                                    bili_jct=data_info['cookies']['bili_jct'],
                                    buvid3=data_info['cookies']['buvid3'],
                                    dedeuserid=data_info['cookies']['dedeuserid'])
            #print(await credential.check_refresh())
            #检测credential需不需要刷新，此处缺少相关值无法自动刷新，只能重新登录
            if await credential.check_refresh():
                if notice_flag:
                    await bot.send_friend_message(config.common_config.basic_config["master"]['id'], f"B站登录失效，请重新登录喵")
                    notice_flag = False
                gc.collect()
                await asyncio.sleep(600)
                continue
            notice_flag = True
            for up_id in up_list:
                try:
                    dynamic_info = await bili_up_dynamic_monitor(up_id,data_info,day_info,credential,False)
                    # 若获取不到动态列表，大概率是没关注同时也没有相应分组
                    if dynamic_info['status'] is False and subscribe_group_id_flag:
                        subscribe_group_id_flag = False
                        await bot.send_friend_message(config.common_config.basic_config["master"]['id'],
                                                      f'检测到相关用户没有关注，请使用 “/bili resub” 重新关注up主们')
                except Exception as e:
                    logger.error(f"B站动态出错：{e}")
                    #await bot.send_friend_message(config.common_config.basic_config["master"]['id'],f"B站动态出错：{e}")
                    continue
                #pprint.pprint(dynamic_info)
                #检测到需要推送的情况下开始执行下一步
                if dynamic_info['is_push']:
                    new_dynamic_id = dynamic_info['new_dynamic_id']
                    if not new_dynamic_id: continue
                    for group_id in dynamic_info['push_groups']:
                        if group_id not in group_list:continue
                        try:
                            dynamic_info_prising = await link_prising(f'https://t.bilibili.com/{new_dynamic_id}')
                            logger.info_func(
                                f"推送动态 群号:{group_id} 关注id: {up_id} 最新动态id: {new_dynamic_id}")
                            await bot.send_group_message(group_id, [Image(file=dynamic_info_prising['pic_path']),
                                                                    f'\nhttps://t.bilibili.com/{new_dynamic_id}'])
                        except:
                            logger.error(
                                f"推送动态失败 群号:{group_id} 关注id: {up_id} 最新动态id: {new_dynamic_id}")
        #因为py传的都是地址，在此处同一存储即可
        await data_save(data_info)
        del credential
        #以下时间等待主要为了在分钟属于1的时候开始检测
        interval = config.streaming_media.config["bili_dynamic"]["dynamic_interval"]
        gc.collect()
        await asyncio.sleep(60)
        current_minute, current_second = datetime.now().minute, datetime.now().second
        wait_seconds = ((1 - current_minute % 10) % 10) * 60 - current_second
        await asyncio.sleep(wait_seconds)