from bilibili_api import login_v2, sync, Credential, user, select_client
from bilibili_api.user import create_subscribe_group, set_subscribe_group,get_self_info
import asyncio
from ..data import *
from ..utils import *
import requests
from .monitor import loop_cache
import datetime
from developTools.utils.logger import get_logger
logger=get_logger('bili_dynamic')
select_client("httpx")


async def bili_login(bot = None, event = None) -> None:
    recall_id, cookies_check = None, ''
    day_info = await date_get()
    qr = login_v2.QrCodeLogin(platform=login_v2.QrCodeLoginChannel.WEB) # 生成二维码登录实例，平台选择网页端
    await qr.generate_qrcode()                                          # 生成二维码
    #print(qr.get_qrcode_terminal())                                     # 生成终端二维码文本，打印
    #print(qr.get_qrcode_picture().url)
    if bot and event:
        recall_id = await bot.send(event, ['请扫描下方二维码登录喵',Image(file=qr.get_qrcode_picture().url)])
    while not qr.has_done():                                            # 在完成扫描前轮询
        #print(await qr.check_state())                                   # 检查状态
        logger.info_func(f'B站二维码状态：{(await qr.check_state())}')
        await asyncio.sleep(4)
    cookies = qr.get_credential().get_cookies()
    info = await data_init()
    info['cookies']['sessdata'] = cookies['SESSDATA']
    info['cookies']['bili_jct'] = cookies['bili_jct']
    info['cookies']['buvid3'] = cookies['buvid3']
    info['cookies']['dedeuserid'] = cookies['DedeUserID']
    info['cookies']['ac_time_value'] = cookies['ac_time_value']
    info['cookies']['subscribe_group_id'] = ''
    info['cookies']['login_time'] = day_info['time']
    #await data_save(info)
    msg = '登录成功喵，正在处理相关数据喵'
    if bot and event:
        if recall_id: await bot.recall(recall_id['data']['message_id'])
        recall_id = await bot.send(event, msg)
    logger.info(msg)
    msg = ''
    #获取对应up分组并创建一个保存的关注分组
    credential = Credential(sessdata=cookies['SESSDATA'], bili_jct=cookies['bili_jct'],
                            buvid3=cookies['buvid3'], dedeuserid=cookies['DedeUserID'])
    cookies_info = credential.get_cookies()
    for item in cookies_info:
        cookies_check += f'{item}={cookies_info[item]};'
    try:
        resp = requests.get("https://api.bilibili.com/x/relation/tags",
                            headers={'Cookie': cookies_check, 'User-Agent': 'Mozilla/5.0'},
                            params={'csrf': cookies['bili_jct'] })
        res = resp.json()
        # if res['code'] != 0:
        #     return
        for group in res['data']:
            if group['name'] == 'Bot关注':
                info['cookies']['subscribe_group_id'] = group['tagid']
        if info['cookies']['subscribe_group_id'] == '':
            subscribe_group_info = await create_subscribe_group('Bot关注', credential)
            info['cookies']['subscribe_group_id'] = subscribe_group_info['tagid']
            msg = '已成功创建 “Bot关注” 分组，'
        logger.info('相关分组已确认')
    except Exception as e:
        #创建失败，发出提醒后返回
        msg = '用户关注分组创建失败，订阅up请手动关注喵'
        logger.error(f'用户关注分组创建失败: {e}')
        if bot and event:
            await bot.send(event, msg)
        await data_save(info)
        return

    #新版要求在此处就要对所有bot的订阅up进行关注并分组
    #获取所有订阅的up主
    up_lists = [int(item) for item in info['dynamic_info'] if item.isdigit() and info['dynamic_info'][item]['enable'] and str(item) != str(info['cookies']['dedeuserid'])]
    if not up_lists:
        if bot and event:
            msg += '您此后所有订阅up都将分入此组'
            await bot.send(event, msg)
        await data_save(info)
        return
    # 这里将所有订阅up保证关注上
    try:
        for up in up_lists:
            up_info = user.User(up, credential)
            info_get_relation = await up_info.get_relation()
            if info_get_relation['relation']['attribute'] not in [2,6]:
                await up_info.modify_relation(user.RelationType(1))
            del up_info
        # 将所有订阅up主都添加到相应分组中
        await set_subscribe_group(up_lists, [info['cookies']['subscribe_group_id']], credential)
    except Exception as e:
        #关注分组失败，发出提醒后返回
        msg += '\n相关up关注失败喵，bot订阅up请手动关注喵'
        logger.error(f'用户up主批量关注失败: {e}')
        if bot and event:
            await bot.send(event, msg)
        await data_save(info)
        return
    #操作完成，发送信息
    if bot and event:
        msg += '所有订阅up都已完成关注并分组喵'
        await bot.send(event, msg)
    await data_save(info)
    return


#简易查询当前账号的状态
async def bili_up_status_check():
    global loop_cache
    data_info = await data_init()
    day_info = await date_get()
    #计算账号登录时间
    time_tamp = day_info['time'] - data_info['cookies']['login_time']
    days = time_tamp // 86400
    time_tamp %= 86400
    hours = time_tamp // 3600
    time_tamp %= 3600
    minutes = time_tamp // 60
    time_tamp %= 60
    user_info = data_info['dynamic_info'][f'up_info']
    user_info['time_msg'] = f"{days}天 {hours}时 {minutes}分 {time_tamp}秒"
    #计算上次检测的时间
    if user_info['check_time'] != '':
        user_info['check_time'] = datetime.datetime.fromtimestamp(int(user_info['check_time']))
    else:
        user_info['check_time'] = '未知'
    if loop_cache['check_time'] != '':
        user_info['monitor_time'] = datetime.datetime.fromtimestamp(int(loop_cache['check_time']))
    else:
        user_info['monitor_time'] = '未知'

    #检测其默认账号
    if data_info['cookies']['dedeuserid'] == '':
        user_info['status'] = False
        user_info['up_name'] = ''
        return user_info
    user_info['status'] = True
    up_info = user.User(int(data_info['cookies']['dedeuserid']))
    info = await up_info.get_user_info()
    user_info['up_name'] = info['name']
    credential = Credential(sessdata=data_info['cookies']['sessdata'], bili_jct=data_info['cookies']['bili_jct'],
                            buvid3=data_info['cookies']['buvid3'], dedeuserid=data_info['cookies']['dedeuserid'])
    # 检测credential需不需要刷新，此处缺少相关值无法自动刷新，只能重新登录
    if await credential.check_refresh():
        user_info['status'] = False
    return user_info

if __name__ == '__main__':
    sync(bili_login())