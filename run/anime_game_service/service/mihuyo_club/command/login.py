import asyncio
import json
from typing import Union
from framework_common.manshuo_draw import *
import traceback
from ..api.common import get_ltoken_by_stoken, get_cookie_token_by_stoken, get_device_fp, fetch_game_token_qrcode, \
    query_game_token_qrcode, \
    get_token_by_game_token, get_cookie_token_by_game_token
from ..model import PluginDataManager, plugin_config, UserAccount, UserData, CommandUsage, BBSCookies, \
    QueryGameTokenQrCodeStatus, GetCookieStatus
from ..utils import read_blacklist, read_whitelist, generate_device_id, generate_qr_img
from developTools.utils.logger import get_logger
logger=get_logger()
import base64
from developTools.message.message_components import Text, Image, At
from io import BytesIO
from datetime import datetime, timedelta
from PIL import Image as PImage

async def mys_login(user_id,bot=None,event=None):
    recall_id = None
    user_num = len(set(PluginDataManager.plugin_data.users.values()))  # 由于加入了用户数据绑定功能，可能存在重复的用户数据对象，需要去重
    if user_num <= plugin_config.preference.max_user or plugin_config.preference.max_user in [-1, 0]:
        # 获取用户数据对象
        PluginDataManager.plugin_data.users.setdefault(user_id, UserData())
        user = PluginDataManager.plugin_data.users[user_id]
        if bot:recall_id = await bot.send(event, '正在获取登录二维码，请稍后喵')
        # 1. 获取 GameToken 登录二维码
        device_id = generate_device_id()
        #print(device_id, plugin_config.preference.game_token_app_id)
        login_status, fetch_qrcode_ret = await fetch_game_token_qrcode(
            device_id,
            plugin_config.preference.game_token_app_id
        )
        #print(login_status, fetch_qrcode_ret)
        if fetch_qrcode_ret:
            qrcode_url, qrcode_ticket = fetch_qrcode_ret
            image_bytes = generate_qr_img(qrcode_url)
            base64_data = base64.b64encode(image_bytes).decode("utf-8")
            img_path = await manshuo_draw([{'type': 'img', 'img': [base64_data]}])
            if recall_id: await bot.recall(recall_id['data']['message_id'])
            if bot and event:
                msg = [At(qq=user_id),
                       " 请用米游社App扫描下面的二维码进行登录\n二维码有效时间两分钟，请不要扫描他人的登录二维码进行绑定~",
                       Image(file=img_path)]
                recall_id = await bot.send(event, msg)
            else:
                recall_id = None
                print(img_path)

            # 2. 从二维码登录获取 GameToken
            qrcode_query_times = round(
                plugin_config.preference.qrcode_wait_time / plugin_config.preference.qrcode_query_interval
            )
            bbs_uid, game_token = None, None
            for _ in range(qrcode_query_times):
                login_status, query_qrcode_ret = await query_game_token_qrcode(
                    qrcode_ticket,
                    device_id,
                    plugin_config.preference.game_token_app_id
                )
                if query_qrcode_ret:
                    bbs_uid, game_token = query_qrcode_ret
                    logger.info(f"用户 {bbs_uid} 成功获取 game_token: {game_token}")
                    break
                elif login_status.qrcode_expired:
                    if bot: await bot.send(event, "⚠️二维码已过期，登录失败")
                    break
                elif not login_status:
                    await asyncio.sleep(plugin_config.preference.qrcode_query_interval)
                    continue

            if recall_id: await bot.recall(recall_id['data']['message_id'])

            if bbs_uid and game_token:
                cookies = BBSCookies()
                cookies.bbs_uid = bbs_uid
                account = PluginDataManager.plugin_data.users[user_id].accounts.get(bbs_uid)
                """当前的账户数据对象"""
                if not account or not account.cookies:
                    user.accounts.update({
                        bbs_uid: UserAccount(
                            phone_number=None,
                            cookies=cookies,
                            device_id_ios=device_id,
                            device_id_android=generate_device_id())
                    })
                    account = user.accounts[bbs_uid]
                else:
                    account.cookies.update(cookies)
                fp_status, account.device_fp = await get_device_fp(device_id)
                if fp_status:
                    logger.info(f"用户 {bbs_uid} 成功获取 device_fp: {account.device_fp}")
                PluginDataManager.write_plugin_data()

                if login_status:
                    # 3. 通过 GameToken 获取 stoken_v2
                    login_status, cookies = await get_token_by_game_token(bbs_uid, game_token)
                    if login_status:
                        logger.info(f"用户 {bbs_uid} 成功获取 stoken_v2: {cookies.stoken_v2}")
                        account.cookies.update(cookies)
                        PluginDataManager.write_plugin_data()

                        if account.cookies.stoken_v2:
                            # 5. 通过 stoken_v2 获取 ltoken
                            login_status, cookies = await get_ltoken_by_stoken(account.cookies, device_id)
                            if login_status:
                                logger.info(f"用户 {bbs_uid} 成功获取 ltoken: {cookies.ltoken}")
                                account.cookies.update(cookies)
                                PluginDataManager.write_plugin_data()

                            # 6.1. 通过 stoken_v2 获取 cookie_token
                            login_status, cookies = await get_cookie_token_by_stoken(account.cookies, device_id)
                            if login_status:
                                logger.info(f"用户 {bbs_uid} 成功获取 cookie_token: {cookies.cookie_token}")
                                account.cookies.update(cookies)
                                PluginDataManager.write_plugin_data()
                                logger.info(
                                    f"{plugin_config.preference.log_head}米游社账户 {bbs_uid} 绑定成功")
                                if bot: await bot.send(event, [At(qq=user_id),f" 欢迎，米游社用户： （{bbs_uid}） "])
                        else:
                            # 6.2. 通过 GameToken 获取 cookie_token
                            login_status, cookies = await get_cookie_token_by_game_token(bbs_uid, game_token)
                            if login_status:
                                logger.info(f"用户 {bbs_uid} 成功获取 cookie_token: {cookies.cookie_token}")
                                account.cookies.update(cookies)
                                PluginDataManager.write_plugin_data()
            else:
                logger.error("获取二维码扫描状态超时，请尝试重新登录")
                #if bot: await bot.send(event, "获取二维码扫描状态超时，请尝试重新登录")

        if not login_status:
            notice_text = "登录失败喵："
            if isinstance(login_status, QueryGameTokenQrCodeStatus):
                if login_status.qrcode_expired:
                    notice_text += "登录二维码已过期！"
            if isinstance(login_status, GetCookieStatus):
                if login_status.missing_bbs_uid:
                    notice_text += "Cookies缺少 bbs_uid（例如 ltuid, stuid）"
                elif login_status.missing_login_ticket:
                    notice_text += "Cookies缺少 login_ticket！"
                elif login_status.missing_cookie_token:
                    notice_text += "Cookies缺少 cookie_token！"
                elif login_status.missing_stoken:
                    notice_text += "Cookies缺少 stoken！"
                elif login_status.missing_stoken_v1:
                    notice_text += "Cookies缺少 stoken_v1"
                elif login_status.missing_stoken_v2:
                    notice_text += "Cookies缺少 stoken_v2"
                elif login_status.missing_mid:
                    notice_text += "Cookies缺少 mid"
            if login_status.login_expired:
                notice_text += "登录失效！"
            elif login_status.incorrect_return:
                notice_text += "服务器返回错误！"
            elif login_status.network_error:
                notice_text += "网络连接失败！"
            else:
                notice_text += "未知错误！"
            #notice_text += " 如果部分步骤成功，你仍然可以尝试获取收货地址、兑换等功能"
            if bot: await bot.send(event, notice_text)
            else:print(notice_text)
    else:
        if bot: await bot.send(event, '⚠️目前可支持使用用户数已经满啦~')

