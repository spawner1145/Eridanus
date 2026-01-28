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
        #qr_code.print_ascii()
        PImage.open(result_stream).save('run/anime_game_service/service/skland/arksign.png')
        #PImage.open(result_stream).show()

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
        msg = '绑定成功，\n'
        if 'arknights' in character_dict and character_dict['arknights'].get("nickname") is not None:
            msg += f'欢迎 博士：{character_dict["arknights"].get("nickname")}\n'
        if 'endfield' in character_dict and character_dict['endfield'].get("nickname") is not None:
            msg += f'欢迎 管理员：{character_dict["endfield"].get("nickname")}'
        if 'arknights' not in character_dict and 'endfield' not in character_dict:
            msg ='未查询到您账户下的游戏，给你一拳喵'
        if bot and event:await bot.send(event, msg)
        else:
            pprint.pprint(user_dict)
            pprint.pprint(character_dict)
            print(msg)
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
        pprint.pprint(user_info_self)
        pprint.pprint(character_info_self)

async def skland_signin(userid,bot=None,event=None):
    """明日方舟森空岛签到"""

    @refresh_cred_token_if_needed
    @refresh_access_token_if_needed
    async def sign_in(user_info, character_info):
        """执行签到逻辑"""
        cred = CRED(cred=user_info['cred'], token=user_info['cred_token'])
        ark_info = {'error':None, 'ark_sign_info':{}, 'zmd_sign_info':{}}
        if 'arknights' in character_info and character_info['arknights'].get('uid') is not None:
            try:
                ark_sign_info = await SklandAPI.ark_sign(cred, str(character_info['arknights']['uid']),
                                                         channel_master_id=str(character_info['arknights']['channel_master_id']))
                ark_info['ark_sign_info']['info'] = ark_sign_info
            except (RequestException) as e:
                ark_info['error'] = e
                ark_info['ark_sign_info']['error'] = e
        else:
            ark_info['ark_sign_info']['error'] = '未绑定明日方舟账户喵'
        if 'endfield' in character_info and character_info['endfield'].get('uid') is not None:
            try:
                zmd_sign_info = await SklandAPI.endfield_sign(cred, str(character_info['endfield']['roleid']),
                                                         server_id=character_info['endfield']['serverid'])
                ark_info['zmd_sign_info']['info'] = zmd_sign_info
            except (RequestException) as e:
                ark_info['error'] = e
                ark_info['zmd_sign_info']['error'] = e
        else:
            ark_info['zmd_sign_info']['error'] = '未绑定终末地账户喵'
        #pprint.pprint(ark_info)
        return ark_info

    user_info =await db.read_user(userid)
    return_json = {'msg':'','manshuo_draw':[],'status':False}
    if not (user_info and 'skland' in user_info and 'user_info' in user_info['skland'] and 'character_info' in user_info['skland']):
        msg = '此用户还未绑定，请发送 ‘森空岛帮助’ 查看菜单'
        if bot and event:await bot.send(event, msg)
        else:print(msg)
        return_json['msg'] = msg
        return return_json
    user_info_self, character_info_self = user_info['skland']['user_info'], user_info['skland']['character_info']
    #重新绑定判定
    if 'arknights' not in character_info_self or 'endfield' not in character_info_self:
        msg = f"您的登录已过期，请发送 ‘森空岛绑定’ 重新绑定喵"
        if bot and event: await bot.send(event, msg)
        else: print(msg)
        return_json['msg'] = msg
        return return_json
    sign_result: dict[str, ArkSignResponse] = {}
    sing_info = await sign_in(user_info_self, character_info_self)

    #print(sing_info)
    if sing_info is None:
        msg = f"您的登录已过期，请重新登录"
        if bot and event: await bot.send(event, msg)
        else: print(msg)
        return_json['msg'] = msg
        return return_json
    msg = ''
    img_list, msg_list = ['run/manshuo_test/data/img/logo/ark.webp','run/manshuo_test/data/img/logo/zmd.png'], []
    if 'error' in sing_info['ark_sign_info']:
        msg += f"Dr.{character_info_self['arknights'].get('nickname')} ，{sing_info['ark_sign_info']['error']}\n"
        msg_list.append(f"Dr.{character_info_self['arknights'].get('nickname')} ，{sing_info['ark_sign_info']['error']}")
    else:
        sign_result[character_info_self['arknights'].get('nickname')] = sing_info['ark_sign_info']['info']
        for nickname, sign in sign_result.items():
            if sign:
                msg+=f"明日方舟签到奖励 ({nickname})：\n"+ "\n".join(f"{award.resource.name} x {award.count}" for award in sign.awards)
                msg_list.append(f"[title]明日方舟[/title] \nDr.{nickname}：\n"+ "\n".join(f"{award.resource.name} x {award.count}" for award in sign.awards))
            else:
                msg += f'Dr.{nickname} ，您的token可能已失效，请重新登录'
                msg_list.append(f'Dr.{nickname} ，您的token可能已失效，请重新登录')
        msg += '\n'

    if 'error' in sing_info['zmd_sign_info']:
        msg += f"管理员 {character_info_self['endfield'].get('nickname')}，{sing_info['zmd_sign_info']['error']}"
        msg_list.append(f"管理员 {character_info_self['endfield'].get('nickname')}，{sing_info['zmd_sign_info']['error']}")
    else:
        info = sing_info['zmd_sign_info']['info']
        #构建每日签到奖励
        msg += f"终末地签到奖励 (管理员 {character_info_self['endfield'].get('nickname')})：\n"
        per_msg = f"[title]终末地[/title] \n管理员 {character_info_self['endfield'].get('nickname')}：\n"
        for award_info in info['awardIds']:
            msg += f"{info['resourceInfoMap'][award_info['id']]['name']} × {info['resourceInfoMap'][award_info['id']]['count']}\n"
            per_msg += f"{info['resourceInfoMap'][award_info['id']]['name']} × {info['resourceInfoMap'][award_info['id']]['count']}\n"
        msg_list.append(per_msg)
    if bot and event: await bot.send(event, msg)
    else: print(msg)
    return_json['msg'],return_json['status'] = msg, True
    return_json['manshuo_draw'] = [
        {'type': 'avatar', 'subtype': 'common', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={userid}&s=640"],
         'upshift_extra': 15,'background':'run/anime_game_service/service/skland/core/resources/images/background/sklandbg.png',
         'content': [f"[name]森空岛签到[/name]\n[time]森空岛id: {user_info_self['user_id']}[/time]"]},
         {'type': 'img', 'subtype': 'common_with_des_right', 'img': img_list, 'content': msg_list,'number_per_row':1}
         ]
    return return_json




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
    user_info_self, character_info_self = user_info['skland']['user_info'], user_info['skland']['character_info']['arknights']
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
    user_info_self, character_info_self = user_info['skland']['user_info'], user_info['skland']['character_info']['arknights']
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
    user_info_self, character_info_self = user_info['skland']['user_info'], user_info['skland']['character_info']['arknights']
    topic_id = Topics(rg_type).topic_id
    rogue_data = await get_rogue_info(user_info_self, str(character_info_self['uid']), topic_id)
    background = await get_rogue_background_image(topic_id)
    image_path = await render_rogue_info(rogue_data, background, game_count, favored)
    if bot and event:
        await bot.send(event, [At(qq=userid),f" 的 {rg_type} 肉鸽信息如下：",Image(file=image_path)])
    else:
        PImage.open(image_path).show()





if __name__ == '__main__':

    #asyncio.run(skland_signin(1270858640))
    #asyncio.run(qrcode_get(1270858640))
    #asyncio.run(rouge_info(1270858640))
    #asyncio.run(skland_info(942755190))
    #asyncio.run(rouge_info(1667962668,'水月'))
    asyncio.run(rouge_detailed_info(1667962668,'界园'))