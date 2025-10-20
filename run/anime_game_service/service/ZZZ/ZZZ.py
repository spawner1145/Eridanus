from requests import RequestException
from framework_common.database_util.ManShuoDrawCompatibleDataBase import AsyncSQLiteDatabase
import json
import asyncio
from io import BytesIO
from datetime import datetime, timedelta
from PIL import Image as PImage
import base64
import qrcode
import pprint
from developTools.message.message_components import Text, Image, At
from framework_common.manshuo_draw import *
from run.anime_game_service.service.ZZZ.core import *

from framework_common.framework_util.yamlLoader import YAMLManager
try:config = YAMLManager.get_instance()
except Exception as e:config = YAMLManager("run")
db=asyncio.run(AsyncSQLiteDatabase.get_instance())
from pathlib import Path
module_path: Path = Path(__file__).parent / 'core'


async def qrcode_get(userid,bot=None,event=None):
    qr_info = await get_qr(event.user_id)
    ticket,uuid_d,qr_url = qr_info['ticket'], qr_info['uuid_d'], qr_info['qr_url']
    #print(qr_url)
    if bot and event:
        msg = [At(qq=userid),
               " 请使用米游社扫描二维码绑定账号\n二维码有效时间两分钟，请不要扫描他人的登录二维码进行绑定~",
               Image(file=await manshuo_draw([{'type':'img','img':[qr_url]}]))]
        recall_id=await bot.send(event, msg)
    else:
        recall_id=None
        PImage.open(await manshuo_draw([{'type':'img','img':[qr_url]}])).show()

    #data = await ZZZ_uid.send(MessageSegment.image(Path(f"{module_path}/qrcode/{event.user_id}.png"))+MessageSegment.at(event.user_id)+MessageSegment.text("请使用米游社扫码登录"))
    while True:
        record,status,cookies = await check_qr(ticket,uuid_d)
        await asyncio.sleep(1)
        if status == "Confirmed":
            #await ZZZ_uid.send(MessageSegment.at(event.user_id)+MessageSegment.text("扫码成功，正在获取游戏数据"))
            print("扫码成功，正在获取游戏数据")
            if recall_id: await bot.recall(recall_id['data']['message_id'])
            cookies = json.loads(cookies)
            pprint.pprint(cookies)
            await save_cookie(cookies,event.user_id)
            user_info = await getuid(cookies)
            if bot and event:await bot.send(event, f"欢迎，绳匠@{user_info['nickname']} ({user_info['uid']})")
            else:print(f"欢迎，绳匠@{user_info['nickname']} ({user_info['uid']})")
            #await db.write_user(userid, {'skland': {'user_info': user_dict}})
            #print(uid)

            #avatar_id_list = await get_avatar_id_list(uid,cookies)
            #pprint.pprint(avatar_id_list)
            #await save_avatar(avatar_id_list,event.user_id)
            #await get_avatar_info_list(cookies,avatar_id_list,uid,event.user_id)

            #await get_avatar_list_png(event.user_id)
            #await ZZZ_uid.send(MessageSegment.image(Path(f"{module_path}/out/{event.user_id}.png"))+MessageSegment.at(event.user_id)+MessageSegment.at(event.user_id))
            break
        elif record == -3501:
            if bot and event:await bot.send(event, "扫码超时，请重新发送【ZZZ绑定】以获取二维码")
            else:print("扫码超时，请重新发送【ZZZ绑定】以获取二维码")
            #await ZZZ_uid.send(MessageSegment.at(event.user_id)+MessageSegment.text("扫码超时，请重新发送【ZZZ绑定】以获取二维码"))
            break
        elif record == -3505:
            if bot and event: await bot.send(event, "您已取消扫码，请重新发送【ZZZ绑定】以获取二维码")
            else:print("您已取消扫码，请重新发送【ZZZ绑定】以获取二维码")
            #await ZZZ_uid.send(MessageSegment.at(event.user_id)+MessageSegment.text("您已取消扫码，请重新发送【ZZZ绑定】以获取二维码"))
            break
    #await bot.delete_msg(message_id=data["message_id"])

if __name__ == '__main__':
    asyncio.run(qrcode_get(1270858640))