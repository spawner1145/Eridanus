from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import Text, Image, At
from run.group_fun.service.today_pig import *


def main(bot, config):
    @bot.on(GroupMessageEvent)
    async def random_pig_order(event: GroupMessageEvent):
        context, userid, nickname, group_id = event.pure_text, str(event.sender.user_id), event.sender.nickname, int(event.group_id)
        if context.strip() not in  ['随机小猪','随机猪猪','随机猪','随机红猪']: return
        pig_info = await pig_random()
        if pig_info['status'] is True:
            await bot.send(event, Image(file=pig_info['img_path']))
        else:
            await bot.send(event, pig_info['msg'])

    @bot.on(GroupMessageEvent)
    async def random_pig_order(event: GroupMessageEvent):
        context, userid=event.pure_text, str(event.sender.user_id)
        order_list = ['今日小猪', '今天是什么小猪', '今天是什么猪', '今天我是什么小猪', '今天我是什么猪']
        if event.message_chain.has(At) and event.message_chain.has(Text):
            userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        if context.strip() not in order_list: return
        pig_info = await pig_hub_random_img(userid)
        if pig_info['status'] is True:
            if event.message_chain.has(At):
                await bot.send(event, ['今天的 ', At(qq=userid), ' 是这样的小猪喵', Image(file=pig_info['img_path'])])
            else:
                await bot.send(event, [f'今天你是这个小猪喵',Image(file=pig_info['img_path'])])
        else:
            await bot.send(event, pig_info['msg'])