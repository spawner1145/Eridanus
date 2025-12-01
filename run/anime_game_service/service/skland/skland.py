from requests import RequestException

from framework_common.database_util.ManShuoDrawCompatibleDataBase import AsyncSQLiteDatabase
from run.anime_game_service.service.skland.core import *
import json
import asyncio
from io import BytesIO
from datetime import datetime, timedelta
from PIL import Image as PImage
import base64
from framework_common.utils.install_and_import import install_and_import
dateutil=install_and_import('qrcode', 'qrcode')
import qrcode
import pprint
from developTools.message.message_components import Text, Image, At
from framework_common.manshuo_draw import *
from run.anime_game_service.service.skland.core.exception import LoginException, RequestException, UnauthorizedException

db=asyncio.run(AsyncSQLiteDatabase.get_instance())

async def user_check(userid):
    user_info =await db.read_user(userid)
    pprint.pprint(user_info)
    if user_info and 'skland' in user_info and 'user_info' in user_info['skland'] and 'character_info' in user_info['skland']:
        return True

    return False


async def qrcode_get(userid,bot=None,event=None):
    """二维码绑定森空岛账号"""
    scan_id = await SklandLoginAPI.get_scan()
    scan_url = f"hypergryph://scan_login?scanId={scan_id}"
    qr_code = qrcode.make(scan_url)
    result_stream = BytesIO()
    qr_code.save(result_stream, "PNG")
    if bot and event:
        base64_data = base64.b64encode(result_stream.getvalue()).decode("utf-8")
        msg = [At(qq=userid),
               " 请使用森空岛app扫描二维码绑定账号\n二维码有效时间两分钟，请不要扫描他人的登录二维码进行绑定~",
               Image(file=await manshuo_draw([{'type':'img','img':[base64_data]}]))]
        recall_id=await bot.send(event, msg)
    else:
        recall_id=None
        PImage.open(result_stream).show()

    end_time = datetime.now() + timedelta(seconds=100)
    scan_code = None
    while datetime.now() < end_time:
        try:
            scan_code = await SklandLoginAPI.get_scan_status(scan_id)
            break
        except :
            pass
        await asyncio.sleep(2)
    if scan_code:
        if recall_id:await bot.recall(recall_id['data']['message_id'])
        token = await SklandLoginAPI.get_token_by_scan_code(scan_code)
        grant_code = await SklandLoginAPI.get_grant_code(token)
        cred = await SklandLoginAPI.get_cred(grant_code)
        user_dict={
            'access_token' : token,
            'cred' : cred.cred,
            'cred_token' :cred.token,
            'id' : userid,
            'user_id' : cred.userId,
        }
        #pprint.pprint(user_dict)
        await db.write_user(userid, {'skland':{'user_info':user_dict}})
        character_dict=await get_characters_and_bind(user_dict, userid, db)
        if bot and event:await bot.send(event, f'绑定成功，欢迎 {character_dict["nickname"]}')
        else:
            pprint.pprint(user_dict)
            pprint.pprint(character_dict)
            print(f'绑定成功，欢迎 {character_dict["nickname"]}')
    else:
        if bot and event:await bot.send(event, '请重新获取并扫码')
        else:print('二维码超时,请重新获取并扫码')


async def self_info(userid,bot=None,event=None):
    user_info =await db.read_user(userid)
    if not (user_info and 'skland' in user_info and 'user_info' in user_info['skland'] and 'character_info' in user_info['skland']):
        await bot.send(event, '此用户还未绑定，请发送 ‘森空岛帮助’ 查看菜单')
        return
    user_info_self=user_info['skland']['user_info']
    character_info_self=user_info['skland']['character_info']
    if bot and event:
        await bot.send(event, '此处应为个人信息')
    else:
        for item in user_info_self:
            print(item, user_info_self[item])
        for item in character_info_self:
            print(item, character_info_self[item])

async def skland_signin(userid,bot=None,event=None):
    """明日方舟森空岛签到"""

    @refresh_cred_token_if_needed
    @refresh_access_token_if_needed
    async def sign_in(user_info, uid: str, channel_master_id: str):
        """执行签到逻辑"""
        cred = CRED(cred=user_info['cred'], token=user_info['cred_token'])
        ark_info = {'error':None}
        try:
            ark_sign_info = await SklandAPI.ark_sign(cred, uid, channel_master_id=channel_master_id)
            ark_info['ark_sign_info'] = ark_sign_info
            return ark_info
        except (RequestException) as e:
            ark_info['error'] = e
            return ark_info

    user_info =await db.read_user(userid)
    if not (user_info and 'skland' in user_info and 'user_info' in user_info['skland'] and 'character_info' in user_info['skland']):
        msg = '此用户还未绑定，请发送 ‘森空岛帮助’ 查看菜单'
        if bot and event:await bot.send(event, msg)
        else:print(msg)
        return msg
    user_info_self, character_info_self = user_info['skland']['user_info'], user_info['skland']['character_info']
    sign_result: dict[str, ArkSignResponse] = {}
    sing_info = await sign_in(user_info_self, str(character_info_self['uid']), character_info_self['channel_master_id'])
    #print(sing_info)
    if sing_info is  None:
        msg = f"Dr.{character_info_self['nickname']} ，登录已过期，请重新登录"
        if bot and event: await bot.send(event, msg)
        else: print(msg)
        return msg
    if sing_info['error'] is not None:
        msg = f"Dr.{character_info_self['nickname']} ，{sing_info['error']}"
        if bot and event: await bot.send(event, msg)
        else: print(msg)
        return msg
    sign_result[character_info_self['nickname']] = sing_info['ark_sign_info']
    msg=''
    if sign_result:
        #pprint.pprint(sign_result)
        for nickname, sign in sign_result.items():
            if sign:msg+=f"角色: {nickname} 签到成功，获得了:\n"+ "\n".join(f"{award.resource.name} x {award.count}" for award in sign.awards)
            else: msg+=f'Dr.{nickname} ，您的token可能已失效，请重新登录'
    if bot and event: await bot.send(event, msg)
    else: print(msg)
    return msg



async def skland_info(userid,bot=None,event=None):
    @refresh_cred_token_if_needed
    @refresh_access_token_if_needed
    async def get_character_info(user_info, uid: str):
        return await SklandAPI.ark_card(CRED(cred=user_info['cred'], token=user_info['cred_token']), uid)

    user_info =await db.read_user(userid)
    if not (user_info and 'skland' in user_info and 'user_info' in user_info['skland'] and 'character_info' in user_info['skland']):
        if bot and event:await bot.send(event, '此用户还未绑定，请发送 ‘森空岛帮助’ 查看菜单')
        else:print('此用户还未绑定，请发送 ‘森空岛帮助’ 查看菜单')
        return
    user_info_self, character_info_self = user_info['skland']['user_info'], user_info['skland']['character_info']
    info = await get_character_info(user_info_self, str(character_info_self['uid']))
    #print(info)

    background = await get_background_image()
    image_path = await render_ark_card(info, background)
    if bot and event:
        await bot.send(event, [At(qq=userid)," 的森空岛信息如下：",Image(file=image_path)])
    else:
        PImage.open(image_path).show()


async def rouge_info(userid,rg_type,bot=None,event=None):
    """获取明日方舟肉鸽战绩"""

    @refresh_cred_token_if_needed
    @refresh_access_token_if_needed
    async def get_rogue_info(user_info, uid: str, topic_id: str):
        return await SklandAPI.get_rogue(
            CRED(cred=user_info['cred'], token=user_info['cred_token'], userId=str(user_info['user_id'])),
            uid,topic_id,)
    user_info =await db.read_user(userid)
    if not (user_info and 'skland' in user_info and 'user_info' in user_info['skland'] and 'character_info' in user_info['skland']):
        if bot and event:await bot.send(event, '此用户还未绑定，请发送 ‘森空岛帮助’ 查看菜单')
        else:print('此用户还未绑定，请发送 ‘森空岛帮助’ 查看菜单')
        return
    user_info_self, character_info_self = user_info['skland']['user_info'], user_info['skland']['character_info']
    topic_id = Topics(rg_type).topic_id
    rogue_data = await get_rogue_info(user_info_self, str(character_info_self['uid']), topic_id)
    background = await get_rogue_background_image(topic_id)
    image_path = await render_rogue_card(rogue_data, background)

    if bot and event:
        await bot.send(event, [At(qq=userid),f" 的 {rg_type} 肉鸽信息如下：",Image(file=image_path)])
    else:
        PImage.open(image_path).show()

async def rouge_detailed_info(userid,rg_type,game_count=None,favored=False,bot=None,event=None):
    """获取明日方舟肉鸽战绩详情"""
    @refresh_cred_token_if_needed
    @refresh_access_token_if_needed
    async def get_rogue_info(user_info, uid: str, topic_id: str):
        return await SklandAPI.get_rogue(
            CRED(cred=user_info['cred'], token=user_info['cred_token'], userId=str(user_info['user_id'])),
            uid,topic_id,)
    user_info =await db.read_user(userid)
    if not (user_info and 'skland' in user_info and 'user_info' in user_info['skland'] and 'character_info' in user_info['skland']):
        if bot and event:await bot.send(event, '此用户还未绑定，请发送 ‘森空岛帮助’ 查看菜单')
        else:print('此用户还未绑定，请发送 ‘森空岛帮助’ 查看菜单')
        return
    if game_count is None: game_count = 1
    user_info_self, character_info_self = user_info['skland']['user_info'], user_info['skland']['character_info']
    topic_id = Topics(rg_type).topic_id
    rogue_data = await get_rogue_info(user_info_self, str(character_info_self['uid']), topic_id)
    background = await get_rogue_background_image(topic_id)
    image_path = await render_rogue_info(rogue_data, background, game_count, favored)
    if bot and event:
        await bot.send(event, [At(qq=userid),f" 的 {rg_type} 肉鸽信息如下：",Image(file=image_path)])
    else:
        PImage.open(image_path).show()





if __name__ == '__main__':

    #asyncio.run(qrcode_get(1667962668))
    #asyncio.run(user_check(3922292124))
    asyncio.run(skland_signin(1270858640))
    #asyncio.run(skland_info(942755190))
    #asyncio.run(rouge_info(1667962668,'水月'))
    #asyncio.run(rouge_detailed_info(1667962668,'界园'))