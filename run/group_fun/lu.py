import asyncio
import datetime
import os
import random
import re
from framework_common.utils.utils import delay_recall
from developTools.event.events import GroupMessageEvent, LifecycleMetaEvent
from developTools.message.message_components import Node, Text, Image, At
from asyncio import sleep
from run.group_fun.service.lu import *

def main(bot, config):
    @bot.on(GroupMessageEvent)
    async def today_LU(event: GroupMessageEvent):
        context, userid=event.pure_text, str(event.sender.user_id)
        if event.message_chain.has(At) and event.message_chain.has(Text):
            userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        if not context.startswith('🦌'):return
        times_add = 0
        for context_check in context:
            if context_check == '🦌':times_add += 1
        if context.replace('🦌','').replace(' ','') != '':return

        lu_recall = ['不！给！你！🦌！！！', '我靠你怎么这么坏！', '再🦌都🦌出火星子了！！', '让我来帮你吧~', '好恶心啊~~',
                     '有变态！！', '你这种人渣我才不会喜欢你呢！', '令人害怕的坏叔叔', '才不给你计数呢！（哼', '杂鱼杂鱼',
                     '杂鱼哥哥还是处男呢', '哥哥怎么还在这呀，好可怜']
        flag = random.randint(0, 100)
        if flag <= 8:
            await bot.send(event, lu_recall[random.randint(0, len(lu_recall) - 1)])
            return
        bot.logger.info("接收到开🦌请求")
        recall_id = await today_lu(userid,times_add,bot=bot,event=event)
        if config.group_fun.config["today_wife"]["签🦌撤回"] is True:
            await sleep(55)
            await bot.recall(recall_id['data']['message_id'])

    @bot.on(GroupMessageEvent)
    async def today_LU2(event: GroupMessageEvent):
        context, userid=event.pure_text, str(event.sender.user_id)
        if event.message_chain.has(At) and event.message_chain.has(Text):
            userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        order_list = ['鹿','这倒提醒我了','🦌！','鹿！']
        if context in order_list:
            bot.logger.info("接收到🦌请求")
            recall_id = await today_lu(userid, 1, bot=bot, event=event)
            if config.group_fun.config["today_wife"]["签🦌撤回"] is True:
                await sleep(55)
                await bot.recall(recall_id['data']['message_id'])

    @bot.on(GroupMessageEvent)
    async def check_LU(event: GroupMessageEvent):
        context, userid=event.pure_text, str(event.sender.user_id)
        if event.message_chain.has(At) and event.message_chain.has(Text):
            userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        order_list = ['查🦌']
        if context in order_list:
            bot.logger.info("接收到查🦌请求")
            recall_id = await check_lu(userid,bot=bot,event=event)
            if config.group_fun.config["today_wife"]["签🦌撤回"] is True:
                await sleep(55)
                await bot.recall(recall_id['data']['message_id'])

    @bot.on(GroupMessageEvent)
    async def supple_LU(event: GroupMessageEvent):
        context, userid=event.pure_text, str(event.sender.user_id)
        #if event.message_chain.has(At):userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        order_list = ['补🦌']
        if context in order_list:
            bot.logger.info("接收到补🦌请求")
            recall_id = await supple_lu(userid,bot=bot,event=event)
            if config.group_fun.config["today_wife"]["签🦌撤回"] is True:
                await sleep(55)
                await bot.recall(recall_id['data']['message_id'])

    @bot.on(GroupMessageEvent)
    async def rank_LU(event: GroupMessageEvent):
        context, userid, type_check=event.pure_text, str(event.sender.user_id), 'month'
        #if event.message_chain.has(At):userid, context = event.message_chain.get(At)[0].qq, event.message_chain.get(Text)[0].text
        order_list = ['🦌排行','🦌排名']
        if not any(word in context for word in order_list):return
        bot.logger.info("接收到🦌排行请求")
        if any(word in context for word in ['每月','本月','当月']): type_check = 'month'
        elif any(word in context for word in ['年度', '今年']): type_check = 'year'
        elif any(word in context for word in ['所有', '总共', '全部']): type_check = 'total'
        recall_id = await bot.send(event, [f"开始查询中，请稍等喵～"])
        friendlist_get = await bot.get_group_member_list(event.group_id)
        userid_list = [friend['user_id'] for friend in friendlist_get["data"]]
        await rank_lu(userid_list,type_check,bot=bot,event=event)
        await bot.recall(recall_id['data']['message_id'])