import asyncio
import base64
import json
import re
import uuid
from asyncio import sleep
from pathlib import Path
from typing import Optional, Dict, Any

import httpx
from qzone_api import QzoneApi
from qzone_api.login import QzoneLogin

from developTools.event.events import LifecycleMetaEvent, GroupMessageEvent, PrivateMessageEvent
from developTools.message.message_components import Text, Image, Mface
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.utils.utils import download_img, get_img
from run.qq_zone.service.QzoneApiFixed import QzoneApiFixed


def main(bot: ExtendBot,config: YAMLManager):
    qzone_login = QzoneLogin()
    login_result = None
    login_task = None
    qzone = QzoneApiFixed()
    qzone_status = False

    """
    本地的cookie缓存
    """
    cookie_file = Path("qzone_cookie.json")  # ✅ 新增
    def load_cookie_cache():
        if cookie_file.exists():
            try:
                with open(cookie_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                bot.logger.info("已加载本地 cookie.json")
                return data
            except Exception as e:
                bot.logger.warning(f"读取 cookie.json 失败: {e}")
        return None

    def save_cookie_cache(data):
        try:
            with open(cookie_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            bot.logger.info("已保存 cookie.json")
        except Exception as e:
            bot.logger.error(f"保存 cookie.json 失败: {e}")
    if load_cookie_cache():
        login_result = load_cookie_cache()
        bot.logger.info("使用本地 cookie 登录 Qzone")
    @bot.on(LifecycleMetaEvent)
    async def handle_lifecycle_event(event: LifecycleMetaEvent):
        nonlocal login_result
        if not login_result:
            cached = load_cookie_cache()
            if cached:
                login_result = cached
                bot.logger.info("使用本地 cookie 登录 Qzone")
                return
            login_result = await qzone_login.login()
    @bot.on(GroupMessageEvent)
    async def handle_group_message_event(event: GroupMessageEvent):
        nonlocal qzone_status
        if event.pure_text=="/qzone login" and event.user_id==config.common_config.basic_config["master"]['id']:
            await login_task_wrapper(event)
        elif event.pure_text=="/发空间" and event.user_id==config.common_config.basic_config["master"]['id']:
            await bot.send(event,"下条消息将被发送到空间")
            await sleep(1)
            qzone_status=True
        elif qzone_status and event.user_id==config.common_config.basic_config["master"]['id']:
            qzone_status=False
            await set_cache(event)

        '''if event.pure_text=="test":
            nonlocal login_result
            cookies = login_result["cookies"]
            login_result["qq"]=login_result["qq"].replace("o","")

            r=await qzone._send_zone_with_pic(
                target_qq=int(login_result["qq"]),
                content="test",
                pic_path="D:\python\Eridanus\FIfk1xV.png",
                cookies=cookies,
                g_tk=login_result["bkn"]
            )
            print(r)'''

    @bot.on(PrivateMessageEvent)
    async def handle_private_message_event(event: PrivateMessageEvent):
        nonlocal qzone_status
        if event.pure_text=="/qzone login" and event.user_id==config.common_config.basic_config["master"]['id']:
            await login_task_wrapper(event)
        elif event.pure_text=="/发空间" and event.user_id==config.common_config.basic_config["master"]['id']:
            await bot.send(event, "下条消息将被发送到空间")
            await sleep(1)
            qzone_status=True
        elif qzone_status and event.user_id==config.common_config.basic_config["master"]['id']:
            qzone_status=False
            await set_cache(event)

    async def set_cache(event):
        text_cache = ""
        img_cache = []
        for msg in event.message_chain:
            if isinstance(msg, Text):
                text_cache += msg.text
            elif isinstance(msg, Image) or isinstance(msg, Mface):
                url=await get_img(event,bot)

                path = f"data/pictures/cache/{uuid.uuid4()}.png"
                await download_img(url, path)
                img_cache.append(path)
        await send_to_qzone(event, text_cache, img_cache)
        #return text_cache, img_cache
    async def send_to_qzone(event, text_cache, img_cache):
        nonlocal login_result
        """
        目前没写多图支持
        """
        try:
            if img_cache:
                bot.logger.info("发送到空间的消息包含图片")
                img_path = img_cache[0]
                cookies = login_result["cookies"]
                login_result["qq"] = login_result["qq"].replace("o", "")

                r = await qzone._send_zone_with_pic(
                    target_qq=int(login_result["qq"]),
                    content=text_cache,
                    pic_path=img_path,
                    cookies=cookies,
                    g_tk=login_result["bkn"]
                )
            else:
                bot.logger.info("发送到空间的消息不包含图片")
                cookies = login_result["cookies"]
                login_result["qq"] = login_result["qq"].replace("o", "")

                r = await qzone._send_zone(
                    target_qq=int(login_result["qq"]),
                    content=text_cache,
                    cookies='; '.join([f"{k}={v}" for k, v in cookies.items()]),
                    g_tk=login_result["bkn"]
                )
        except Exception as e:
            bot.logger.error(f"发送到空间失败: {str(e)}")
            await bot.send(event, [Text(f"发送到空间失败: {str(e)} token过期,请重新登录")])
            await login_task_wrapper(event)

    async def login_task_wrapper(event):
        nonlocal login_result, login_task
        await bot.send(event, [Text("请使用机器人账号扫描二维码(二维码已发送至私聊)...")])

        qr_path = Path("./QR.png")
        if qr_path.exists():
            qr_path.unlink()

        login_task = asyncio.create_task(qzone_login.login())
        max_wait = 10
        for i in range(max_wait * 10):
            await asyncio.sleep(0.1)
            if qr_path.exists():
                await bot.send_friend_message(config.common_config.basic_config["master"]['id'], [Image(file="./QR.png")])
                break
        else:
            await bot.send(event, [Text("二维码生成超时,请重试")])
            return

        await bot.send(event, [Text("等待扫码中...")])
        try:
            login_result = await login_task
            await bot.send(event, [Text("登录成功!")])
            print(login_result)
            save_cookie_cache(login_result)
            if qr_path.exists():
                qr_path.unlink()
        except Exception as e:
            await bot.send(event, [Text(f"登录失败: {str(e)}")])

