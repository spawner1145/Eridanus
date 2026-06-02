import os
import shutil
import subprocess
import tempfile

from developTools.event.events import GroupMessageEvent, PrivateMessageEvent
from developTools.message.message_components import File, Record


def _normalize_text(text: str, ignore_case: bool = False) -> str:
    normalized = (text or "").strip()
    return normalized.lower() if ignore_case else normalized


def _find_audio_file(plugin_config: dict, message_text: str):
    replies = plugin_config.get("replies", [])
    match_mode = plugin_config.get("match_mode", "exact")
    ignore_case = plugin_config.get("ignore_case", False)

    normalized_message = _normalize_text(message_text, ignore_case)
    if not normalized_message:
        return None, None

    for item in replies:
        if not isinstance(item, str):
            continue

        keyword = item.strip()
        normalized_keyword = _normalize_text(keyword, ignore_case)
        if not normalized_keyword:
            continue

        matched = (
            normalized_message == normalized_keyword
            if match_mode == "exact"
            else normalized_keyword in normalized_message
        )
        if matched:
            filename = keyword if keyword.lower().endswith(".mp3") else f"{keyword}.mp3"
            return keyword, filename

    return None, None


def _prepare_voice_file(audio_path: str, plugin_config: dict, logger):
    if not plugin_config.get("transcode_to_wav", True):
        return audio_path, None

    if os.path.splitext(audio_path)[1].lower() == ".wav":
        return audio_path, None

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        logger.warning(f"ffmpeg not found, send original audio: {audio_path}")
        return audio_path, None

    temp_dir = tempfile.mkdtemp(prefix="keyword_audio_reply_")
    wav_path = os.path.join(
        temp_dir,
        os.path.splitext(os.path.basename(audio_path))[0] + ".wav",
    )

    command = [
        ffmpeg_path,
        "-y",
        "-i",
        audio_path,
        "-ac",
        "1",
        "-ar",
        "24000",
        wav_path,
    ]

    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return wav_path, temp_dir
    except Exception as exc:
        logger.warning(f"audio transcode failed: {audio_path}, error={exc}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        if plugin_config.get("fallback_to_original", True):
            return audio_path, None
        return None, None


def main(bot, config):
    plugin_config = config.system_plugin.config
    plugin_dir = os.path.dirname(__file__)

    async def handle_message(event):
        if not plugin_config.get("enabled", True):
            return

        keyword, filename = _find_audio_file(plugin_config, event.pure_text)
        if not filename:
            return

        audio_dir = plugin_config.get("audio_dir", "audio")
        audio_path = os.path.join(plugin_dir, audio_dir, filename)
        if not os.path.isfile(audio_path):
            bot.logger.warning(f"Keyword audio file not found for '{keyword}': {audio_path}")
            return

        voice_path, temp_dir = _prepare_voice_file(audio_path, plugin_config, bot.logger)
        if not voice_path:
            return

        try:
            bot.logger.info(f"Keyword audio matched '{keyword}', send: {voice_path}")
            if plugin_config.get("send_as_voice", True):
                await bot.send(event, Record(file=voice_path))
            else:
                await bot.send(event, File(file=voice_path))
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

    @bot.on(GroupMessageEvent)
    async def on_group_message(event: GroupMessageEvent):
        await handle_message(event)

    @bot.on(PrivateMessageEvent)
    async def on_private_message(event: PrivateMessageEvent):
        await handle_message(event)
