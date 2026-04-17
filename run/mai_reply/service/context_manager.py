"""
context_manager.py
上下文/记忆管理 —— 增加对 Bot 发送消息 ID 的短效追踪，用于精准捕获“回复事件”
"""

import asyncio
import json
import time
from typing import List, Dict, Optional

from framework_common.database_util.RedisCacheManager import create_custom_cache_manager


class ContextManager:

    def __init__(self, config):
        self.cfg = config
        ccfg = config.mai_reply.config.get("context", {})
        self.max_turns: int = ccfg.get("max_turns", 20)
        self.group_window: int = ccfg.get("group_context_window", 15)
        self.session_ttl: int = ccfg.get("session_ttl", 7200)
        self.enable_impression: bool = ccfg.get("enable_impression", True)
        self.impression_ttl: int = ccfg.get("impression_ttl", 604800)

        db_cfg = config.mai_reply.config.get("redis", {})
        ctx_db = db_cfg.get("context_db", 5)
        imp_db = db_cfg.get("impression_db", 6)

        self._ctx_cache = create_custom_cache_manager(db_number=ctx_db, cache_ttl=self.session_ttl)
        self._imp_cache = create_custom_cache_manager(db_number=imp_db, cache_ttl=self.impression_ttl)

    # ------------------------------------------------------------------ Bot 发送消息 ID 追踪
    def record_bot_message(self, msg_id: str) -> None:
        """记录bot发出的消息ID，用于检测别人是否在回复bot。保留24小时"""
        if not msg_id:
            return
        key = f"bot_msg:{msg_id}"
        self._ctx_cache.set(key, "1", ttl=86400)

    def is_bot_message(self, msg_id: str) -> bool:
        """判断某个群消息ID是否为bot自己发出的"""
        if not msg_id:
            return False
        key = f"bot_msg:{msg_id}"
        return bool(self._ctx_cache.exists(key))

    # ------------------------------------------------------------------ keys 等其它历史逻辑保持不变
    @staticmethod
    def _private_key(user_id: int) -> str:
        return f"ctx:private:{user_id}"

    @staticmethod
    def _group_key(group_id: int, user_id: int) -> str:
        return f"ctx:group:{group_id}:{user_id}"

    @staticmethod
    def _group_window_key(group_id: int) -> str:
        return f"ctx:gwin:{group_id}"

    @staticmethod
    def _impression_key(user_id: int) -> str:
        return f"imp:{user_id}"

    @staticmethod
    def _lock_key(session_key: str) -> str:
        return f"lock:{session_key}"

    def _load_history(self, key: str) -> List[Dict]:
        raw = self._ctx_cache.get(key)
        if not raw: return[]
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            return data if isinstance(data, list) else[]
        except Exception:
            return []

    def _save_history(self, key: str, history: List[Dict]) -> None:
        trimmed = history[-(self.max_turns * 2):]
        self._ctx_cache.set(key, json.dumps(trimmed, ensure_ascii=False), ttl=self.session_ttl)

    def get_session_history(self, group_id: Optional[int], user_id: int) -> List[Dict]:
        key = self._group_key(group_id, user_id) if group_id else self._private_key(user_id)
        return self._load_history(key)

    def append_to_session(self, group_id: Optional[int], user_id: int, user_message: str, assistant_message: str) -> None:
        key = self._group_key(group_id, user_id) if group_id else self._private_key(user_id)
        history = self._load_history(key)
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": assistant_message})
        self._save_history(key, history)

    def clear_session(self, group_id: Optional[int], user_id: int) -> None:
        key = self._group_key(group_id, user_id) if group_id else self._private_key(user_id)
        self._ctx_cache.delete(key)

    def push_group_window(self, group_id: int, sender_name: str, text: str) -> None:
        key = self._group_window_key(group_id)
        window: List[Dict] = self._load_group_window(group_id)
        window.append({"sender": sender_name, "text": text, "ts": int(time.time())})
        window = window[-self.group_window:]
        self._ctx_cache.set(key, json.dumps(window, ensure_ascii=False), ttl=self.session_ttl)

    def _load_group_window(self, group_id: int) -> List[Dict]:
        key = self._group_window_key(group_id)
        raw = self._ctx_cache.get(key)
        if not raw: return[]
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            return data if isinstance(data, list) else []
        except Exception:
            return[]

    def build_group_context_snippet(self, group_id: int, bot_name: str) -> str:
        window = self._load_group_window(group_id)
        if not window: return ""
        lines =[]
        for item in window:
            sender = item.get("sender", "?")
            text = item.get("text", "")
            if sender == bot_name:
                lines.append(f"你说：{text}")
            else:
                lines.append(f"{sender}：{text}")
        return "【群里最近的聊天记录】\n" + "\n".join(lines)

    def get_impression(self, user_id: int) -> str:
        if not self.enable_impression: return ""
        raw = self._imp_cache.get(self._impression_key(user_id))
        return raw if isinstance(raw, str) else ""

    def update_impression(self, user_id: int, summary: str) -> None:
        if not self.enable_impression: return
        self._imp_cache.set(self._impression_key(user_id), summary, ttl=self.impression_ttl)

    async def acquire_lock(self, session_key: str, timeout: int = 30) -> bool:
        lock_key = self._lock_key(session_key)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._ctx_cache.exists(lock_key):
                self._ctx_cache.set(lock_key, "1", ttl=timeout)
                return True
            await asyncio.sleep(0.1)
        return False

    def release_lock(self, session_key: str) -> None:
        self._ctx_cache.delete(self._lock_key(session_key))

    def session_key_for(self, group_id: Optional[int], user_id: int) -> str:
        return self._group_key(group_id, user_id) if group_id else self._private_key(user_id)