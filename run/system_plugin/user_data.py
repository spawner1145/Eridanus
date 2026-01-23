import traceback
from asyncio import sleep

import asyncio
import re
from developTools.event.events import GroupMessageEvent, LifecycleMetaEvent
from developTools.message.message_components import Node, Text, Image, At
from framework_common.database_util.User import add_user, get_user, record_sign_in, update_user
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from run.system_plugin.func_collection import call_user_data_register, call_user_data_query, call_user_data_sign, \
    call_change_city, call_change_name, call_permit


def main(bot: ExtendBot,config: YAMLManager):
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

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(setup_users())
    except RuntimeError:
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
        elif event.pure_text =="我的信息" and config.system_plugin.config["user_data"]["是否启用个人信息查询"]:
            await call_user_data_query(bot,event,config)
        elif event.pure_text == "签到" and config.system_plugin.config["user_data"]["是否启用签到"]:
            await call_user_data_sign(bot,event,config)
        elif event.pure_text.startswith("修改城市"):
            city=event.pure_text.split("修改城市")[1]
            await call_change_city(bot,event,config,city)
        elif event.pure_text.startswith("叫我"):
            user_info=await get_user(event.user_id, event.sender.nickname)
            if user_info.permission>=config.system_plugin.config["user_data"]["change_info_operate_level"]:
                nickname=event.pure_text.split("叫我")[1]
                await call_change_name(bot,event,config,nickname)

    @bot.on(GroupMessageEvent)
    async def handle_group_message1(event):
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
        elif event.raw_message.startswith("授权"):
            match = re.search(r"qq=(\d+)", event.raw_message)
            if match: #f
                target_qq = match.group(1)
                user_info = await get_user(event.user_id, event.sender.nickname)
                if user_info.permission < config.system_plugin.config["user_data"]["permit_user_operate_level"]:
                    await bot.send(event, [At(qq=int(target_qq)), f' 的权限好像不够喵'])
                    return
                if '用户' in event.raw_message:
                    await update_user(user_id=target_qq, permission=1)
                    await bot.send(event, [At(qq=int(target_qq)), f' 被设定为用户'])
                elif '关注者' in event.raw_message:
                    await update_user(user_id=target_qq, permission=2)
                    await bot.send(event, [At(qq=int(target_qq)), f' 被设定为关注者'])
                elif '贡献者' in event.raw_message:
                    await update_user(user_id=target_qq, permission=3)
                    await bot.send(event, [At(qq=int(target_qq)), f' 被设定为贡献者'])
                elif '信任' in event.raw_message:
                    await update_user(user_id=target_qq, permission=4)
                    await bot.send(event, [At(qq=int(target_qq)), f' 被设定为信任者'])
                elif '管理员' in event.raw_message:
                    await update_user(user_id=target_qq, permission=10)
                    await bot.send(event, [At(qq=int(target_qq)), f' 被设定为管理员'])
