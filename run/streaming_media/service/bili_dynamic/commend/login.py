from bilibili_api import login_v2, sync, Credential, user, select_client
from bilibili_api.user import create_subscribe_group, set_subscribe_group,get_self_info
select_client("httpx")
from ..data import *
from ..utils import *
import requests
import time
from developTools.utils.logger import get_logger
logger=get_logger('bili_dynamic')
import asyncio

async def bili_login(bot = None, event = None) -> None:
    recall_id, cookies_check = None, ''
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
    #await data_save(info)
    msg = '登录成功喵'
    logger.info(msg)
    #获取对应up分组并创建一个保存的关注分组
    try:
        credential = Credential(sessdata=cookies['SESSDATA'], bili_jct=cookies['bili_jct'],
                                buvid3=cookies['buvid3'], dedeuserid=cookies['DedeUserID'])
        cookies_info = credential.get_cookies()
        for item in cookies_info:
            cookies_check += f'{item}={cookies_info[item]};'
        resp = requests.get("https://api.bilibili.com/x/relation/tags",
                            headers={'Cookie': cookies_check, 'User-Agent': 'Mozilla/5.0'},
                            params={'csrf': cookies['bili_jct'] })
        res = resp.json()
        if res['code'] != 0:
            return
        for group in res['data']:
            if group['name'] == 'Bot关注':
                info['cookies']['subscribe_group_id'] = group['tagid']
        if info['cookies']['subscribe_group_id'] == '':
            subscribe_group_info = await create_subscribe_group('Bot关注', credential)
            info['cookies']['subscribe_group_id'] = subscribe_group_info['tagid']
            msg += '\n已成功创建 “Bot关注” 分组，此后订阅的所有up都将分入此组'
        logger.info('相关分组已确认')
    except Exception as e:
        msg += '\n用户关注分组创建失败，订阅up请手动关注喵'
        logger.error(f'用户关注分组创建失败: {e}')
    finally:
        if bot and event:
            if recall_id: await bot.recall(recall_id['data']['message_id'])
            await bot.send(event, msg)
        await data_save(info)



if __name__ == '__main__':
    sync(bili_login())