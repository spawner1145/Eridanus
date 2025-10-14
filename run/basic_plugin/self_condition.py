from developTools.event.events import GroupMessageEvent, LifecycleMetaEvent
from developTools.message.message_components import Text, Image, At
from framework_common.manshuo_draw import *
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
from datetime import datetime
from run.basic_plugin.service.self_condition import self_info_record



self_task = None
self_task_lock = asyncio.Lock()
async def self_condition_loop(bot, config):
    """自身状态检查的主循环"""
    bot.logger.info_func("自身状态监控循环启动")
    while True:
        try:
            await self_info_record()
        except Exception as e:
            bot.logger.error(f"自身状态检查出错：{e}")

        interval = 1800
        await asyncio.sleep(interval)

def main(bot, config):
    """

    排查问题，控制变量，暂时停用
    """
    if not config.basic_plugin.config["self_condition"]["enable"]: return
    #查询bot自身状态
    @bot.on(GroupMessageEvent)
    async def self_info(event: GroupMessageEvent):
        context, userid=event.pure_text, str(event.sender.user_id)
        order_list = ['botinfo', 'selfinfo','bot状态']
        if context in order_list:
            pass

    @bot.on(LifecycleMetaEvent)
    async def start_self_condition_monitor(event):
        """生命周期事件处理"""
        #print('1')
        global self_task, self_task_lock
        async with self_task_lock:
            # 检查是否已有任务在运行
            if self_task is not None and not self_task.done():
                bot.logger.info("自身状态监控已在运行中")
                return
            # 创建新的监控任务
            self_task = asyncio.create_task(self_condition_loop(bot, config))
            bot.logger.info_func("自身状态监控任务已启动")