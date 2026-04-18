"""
context_manager.py
上下文/记忆管理 —— Redis 热缓存 + SQLite 冷存储双层持久化
- Redis 负责快速读写（TTL 热缓存）
- SQLite 负责永久落盘（重启/缓存清理后自动恢复）
- 写入时同时写 Redis + SQLite
- 读取时 Redis miss 则从 SQLite 回填
"""

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import List, Dict, Optional

from framework_common.database_util.RedisCacheManager import create_custom_cache_manager


# ──────────────────────────────────────────────────────────────────────────────
# SQLite 持久层（独立辅助类，方便测试和替换）
# ──────────────────────────────────────────────────────────────────────────────

class SQLitePersistence:
    """
    极简 KV 持久层，使用 SQLite。
    value 统一存 TEXT（调用方负责 JSON 序列化）。
    线程安全：使用 check_same_thread=False + WAL 模式。
    """

    def __init__(self, db_path: str = "context_store.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS kv_store (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)
        self._conn.commit()

    def get(self, key: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT value FROM kv_store WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def set(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO kv_store (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, int(time.time())),
        )
        self._conn.commit()

    def delete(self, key: str) -> None:
        self._conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# ContextManager 主类
# ──────────────────────────────────────────────────────────────────────────────

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

        # SQLite 持久层路径可通过配置指定，默认放在当前目录
        sqlite_cfg = config.mai_reply.config.get("sqlite", {})
        ctx_sqlite_path  = sqlite_cfg.get("context_db_path",    "data/context_store.db")
        imp_sqlite_path  = sqlite_cfg.get("impression_db_path", "data/impression_store.db")

        self._ctx_sqlite = SQLitePersistence(ctx_sqlite_path)
        self._imp_sqlite = SQLitePersistence(imp_sqlite_path)

    # ------------------------------------------------------------------ 内部读写辅助（带双层 fallback）

    def _ctx_get(self, key: str) -> Optional[str]:
        """先读 Redis；miss 则从 SQLite 回填 Redis 后返回。"""
        value = self._ctx_cache.get(key)
        if value:
            return value if isinstance(value, str) else None
        # cache miss → 从 SQLite 恢复
        value = self._ctx_sqlite.get(key)
        if value:
            self._ctx_cache.set(key, value, ttl=self.session_ttl)
        return value

    def _ctx_set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """同时写 Redis 和 SQLite。"""
        self._ctx_cache.set(key, value, ttl=ttl or self.session_ttl)
        self._ctx_sqlite.set(key, value)

    def _ctx_delete(self, key: str) -> None:
        self._ctx_cache.delete(key)
        self._ctx_sqlite.delete(key)

    def _ctx_exists(self, key: str) -> bool:
        if self._ctx_cache.exists(key):
            return True
        return self._ctx_sqlite.get(key) is not None

    def _imp_get(self, key: str) -> Optional[str]:
        value = self._imp_cache.get(key)
        if value:
            return value if isinstance(value, str) else None
        value = self._imp_sqlite.get(key)
        if value:
            self._imp_cache.set(key, value, ttl=self.impression_ttl)
        return value

    def _imp_set(self, key: str, value: str) -> None:
        self._imp_cache.set(key, value, ttl=self.impression_ttl)
        self._imp_sqlite.set(key, value)

    # ------------------------------------------------------------------ Bot 发送消息 ID 追踪
    # 注意：bot_msg 仅用于短效检测（24h），不需要永久持久化，仍只写 Redis。

    def record_bot_message(self, msg_id: str) -> None:
        """记录 bot 发出的消息 ID，用于检测别人是否在回复 bot。保留 24h。"""
        if not msg_id:
            return
        self._ctx_cache.set(f"bot_msg:{msg_id}", "1", ttl=86400)

    def is_bot_message(self, msg_id: str) -> bool:
        """判断某个群消息 ID 是否为 bot 自己发出的。"""
        if not msg_id:
            return False
        return bool(self._ctx_cache.exists(f"bot_msg:{msg_id}"))

    # ------------------------------------------------------------------ Keys

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

    # ------------------------------------------------------------------ 历史读写（现在有持久化）

    def _load_history(self, key: str) -> List[Dict]:
        raw = self._ctx_get(key)
        if not raw:
            return []
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_history(self, key: str, history: List[Dict]) -> None:
        trimmed = history[-(self.max_turns * 2):]
        self._ctx_set(key, json.dumps(trimmed, ensure_ascii=False))

    def get_session_history(self, group_id: Optional[int], user_id: int) -> List[Dict]:
        key = self._group_key(group_id, user_id) if group_id else self._private_key(user_id)
        return self._load_history(key)

    def append_to_session(
        self,
        group_id: Optional[int],
        user_id: int,
        user_message: str,
        assistant_message: str,
    ) -> None:
        key = self._group_key(group_id, user_id) if group_id else self._private_key(user_id)
        history = self._load_history(key)
        history.append({"role": "user",      "content": user_message})
        history.append({"role": "assistant", "content": assistant_message})
        self._save_history(key, history)

    def clear_session(self, group_id: Optional[int], user_id: int) -> None:
        """清空会话（Redis + SQLite 均删除）。"""
        key = self._group_key(group_id, user_id) if group_id else self._private_key(user_id)
        self._ctx_delete(key)

    # ------------------------------------------------------------------ 群聊窗口（持久化）

    def push_group_window(self, group_id: int, sender_name: str, text: str) -> None:
        key = self._group_window_key(group_id)
        window: List[Dict] = self._load_group_window(group_id)
        window.append({"sender": sender_name, "text": text, "ts": int(time.time())})
        window = window[-self.group_window:]
        self._ctx_set(key, json.dumps(window, ensure_ascii=False))

    def _load_group_window(self, group_id: int) -> List[Dict]:
        key = self._group_window_key(group_id)
        raw = self._ctx_get(key)
        if not raw:
            return []
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def build_group_context_snippet(self, group_id: int, bot_name: str) -> str:
        window = self._load_group_window(group_id)
        if not window:
            return ""
        lines = []
        for item in window:
            sender = item.get("sender", "?")
            text   = item.get("text", "")
            lines.append(f"你说：{text}" if sender == bot_name else f"{sender}：{text}")
        return "【群里最近的聊天记录】\n" + "\n".join(lines)

    # ------------------------------------------------------------------ 印象（持久化）

    def get_impression(self, user_id: int) -> str:
        if not self.enable_impression:
            return ""
        raw = self._imp_get(self._impression_key(user_id))
        return raw if isinstance(raw, str) else ""

    def update_impression(self, user_id: int, summary: str) -> None:
        if not self.enable_impression:
            return
        self._imp_set(self._impression_key(user_id), summary)

    # ------------------------------------------------------------------ 分布式锁（仍只用 Redis，锁不需要持久化）

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

    # ------------------------------------------------------------------ 生命周期

    def close(self) -> None:
        """进程退出时调用，确保 SQLite 连接正确关闭。"""
        self._ctx_sqlite.close()
        self._imp_sqlite.close()