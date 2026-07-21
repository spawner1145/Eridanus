import os

from developTools.event.events import GroupMessageEvent, PrivateMessageEvent
from developTools.message.message_components import Record


AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".wma", ".amr", ".silk")


def main(bot, config):
    bot.logger.info(f"Keyword audio reply plugin loaded 如有需要可将音频放置在data/voice/audio")
    audio_dir = "data/voice/audio"

    async def handle_message(event):

        text = (event.pure_text or "").strip()
        if not text:
            return

        for ext in AUDIO_EXTENSIONS:
            audio_path = os.path.join(audio_dir, f"{text}{ext}")
            if os.path.isfile(audio_path):
                bot.logger.info(f"Keyword audio matched '{text}', send: {audio_path}")
                await bot.send(event, Record(file=audio_path))
                return

    @bot.on(GroupMessageEvent)
    async def on_group_message(event: GroupMessageEvent):
        await handle_message(event)

    @bot.on(PrivateMessageEvent)
    async def on_private_message(event: PrivateMessageEvent):
        await handle_message(event)