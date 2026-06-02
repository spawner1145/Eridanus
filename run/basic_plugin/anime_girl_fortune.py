import random
import time
from pathlib import Path

from developTools.event.events import GroupMessageEvent, PrivateMessageEvent
from developTools.message.message_components import At, Text
from ruamel.yaml import YAML


PLUGIN_DIR = Path(__file__).parent
CONFIG_PATH = PLUGIN_DIR / "config.yaml"
CACHE_PATH = PLUGIN_DIR / "anime_girl_fortune_user_cache.yaml"
DEFAULT_CONFIG = {
    "enabled": True,
    "trigger": "今天我是什么少女",
    "target_trigger": "今天他是什么少女",
    "reply_prefix": "二次元少女的",
    "reset_hours": 24,
    "templates": [],
}
YAML_LOADER = YAML(typ="safe")
YAML_WRITER = YAML()


def _load_plugin_config(config) -> dict:
    try:
        loaded = config.basic_plugin.config
        if isinstance(loaded, dict):
            merged = DEFAULT_CONFIG.copy()
            merged.update(loaded)
            return merged
    except Exception:
        pass

    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            loaded = YAML_LOADER.load(f) or {}
        if isinstance(loaded, dict):
            merged = DEFAULT_CONFIG.copy()
            merged.update(loaded)
            return merged
    except Exception:
        return DEFAULT_CONFIG

    return DEFAULT_CONFIG


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}

    try:
        with CACHE_PATH.open("r", encoding="utf-8") as f:
            loaded = YAML_LOADER.load(f) or {}
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _save_cache(cache: dict):
    with CACHE_PATH.open("w", encoding="utf-8") as f:
        YAML_WRITER.dump(cache, f)


def _sender_name(event) -> str:
    sender = getattr(event, "sender", None)
    if sender is not None:
        for attr in ("card", "nickname"):
            value = getattr(sender, attr, "")
            if value:
                return str(value).strip()
    return str(getattr(event, "user_id", "神秘少女"))


def _message_text(event) -> str:
    message_chain = getattr(event, "message_chain", None)
    if message_chain is not None:
        try:
            if message_chain.has(Text):
                return "".join(str(item.text) for item in message_chain.get(Text)).strip()
        except Exception:
            pass

    return str(getattr(event, "pure_text", "") or "").strip()


def _first_at(event):
    message_chain = getattr(event, "message_chain", None)
    if message_chain is not None:
        try:
            if message_chain.has(At):
                return message_chain.get(At)[0]
        except Exception:
            pass

    at_items = event.get("at") if hasattr(event, "get") else None
    if not at_items:
        return None
    return at_items[0]


def _at_qq(at_item) -> str | None:
    if isinstance(at_item, dict):
        qq = at_item.get("qq") or at_item.get("target") or at_item.get("user_id")
    else:
        qq = getattr(at_item, "qq", None) or getattr(at_item, "target", None) or getattr(at_item, "user_id", None)
    return str(qq).strip() if qq else None


def _at_name(at_item) -> str | None:
    if isinstance(at_item, dict):
        name = at_item.get("name") or at_item.get("nickname") or at_item.get("card")
    else:
        name = getattr(at_item, "name", None) or getattr(at_item, "nickname", None) or getattr(at_item, "card", None)
    return str(name).strip() if name else None


async def _target_name(bot, event, user_id: str, fallback: str | None = None) -> str:
    group_id = getattr(event, "group_id", None)
    if group_id:
        try:
            result = await bot.get_group_member_info(group_id=group_id, user_id=int(user_id))
            data = result.get("data", {}) if isinstance(result, dict) else {}
            name = data.get("card") or data.get("nickname")
            if name:
                return str(name).strip()
        except Exception:
            pass
    return fallback or user_id


def _template_for_user(plugin_config: dict, user_id: str) -> str | None:
    templates = plugin_config.get("templates", [])
    if not templates:
        return None

    now = int(time.time())
    reset_seconds = int(plugin_config.get("reset_hours", 24) or 24) * 3600
    cache = _load_cache()
    record = cache.get(user_id, {})

    if isinstance(record, dict):
        index = record.get("index")
        expires_at = int(record.get("expires_at", 0) or 0)
        if isinstance(index, int) and 0 <= index < len(templates) and expires_at > now:
            return templates[index]

    index = random.randrange(len(templates))
    cache[user_id] = {
        "index": index,
        "expires_at": now + reset_seconds,
    }
    _save_cache(cache)
    return templates[index]


def _build_reply(plugin_config: dict, name: str, user_id: str) -> str | None:
    template = _template_for_user(plugin_config, user_id)
    if not template:
        return None

    prefix = plugin_config.get("reply_prefix", "二次元少女的")
    return f"{prefix}{name}，{template}"


def main(bot, config):
    plugin_config = _load_plugin_config(config)

    async def handle_message(event):
        if not plugin_config.get("enabled", True):
            return

        text = _message_text(event).replace(" ", "")
        trigger = str(plugin_config.get("trigger", "今天我是什么少女")).strip()
        target_trigger = str(plugin_config.get("target_trigger", "今天他是什么少女")).strip()

        if text == trigger:
            target_id = str(event.user_id)
            target_name = _sender_name(event)
        elif text.startswith(target_trigger):
            at_item = _first_at(event)
            target_id = _at_qq(at_item) if at_item else None
            if not target_id:
                return
            target_name = await _target_name(bot, event, target_id, _at_name(at_item))
        else:
            return

        reply = _build_reply(plugin_config, target_name, target_id)
        if reply:
            await bot.send(event, reply)

    @bot.on(GroupMessageEvent)
    async def on_group_message(event: GroupMessageEvent):
        await handle_message(event)

    @bot.on(PrivateMessageEvent)
    async def on_private_message(event: PrivateMessageEvent):
        await handle_message(event)
