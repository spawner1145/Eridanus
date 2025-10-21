import traceback
from asyncio import sleep

import asyncio
import re
from developTools.event.events import GroupMessageEvent, LifecycleMetaEvent
from developTools.message.message_components import Node, Text, Image, At
from framework_common.database_util.llmDB import delete_user_history, clear_all_history
from framework_common.database_util.User import add_user, get_user, record_sign_in, update_user
from datetime import datetime
from run.group_fun.service.wife_you_want import today_check_api
from io import BytesIO
from PIL import Image as PlImage
from run.basic_plugin.service.divination import tarotChoice
import random
from framework_common.manshuo_draw import *
import json

async def call_user_data_register(bot,event,config):
    data = await bot.get_group_member_info(group_id=event.group_id, user_id=event.user_id)
    r = await add_user(
        data["data"]["user_id"],
        data["data"]["nickname"],
        data["data"]["card"],
        data["data"]["sex"],
        data["data"]["age"],
        data["data"]["area"])
    await bot.send(event, r)
async def call_user_data_query(bot,event,config):
    user_data = await get_user(event.user_id, event.sender.nickname)
    uer_sign_days = len(user_data.signed_days)
    #await bot.send(event, str(r))
    context, userid, nickname = event.pure_text, event.sender.user_id, event.sender.nickname
    formatted_date = datetime.now().strftime("%Y年%m月%d日")

    draw_list = [
        {'type': 'basic_set', 'img_width': 1000,},
        {'type': 'avatar', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={userid}&s=640"], 'upshift_extra': 15,
         'avatar_backdrop_color': (235, 239, 253, 0),
         'content': [f"[name]{nickname} 的个人信息[/name]\n[time]当前时间：{formatted_date}[/time]"]},
        f'用户：{user_data.user_id}， 昵称：{user_data.nickname}， 卡片名称：{user_data.card}',
        f'性别：{user_data.sex}， 年龄：{user_data.age}， 所在城市：{user_data.city}',
        f' {nickname} 签到天数：{uer_sign_days}）， 注册时间：{user_data.registration_date}',
        f'权限等级：{user_data.permission}， ai对话token：{user_data.ai_token_record}',
        f'用户画像更新时间：{user_data.portrait_update_time}， 用户画像：{user_data.user_portrait}',
    ]
    bot.logger.info('开始制作用户信息图片')
    await bot.send(event, Image(file=(await manshuo_draw(draw_list))))

async def call_user_data_sign(bot,event,config):
    context, userid, nickname = event.pure_text, event.sender.user_id, event.sender.nickname
    sign_str = await record_sign_in(event.user_id)
    if '今天已经签到过了' in sign_str and event.sender.user_id!=config.common_config.basic_config["master"]["id"]:
        await bot.send(event, sign_str)
        return
    user_data = await get_user(event.user_id, event.sender.nickname)
    user_data.signed_days = json.loads(user_data.signed_days)
    uer_sign_days = len(user_data.signed_days)
    formatted_date = datetime.now().strftime("%Y年%m月%d日")
    today_wife_api, header = config.group_fun.config["today_wife"]["api"], config.group_fun.config["today_wife"]["header"]
    try:
        response = await today_check_api(today_wife_api, header)
        img = PlImage.open(BytesIO(response.content))
        if config.system_plugin.config["user_data"]["签到附带原图"] and img != "data/system/bot.png":
            img.save(f"data/pictures/cache/wife_{userid}.jpg")
            img = f"data/pictures/cache/wife_{userid}.jpg"
    except Exception as e:
        traceback.print_exc()
        bot.logger.error("获取图片失败，使用预设图片: data/system/bot.png")
        img="data/system/bot.png"
    tarottxt, tarotimg, tarots = tarotChoice(config.basic_plugin.config["tarot"]["mode"])
    r = random.randint(1, 100)
    if r <= 10:
        card_ = "data/pictures/Amamiya/谕吉.jpg"
        card_txt = '[title]谕吉[/title]\n通常表示吉祥的预兆，但带有提醒或警示的意味，\n暗示虽然吉利，但仍需谨慎行事。\n吉中带谕，有幸运但不宜过于冒进。'
    elif 10 < r <= 30:
        card_ = "data/pictures/Amamiya/大吉.jpg"
        card_txt = '[title]大吉[/title]\n事情非常顺利，成功几率高，\n适合开始重要的计划或行动。\n吉中之王，代表极佳的运势和极大好运。'
    elif 30 < r <= 60:
        card_ = "data/pictures/Amamiya/中吉.jpg"
        card_txt = '[title]中吉[/title]\n运势较好，事情有望顺利，\n但可能会遇到一些小困难或需要付出努力。\n介于大吉和小吉之间，吉利但不完美。'
    elif 60 < r <= 90:
        card_ = "data/pictures/Amamiya/小吉.jpg"
        card_txt = '[title]小吉[/title]\n总体有利，但吉祥程度较轻微，\n可能会有一些阻碍或限制。\n吉祥但平缓，适合稳妥行事。'
    else:
        card_ = "data/pictures/Amamiya/大兄.jpg"
        card_txt = '[title]凶[/title]\n事情可能不顺，\n容易遇到困难、损失或不幸。\n提醒谨慎，小心防范，避免冒险。'

    draw_list = [{'type': 'basic_set', 'img_width': 750, 'img_height': 3000, 'is_stroke_layer': True,
         'backdrop_mode': 'one_color', 'backdrop_color': {'color1': (235, 239, 253, 225)}},]
    if config.system_plugin.config["user_data"]["with_img_backdrop"]:
        draw_list.extend([{'type': 'backdrop', 'subtype': 'img', 'background': [img]},])
    draw_list.extend([
        {'type': 'avatar', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={userid}&s=640"], 'upshift_extra': 15,'avatar_backdrop_color': (235, 239, 253, 0),
         'content': [f"[name]{nickname} 今天签到啦～[/name]\n[time]当前时间：{formatted_date}[/time]"], 'shadow_font_color': (255,255,255), 'is_shadow_font': True},
        f'[title]今天 {nickname} 签到了哦[/title]（签到天数：{uer_sign_days}）',])
    if config.system_plugin.config["user_data"]["with_taro"]:
        draw_list.extend([
            {'type': 'img', 'subtype': 'common', 'img': [img], 'jump_next_page': True},
            '[title]您今天的塔罗牌和运势为：[/title]',
            {'type': 'img', 'subtype': 'common_with_des_right', 'img': [tarotimg, card_],
             'content': [tarottxt, card_txt],'is_crop': False, 'number_per_row': 1}])
    else:
        draw_list.extend([{'type': 'img', 'subtype': 'common', 'img': [img]},])
    bot.logger.info('开始制作用户签到图片')
    await bot.send(event, Image(file=(await manshuo_draw(draw_list))))
    if config.system_plugin.config["user_data"]["签到附带原图"] and img!= "data/system/bot.png":
        img = f"data/pictures/cache/wife_{userid}.jpg"
        await bot.send(event, [Text("原图已保存，请查收"), Image(file=img)])



async def call_change_city(bot,event,config,city):
    user_info = await get_user(event.user_id, event.sender.nickname)
    if user_info.permission>=config.system_plugin.config["user_data"]["change_info_operate_level"]:
        r = await update_user(event.user_id, city=city)
        await bot.send(event, r)
    else:
        await bot.send(event,"权限好像不够呢.....")
async def call_change_name(bot,event,config,name):
    user_info = await get_user(event.user_id, event.sender.nickname)
    if user_info.permission>=config.system_plugin.config["user_data"]["change_info_operate_level"]:
        await update_user(event.user_id, nickname=name)
        await bot.send(event, f"已将你的昵称改为{name}")
    else:
        await bot.send(event,"权限好像不够呢.....")
async def call_permit(bot,event,config,target_id,level,type="user"):
    user_info = await get_user(event.user_id, event.sender.nickname)
    if user_info.permission >= config.system_plugin.config["user_data"]["permit_user_operate_level"]:
        if type == "user":
            await update_user(user_id=target_id, permission=level)
            await bot.send(event, f"已将{target_id}的权限设置为{level}")
        elif type == "group":
            groupmemberlist_get = await bot.get_group_member_list(target_id)
            bot.logger.info(f"number of members in group {target_id}: {len(groupmemberlist_get['data'])}")
            for member in groupmemberlist_get["data"]:
                try:
                    if config.common_config.basic_config["master"]["id"] == member["user_id"]:
                        continue
                    #bot.logger.info(f"Setting permission of {member['user_id']} to {level}")
                    await update_user(user_id=member["user_id"], permission=level)
                except Exception as e:
                    bot.logger.error(f"Error in updating user permission: {e}")
            await bot.send(event, f"已将群{target_id}中所有成员的权限设置为{level}")
    else:
        await bot.send(event,"权限不足以进行此操作。")
async def call_delete_user_history(bot,event,config):
    await delete_user_history(event.user_id)
    await bot.send(event, "已清理对话记录")
async def call_clear_all_history(bot,event,config):
    if event.user_id==config.common_config.basic_config["master"]["id"]:
        await clear_all_history()
        await bot.send(event, "已清理所有用户的对话记录")
    else:
        await bot.send(event, "你不是master，没有权限进行此操作。")


def main(bot,config):
    """
    数据库提供指令
    注册 #开了auto_register后，发言的用户会被自动注册
    我的信息 #查看自己的信息
    签到 #签到
    修改城市{city} #修改自己的城市
    叫我{nickname} #修改自己的昵称
    授权#{target_qq}#{level} #授权某人相应权限，为高等级权限专有指令
    """
    master_id = config.common_config.basic_config["master"]["id"]
    bot.master=master_id
    master_name = config.common_config.basic_config["master"]["name"]

    async def setup_users():
        tasks = [
            add_user(master_id, master_name, master_name),
            update_user(master_id, permission=9999, nickname=master_name),
            update_user(111111111, permission=9999, nickname="主人")
        ]
        await asyncio.gather(*tasks)

    # 直接运行异步函数
    asyncio.run(setup_users())

    if master_id not in config.common_config.censor_user["whitelist"]:
        config.common_config.censor_user["whitelist"].append(master_id)
        config.save_yaml("censor_user",plugin_name="common_config")
    @bot.on(LifecycleMetaEvent)
    async def handle_lifecycle_event(event):
        await sleep(10)
        await add_user(master_id, master_name, master_name),
        await update_user(master_id, permission=9999, nickname=master_name),
        await update_user(111111111, permission=9999, nickname="主人")
    @bot.on(GroupMessageEvent)
    async def handle_group_message(event):
        #print(user_info)
        if event.pure_text == "注册":
            await call_user_data_register(bot,event,config)
        elif event.pure_text =="我的信息":
            await call_user_data_query(bot,event,config)
        elif event.pure_text == "签到":
            await call_user_data_sign(bot,event,config)
        elif event.pure_text.startswith("修改城市"):
            city=event.pure_text.split("修改城市")[1]
            await call_change_city(bot,event,config,city)
        elif event.pure_text.startswith("叫我"):
            user_info=await get_user(event.user_id, event.sender.nickname)
            if user_info.permission>=config.system_plugin.config["user_data"]["change_info_operate_level"]:
                nickname=event.pure_text.split("叫我")[1]
                await call_change_name(bot,event,config,nickname)

        if event.pure_text.startswith("授权#") or event.pure_text.startswith("授权群#"):
            try:
                permission=int(event.pure_text.split("#")[2])
                target_qq=int(event.pure_text.split("#")[1])
                if event.pure_text.startswith("授权#"):
                    await call_permit(bot,event,config,target_qq,permission)
                elif event.pure_text.startswith("授权群#"):
                    await call_permit(bot,event,config,target_qq,permission,type="group")
            except:
                await bot.send(event, "请输入正确的命令格式。\n指令为\n授权#{target_qq}#{level}\n如授权#1223434343#1\n授权群#{群号}#{level}\n如授权群#1223434343#1")

        if event.raw_message.startswith("授权"):
            match = re.search(r"qq=(\d+)", event.raw_message)
            if match: #f
                target_qq = match.group(1)
                if '用户' in event.raw_message:
                    await call_permit(bot, event, config, target_qq, 1)
                elif '贡献者' in event.raw_message:
                    await call_permit(bot, event, config, target_qq, 2)
                elif '信任' in event.raw_message:
                    await call_permit(bot, event, config, target_qq, 3)
                elif '管理员' in event.raw_message:
                    await call_permit(bot, event, config, target_qq, 10)
