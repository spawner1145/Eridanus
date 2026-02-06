

import asyncio

from framework_common.ToolKits import Util
from framework_common.manshuo_draw import manshuo_draw
from run.resource_collector.service.hitomi.HitomiParsing import HitomiPage
from run.resource_collector.service.hitomi.drawer import render_hitomi_sections

util=Util.get_instance()
from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import Image, Node, Text, File

from framework_common.database_util.User import get_user

def main(bot,config):
    result=None
    '''
    data_cache暂存数据。d[0]为当日流行，d[1]为最新
    '''
    cache_operator=[]
    @bot.on(GroupMessageEvent)
    async def hitomi1(event: GroupMessageEvent):
        nonlocal cache_operator,result
        if event.pure_text=="/hitomi":
            data_cache=await HitomiPage()
            result=await render_hitomi_sections(data_cache[0],data_cache[1])
            await bot.send(event, [
                "Hitomi今日流行",
                Image(file=result["popular"]["image"])
            ])

            await bot.send(event, [
                "Hitomi今日上新",
                Image(file=result["latest"]["image"])
            ])
            await bot.send(event,'获取指令如下:\n=======\n/hitomi 最新 3 1\n获取第三行第一个\n=======\n/hitomi 热门 2 2\n获取第二行第二个')
            if event.user_id in cache_operator:
                await bot.send(event,"已重置推荐页")
            else:
                cache_operator.append(event.user_id)
        if event.user_id not in cache_operator:
            return
        if not event.pure_text.startswith("/hitomi "):
            return
        if result is None:
            await bot.send(event, "请先发送 /hitomi 获取推荐页")
            return
        try:
            if event.pure_text.startswith("/hitomi 最新 "):
                section = result["latest"]
                raw = event.pure_text.replace("/hitomi 最新 ", "").strip()

            elif event.pure_text.startswith("/hitomi 热门 "):
                section = result["popular"]
                raw = event.pure_text.replace("/hitomi 热门 ", "").strip()

            else:
                return

            x, y = map(int, raw.split())
        except Exception:
            await bot.send(event, "参数格式错误，应为：/hitomi 最新 行 列")
            return

        for item in section["items"]:
            if item["row"] == x and item["col"] == y:
                await bot.send(event, [
                    Text(f"标题：{item['title']}"),
                    Text(f"\n链接：{item['url']}"),
                ])
                return

            # -------- 未命中 --------
        await bot.send(event, "未找到对应位置的条目，请检查行列是否超出范围")