import requests

from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import Image
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager


def main(bot: ExtendBot,config: YAMLManager):
    @bot.on(GroupMessageEvent)
    async def handle_group_message(event: GroupMessageEvent):
        if event.pure_text=="测试244":
            r=requests.get('https://api.xingzhige.com/API/Calendar/')
            with open("123.png", "wb") as f:
                f.write(r.content)
            await bot.send(event,Image(file="123.png"))
            await bot.send(event,"Hello World!")