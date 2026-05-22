
import asyncio
import base64
import uuid

from developTools.event.events import GroupMessageEvent, PrivateMessageEvent
from developTools.message.message_components import Text, Image, Mface, Record
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from run.tts_v2.service.GPT_SoVits import AsyncGPTSoVITSClient


def main(bot: ExtendBot, config: YAMLManager):


    bot.logger.info("[TTS V2] 已加载")

    @bot.on(GroupMessageEvent)
    async def handle_group(event: GroupMessageEvent):
        if event.pure_text.startswith("/达妮娅说"):
            text=event.pure_text.split("说",1)[1]
            SERVER_URL = "http://localhost:9872"
            client = AsyncGPTSoVITSClient(base_url=SERVER_URL)


            p=await client.generate_tts(
                target_text=text,
            )
            await bot.send(event,Record(file=p))