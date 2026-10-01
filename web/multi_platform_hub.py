"""
multi_platform_hub.py - 多平台中转枢纽与网关
支持:
1. WebUI (group_id: 879886836)
2. Telegram 独立 Adapter (group_id: 11111xxxxx 虚拟群)
3. Android 悬浮窗 / 移动助手 (group_id: 222222 虚拟群)
实现 OneBot v11 双向消息流转、会话隔离与 QQ user_id 上下文记忆绑定。
"""

import asyncio
import json
import logging
import os
import threading
import time
from typing import Dict, Any, Optional, Set

logger = logging.getLogger("MultiPlatformHub")

class MultiPlatformHub:
    def __init__(self):
        # 绑定的 QQ 账号 (默认主控 QQ)
        self.default_qq_id = 1840094972
        # 已连接的 WebSocket 客户端集合
        self.ws_clients: Set[Any] = set()
        # 后端 Eridanus bot2 的 WebSocket 连接实例
        self.bot_backend_ws: Optional[Any] = None

        # 核心群号路由规范
        self.GROUP_WEBUI = 879886836
        self.PREFIX_TELEGRAM = "11111"  # 11111+channel_id
        self.GROUP_ANDROID = 222222

        # 异步任务事件循环（跑在独立后台线程中）
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

        # Android 客户端会话映射：user_id -> 等待回复的 Future 队列
        self.android_pending_responses: Dict[int, asyncio.Future] = {}
        # Android client ws 集合
        self.android_ws_clients: Set[Any] = set()

    def start_background(self):
        """启动后台事件循环线程（用于 Android 同步 API 的异步唤醒）"""
        if self._thread and self._thread.is_alive():
            return

        def _worker():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        self._thread = threading.Thread(target=_worker, name="MultiPlatformHubWorker", daemon=True)
        self._thread.start()
        logger.info("[MultiPlatformHub] 后台线程启动完成")

    def register_client(self, ws):
        self.ws_clients.add(ws)

    def unregister_client(self, ws):
        self.ws_clients.discard(ws)
        self.android_ws_clients.discard(ws)
        if self.bot_backend_ws == ws:
            self.bot_backend_ws = None

    def inject_event_to_bot(self, group_id: int, user_id: int, message_list: list, nickname: str = "??", raw_message: str = "", adapter_source: Optional[str] = None) -> dict:
        """
        构造标准的 OneBot v11 消息事件并注入给后端连接的 Eridanus
        """
        now_ms = int(time.time() * 1000)
        event = {
            "self_id": 1000000,
            "user_id": int(user_id) if user_id else self.default_qq_id,
            "time": int(time.time()),
            "message_id": now_ms,
            "real_id": now_ms % 2147483647,
            "message_seq": now_ms % 2147483647,
            "message_type": "group",
            "sender": {
                "user_id": int(user_id) if user_id else self.default_qq_id,
                "nickname": nickname,
                "card": "",
                "role": "member",
                "title": ""
            },
            "raw_message": raw_message,
            "font": 14,
            "sub_type": "normal",
            "message": message_list,
            "message_format": "array",
            "post_type": "message",
            "group_id": int(group_id),
            "adapter_source": adapter_source or ("android" if int(group_id) == self.GROUP_ANDROID else ("telegram" if str(group_id).startswith("11111") else "webui"))
        }

        # 广播给后端 bot
        event_json = json.dumps(event, ensure_ascii=False)
        for client in list(self.ws_clients):
            try:
                client.send(event_json)
            except Exception:
                self.ws_clients.discard(client)

        return event

    def dispatch_bot_action(self, msg_dict: dict, from_ws=None):
        """
        处理 Eridanus 发出的 Action 指令（如 send_group_msg 等），精准路由回对应平台
        """
        action = msg_dict.get("action", "")
        params = msg_dict.get("params", {})
        group_id = params.get("group_id")
        echo = msg_dict.get("echo")

        # 记录此 ws 是主系统/副bot的 backend
        if from_ws:
            self.bot_backend_ws = from_ws

        # 如果有 echo 请求，按 OneBot 规范回包
        if echo is not None and from_ws:
            try:
                from_ws.send(json.dumps({
                    "status": "ok",
                    "retcode": 0,
                    "data": {"message_id": int(time.time() * 1000) % 2147483647},
                    "message": "",
                    "wording": "",
                    "echo": echo
                }))
            except Exception:
                self.ws_clients.discard(from_ws)

        raw_msg = params.get("message", "")
        extracted_text = self._extract_text(raw_msg)
        extracted_images = self._extract_images(raw_msg)

        # 1. 广播给所有的 Adapter WS 客户端（包括 TelegramAdapter）
        action_json = json.dumps(msg_dict, ensure_ascii=False)
        for client in list(self.ws_clients):
            if client != from_ws:
                try:
                    client.send(action_json)
                except Exception:
                    self.ws_clients.discard(client)

        # 2. 如果是发给 Android 悬浮窗 (group_id == 222222)
        if group_id == self.GROUP_ANDROID or str(group_id) == str(self.GROUP_ANDROID):
            # 唤醒 HTTP 阻塞等待的请求
            for future_user_id, fut in list(self.android_pending_responses.items()):
                if not fut.done():
                    fut.set_result({
                        "reply": extracted_text,
                        "images": extracted_images,
                        "raw_message": raw_msg,
                        "time": time.time()
                    })
            # 同时也推送给连接的 Android WebSocket 客户端
            android_event = json.dumps({
                "type": "bot_reply",
                "group_id": self.GROUP_ANDROID,
                "text": extracted_text,
                "images": extracted_images,
                "raw": raw_msg,
                "timestamp": int(time.time() * 1000)
            }, ensure_ascii=False)
            for ws in list(self.android_ws_clients):
                try:
                    ws.send(android_event)
                except Exception:
                    self.android_ws_clients.discard(ws)

    def _extract_text(self, message: Any) -> str:
        """从 OneBot 消息中提取纯文本"""
        if isinstance(message, str):
            return message
        if isinstance(message, list):
            texts = []
            for item in message:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        texts.append(item.get("data", {}).get("text", ""))
                    elif item.get("type") == "image":
                        texts.append("[图片]")
                elif isinstance(item, str):
                    texts.append(item)
            return "".join(texts)
        return str(message)

    def _extract_images(self, message: Any) -> list:
        """从 OneBot 消息中提取图片文件或链接"""
        images = []
        if isinstance(message, list):
            for item in message:
                if isinstance(item, dict) and item.get("type") == "image":
                    file_info = item.get("data", {}).get("file") or item.get("data", {}).get("url")
                    if file_info:
                        images.append(file_info)
        return images

# 全局单例
hub_instance = MultiPlatformHub()
