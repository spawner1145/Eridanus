"""
concurrency.py
并发控制器 —— 全局并发信号量 + 消息合并窗口
防止同一会话同时处理多条消息导致的回复混乱
"""

import asyncio
import time
from typing import Dict, Optional

from framework_common.database_util.RedisCacheManager import create_custom_cache_manager


class ConcurrencyController:

    def __init__(self, config):
        self.cfg = config
        ccfg = config.mai_reply.config.get("concurrency", {})
        max_concurrent: int = int(ccfg.get("max_concurrent", 20))
        self.merge_window_ms: int = int(ccfg.get("message_merge_window_ms", 1200))
        self.lock_timeout: int = int(ccfg.get("lock_timeout", 30))

        # 全局并发信号量
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # 消息合并：session_key -> (text, timestamp, asyncio.Event)
        self._pending: Dict[str, dict] = {}
        self._pending_lock = asyncio.Lock()

    async def acquire_global(self) -> None:
        """获取全局并发槽（阻塞等待）"""
        await self._semaphore.acquire()

    def release_global(self) -> None:
        """释放全局并发槽"""
        self._semaphore.release()

    async def merge_or_process(self, session_key: str, text: str) -> Optional[str]:
        """
        消息合并窗口：
        如果在 merge_window_ms 内收到了同一会话的多条消息，
        则合并为一条处理（取最新的那条）。
        返回最终应该处理的文本，如果当前消息被合并掉了则返回 None。

        使用方式：
            final_text = await controller.merge_or_process(session_key, text)
            if final_text is None:
                return  # 被合并，不处理
        """
        if self.merge_window_ms <= 0:
            return text

        window_sec = self.merge_window_ms / 1000.0
        event = asyncio.Event()

        async with self._pending_lock:
            if session_key in self._pending:
                # 已有一条在等待中，更新文本并重置它的等待（它会被我们替代）
                self._pending[session_key]["text"] = text
                self._pending[session_key]["event"].set()  # 取消旧的等待
                # 重新注册自己
                new_event = asyncio.Event()
                self._pending[session_key] = {"text": text, "event": new_event}
                local_event = new_event
            else:
                self._pending[session_key] = {"text": text, "event": event}
                local_event = event

        # 等待 merge_window_ms，看看会不会被后来的消息取代
        try:
            await asyncio.wait_for(local_event.wait(), timeout=window_sec)
            # 被后来的消息 set() 了，说明我被替代，不处理
            return None
        except asyncio.TimeoutError:
            # 没被替代，轮到我处理
            async with self._pending_lock:
                pending = self._pending.get(session_key)
                if pending and pending.get("event") is local_event:
                    final_text = pending["text"]
                    del self._pending[session_key]
                    return final_text
                # 竞争失败
                return None
