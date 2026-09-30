# telegram_adapter.py
"""
Telegram Adapter:
基于 Telegram 官方 Bot API 与 OneBot v11 标准协议的双向适配桥接器。
参考 Tele-KiraLink (github.com/Echomirix/Tele-KiraLink) 的消息转换机制。
通过 WebSocket 连接至 Eridanus WebUI 后端 Hub。
"""

import asyncio
import json
import os
import time
import urllib.parse
from typing import Dict, Any, Optional, List
import httpx
import websockets

from developTools.utils.logger import get_logger


class TelegramAdapter:
    def __init__(
        self,
        token: str,
        hub_ws_url: str = "ws://127.0.0.1:5007/api/ws",
        proxy: str = "http://127.0.0.1:10809",
        default_qq_id: int = 1840094972
    ):
        self.token = token.strip()
        self.hub_ws_url = hub_ws_url
        self.proxy = proxy if proxy else None
        self.default_qq_id = int(default_qq_id)
        self.logger = get_logger()

        # Bot 自身信息
        self.bot_id: int = 1000000
        self.bot_username: str = ""
        self.bot_first_name: str = "YuccaBot"

        # 映射表: 11111-前缀group_id <-> 真实 Telegram chat_id (int or str)
        self.group_to_tg_chat: Dict[int, Any] = {}
        # 映射表: OneBot message_id <-> 真实 Telegram message_id & chat_id
        self.msg_id_to_tg: Dict[int, Dict[str, Any]] = {}
        # 绑定持久化路径: data/dataBase/tg_user_bindings.json
        self.bindings_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "dataBase", "tg_user_bindings.json"
        )
        self.tg_user_bindings: Dict[str, int] = self._load_bindings()

    def _load_bindings(self) -> Dict[str, int]:
        try:
            if os.path.exists(self.bindings_file):
                with open(self.bindings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return {str(k): int(v) for k, v in data.items()}
        except Exception as e:
            self.logger.tg_warning(f"[TelegramAdapter] 读取用户绑定配置失败: {e}")
        return {}

    def _save_bindings(self):
        try:
            os.makedirs(os.path.dirname(self.bindings_file), exist_ok=True)
            with open(self.bindings_file, "w", encoding="utf-8") as f:
                json.dump(self.tg_user_bindings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.tg_warning(f"[TelegramAdapter] 保存用户绑定配置失败: {e}")

        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_running = False
        self.tg_offset = 0

    def encode_to_virtual_group_id(self, tg_chat_id: Any) -> int:
        """
        将 Telegram 的 channel_id/chat_id 统一转成以 11111 为前缀的数字 group_id:
        若 channel_id 是纯数字则直接拼在 11111 后面；
        若包含非数字字符，则将字符转换成对应 ascii/数字码后拼入。
        """
        raw_str = str(tg_chat_id).strip()
        if raw_str.startswith("-100"):
            clean = raw_str[4:]
        elif raw_str.startswith("-"):
            clean = raw_str[1:]
        else:
            clean = raw_str

        if clean.isdigit():
            virtual_id = int("11111" + clean[:12])
        else:
            num_repr = "".join(str(ord(c)) for c in clean)[:12]
            virtual_id = int("11111" + num_repr)

        self.group_to_tg_chat[virtual_id] = tg_chat_id
        return virtual_id

    async def _fetch_bot_info(self):
        """从 Telegram 官方 API 获取 Bot 自身信息"""
        url = f"https://api.telegram.org/bot{self.token}/getMe"
        try:
            async with httpx.AsyncClient(proxy=self.proxy, timeout=15.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        bot_info = data.get("result", {})
                        self.bot_id = bot_info.get("id", self.bot_id)
                        self.bot_username = bot_info.get("username", "")
                        self.bot_first_name = bot_info.get("first_name", "YuccaBot")
                        self.logger.tg_info(f"[TelegramAdapter] 成功获取 Bot 信息: @{self.bot_username} (ID: {self.bot_id})")
        except Exception as e:
            self.logger.tg_warning(f"[TelegramAdapter] 获取 Bot 信息失败: {e}")

    async def start(self):
        """启动 Telegram Adapter：连接 Hub WS 与 Telegram 轮询"""
        self.is_running = True
        self.logger.tg_info("正在启动 Telegram Adapter 双向桥接服务...")
        await self._fetch_bot_info()

        await asyncio.gather(
            self._connect_hub_ws_loop(),
            self._poll_telegram_updates(),
            return_exceptions=True
        )

    async def _connect_hub_ws_loop(self):
        """持续连接 WebUI Hub WS"""
        while self.is_running:
            try:
                self.logger.tg_info(f"Telegram Adapter 正在连接 Hub: {self.hub_ws_url}")
                async with websockets.connect(self.hub_ws_url) as ws:
                    self.ws = ws
                    self.logger.tg_info("✅ Telegram Adapter 成功连接至 Hub WS！")
                    await self._listen_hub_ws()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.tg_warning(f"Telegram Adapter WS 连接断开: {e}，5秒后重试...")
                self.ws = None
                await asyncio.sleep(5)

    def _resolve_target_chat(self, data: dict) -> Optional[Any]:
        """从 Action 数据中推断目标 Telegram Chat ID"""
        params = data.get("params", {})
        group_id = params.get("group_id")
        user_id = params.get("user_id")
        src = data.get("adapter_source")

        tg_chat_id = None
        if src == "telegram":
            if group_id:
                gid = int(group_id)
                tg_chat_id = self.group_to_tg_chat.get(gid)
                if not tg_chat_id and str(gid).startswith("11111"):
                    gid_str = str(gid)[5:]
                    tg_chat_id = -int("100" + gid_str) if len(gid_str) >= 9 else int(gid_str)
            if not tg_chat_id and user_id:
                tg_chat_id = user_id
        elif group_id and str(group_id).startswith("11111"):
            gid = int(group_id)
            tg_chat_id = self.group_to_tg_chat.get(gid)
            if not tg_chat_id:
                gid_str = str(gid)[5:]
                tg_chat_id = -int("100" + gid_str) if len(gid_str) >= 9 else int(gid_str)
        elif user_id:
            # 查找绑定的 chat_id 或虚拟 user_id 对应的 chat_id
            target_uid = int(user_id)
            for c_id, b_qq in self.tg_user_bindings.items():
                if b_qq == target_uid:
                    tg_chat_id = c_id
                    break
            if not tg_chat_id and str(target_uid).startswith("11111"):
                raw_cid = str(target_uid)[5:]
                tg_chat_id = -int(raw_cid) if (len(raw_cid) >= 9) else int(raw_cid)

        return tg_chat_id

    async def _listen_hub_ws(self):
        """监听来自 WebUI Hub 广播的 OneBot Action 指令"""
        async for raw_msg in self.ws:
            try:
                data = json.loads(raw_msg)
                action = data.get("action", "")
                params = data.get("params", {})
                tg_chat_id = self._resolve_target_chat(data)

                if not tg_chat_id:
                    continue

                # 1. 普通群/私聊发送 (send_group_msg / send_private_msg)
                if action in ("send_group_msg", "send_private_msg"):
                    raw_message = params.get("message", "")
                    await self._send_to_telegram(tg_chat_id, raw_message)

                # 2. 合并转发 (send_group_forward_msg / send_private_forward_msg)
                elif action in ("send_group_forward_msg", "send_private_forward_msg"):
                    nodes = params.get("messages", [])
                    await self._send_forward_nodes_to_telegram(tg_chat_id, nodes)

                # 3. 发送文件 (upload_group_file / upload_private_file)
                elif action in ("upload_group_file", "upload_private_file"):
                    file_path = params.get("file", "")
                    file_name = params.get("name")
                    await self._send_document_to_telegram(tg_chat_id, file_path, file_name)

                # 4. 其它带 message 或 messages 字段的动作
                elif "messages" in params:
                    await self._send_forward_nodes_to_telegram(tg_chat_id, params.get("messages", []))
                elif "message" in params:
                    await self._send_to_telegram(tg_chat_id, params.get("message", ""))

            except Exception as e:
                self.logger.tg_error(f"[TelegramAdapter] 处理 Hub 消息异常: {e}")

    def _resolve_local_path(self, raw_path: str) -> Optional[str]:
        """解析本地文件 URI / 绝对路径 / 反斜杠兼容性与 URL 解码"""
        p = str(raw_path).strip()
        if p.startswith("file:///"):
            p = p[8:]
        elif p.startswith("file://"):
            p = p[7:]

        candidates = [p]
        try:
            candidates.append(urllib.parse.unquote(p, encoding="utf-8"))
        except Exception:
            pass
        try:
            candidates.append(urllib.parse.unquote(p, encoding="gbk"))
        except Exception:
            pass

        for c in list(candidates):
            if not c:
                continue
            c_norm = os.path.normpath(c)
            if os.path.exists(c_norm):
                return c_norm
            if not os.path.isabs(c_norm):
                abs_c = os.path.abspath(c_norm)
                if os.path.exists(abs_c):
                    return abs_c
            c_slash = c.replace("/", os.sep)
            if os.path.exists(c_slash):
                return c_slash
        return None

    async def _send_document_to_telegram(self, chat_id: Any, file_ref: str, display_name: Optional[str] = None):
        """
        使用 Telegram 官方 API (sendDocument) 上传/发送文件 (如 JM 下载的 PDF)
        遵循 50MB 官方限制，使用 multipart/form-data 传输。
        """
        if not chat_id or not file_ref:
            return

        url_doc = f"https://api.telegram.org/bot{self.token}/sendDocument"
        local_path = self._resolve_local_path(file_ref)

        async with httpx.AsyncClient(proxy=self.proxy, timeout=120.0) as client:
            try:
                if local_path and os.path.exists(local_path):
                    file_size = os.path.getsize(local_path)
                    filename = display_name or os.path.basename(local_path)

                    # 检查 Telegram Bot API 单文件大小限制 (50MB)
                    if file_size > 50 * 1024 * 1024:
                        size_mb = round(file_size / (1024 * 1024), 2)
                        warning_text = (
                            f"⚠️ 文件 [{filename}] 体积为 {size_mb}MB，"
                            f"超出 Telegram 官方 Bot API 单文件 50MB 上传限制。\n"
                            f"本地已保存至: {local_path}"
                        )
                        self.logger.tg_warning(f"[TelegramAdapter] {warning_text}")
                        url_msg = f"https://api.telegram.org/bot{self.token}/sendMessage"
                        await client.post(url_msg, json={"chat_id": chat_id, "text": warning_text})
                        return

                    self.logger.tg_info(f"[TelegramAdapter] 正在向 TG {chat_id} 上传文件: {filename} ({round(file_size / 1024, 1)} KB)")
                    with open(local_path, "rb") as f:
                        files = {"document": (filename, f.read(), "application/octet-stream")}
                        data = {"chat_id": chat_id}
                        resp = await client.post(url_doc, data=data, files=files)
                        if resp.status_code == 200 and resp.json().get("ok"):
                            doc_id = resp.json()["result"]["document"]["file_id"]
                            self.logger.tg_info(f"[TelegramAdapter] 文件已成功发送至 TG {chat_id}: {filename} (file_id: {doc_id})")
                        else:
                            self.logger.tg_warning(f"[TelegramAdapter] 发送文件失败: {resp.status_code} {resp.text}")

                elif str(file_ref).startswith("http://") or str(file_ref).startswith("https://"):
                    payload = {"chat_id": chat_id, "document": file_ref}
                    if display_name:
                        payload["caption"] = display_name
                    resp = await client.post(url_doc, json=payload)
                    if resp.status_code == 200 and resp.json().get("ok"):
                        self.logger.tg_info(f"[TelegramAdapter] 文件 URL 已发送至 TG {chat_id}: {file_ref}")
                    else:
                        self.logger.tg_warning(f"[TelegramAdapter] 发送文件 URL 失败: {resp.status_code} {resp.text}")
                else:
                    self.logger.tg_warning(f"[TelegramAdapter] 未找到待发送的本地或网络文件: {file_ref}")
            except Exception as e:
                self.logger.tg_error(f"[TelegramAdapter] 上传文件出错: {e}")

    async def _send_media_group(self, chat_id: Any, images: List[str], caption: str = ""):
        """
        通过 Telegram sendMediaGroup 将多张图片一次性发出（相册），避免刷屏。
        Telegram 官方限制 sendMediaGroup 每次 2~10 张媒体。
        若只有 1 张，退化为 sendPhoto。
        """
        if not images:
            return

        url_media = f"https://api.telegram.org/bot{self.token}/sendMediaGroup"
        url_photo = f"https://api.telegram.org/bot{self.token}/sendPhoto"

        if len(images) == 1:
            img = images[0]
            local_path = self._resolve_local_path(img)
            async with httpx.AsyncClient(proxy=self.proxy, timeout=60.0) as client:
                try:
                    payload = {"chat_id": chat_id}
                    if caption:
                        payload["caption"] = caption[:1024]
                    if local_path and os.path.exists(local_path):
                        ext = os.path.splitext(local_path)[1] or ".jpg"
                        with open(local_path, "rb") as f:
                            files = {"photo": (f"image{ext}", f.read())}
                            await client.post(url_photo, data=payload, files=files)
                    elif str(img).startswith("http://") or str(img).startswith("https://"):
                        payload["photo"] = img
                        await client.post(url_photo, json=payload)
                except Exception as e:
                    self.logger.tg_error(f"[TelegramAdapter] 单张图片发送失败: {e}")
            return

        chunk_size = 10
        for chunk_idx in range(0, len(images), chunk_size):
            chunk = images[chunk_idx:chunk_idx + chunk_size]
            media_list = []
            files_to_upload = {}

            for idx, img_ref in enumerate(chunk):
                attach_key = f"photo_{idx}"
                media_item = {
                    "type": "photo",
                    "media": f"attach://{attach_key}"
                }
                if chunk_idx == 0 and idx == 0 and caption:
                    media_item["caption"] = caption[:1024]

                local_path = self._resolve_local_path(img_ref)
                if local_path and os.path.exists(local_path):
                    with open(local_path, "rb") as f:
                        ext = os.path.splitext(local_path)[1] or ".jpg"
                        files_to_upload[attach_key] = (f"img_{idx}{ext}", f.read(), "image/jpeg")
                    media_list.append(media_item)
                elif str(img_ref).startswith("http://") or str(img_ref).startswith("https://"):
                    media_item["media"] = img_ref
                    media_list.append(media_item)

            if not media_list:
                continue

            async with httpx.AsyncClient(proxy=self.proxy, timeout=120.0) as client:
                try:
                    data = {
                        "chat_id": str(chat_id),
                        "media": json.dumps(media_list)
                    }
                    if files_to_upload:
                        resp = await client.post(url_media, data=data, files=files_to_upload)
                    else:
                        resp = await client.post(url_media, data=data)

                    if resp.status_code == 200 and resp.json().get("ok"):
                        self.logger.tg_info(f"[TelegramAdapter] 成功批量发送 {len(media_list)} 张图片 (MediaGroup) 至 TG {chat_id}")
                    else:
                        self.logger.tg_warning(f"[TelegramAdapter] sendMediaGroup 响应: {resp.status_code} {resp.text}")
                except Exception as e:
                    self.logger.tg_error(f"[TelegramAdapter] sendMediaGroup 出错: {e}")

    async def _send_forward_nodes_to_telegram(self, chat_id: Any, nodes: list):
        """
        将 OneBot 合并转发消息 (Node / send_group_forward_msg) 适配发送至 Telegram:
        1. 收集合并节点中的所有文本、图片与文件；
        2. 将节点内的所有图片通过官方 sendMediaGroup 一次性发成相册，避免一条一条发刷屏；
        3. 聚合文字在相册标题或统一发出；
        4. 包含文件 (如 JM 生成的 PDF) 则通过 sendDocument 上传。
        """
        if not chat_id or not nodes:
            return

        self.logger.tg_info(f"[TelegramAdapter] 准备向 TG {chat_id} 发送合并转发内容 (共 {len(nodes)} 个节点)...")

        all_images = []
        all_files = []
        text_blocks = []

        for idx, node in enumerate(nodes):
            sender_name = "Bot"
            content = None

            if isinstance(node, dict):
                data = node.get("data", {})
                sender_name = data.get("nickname") or node.get("nickname") or "Bot"
                content = data.get("content") or node.get("content")
            else:
                content = getattr(node, "content", None)
                sender_name = getattr(node, "nickname", "Bot")

            if content is None:
                continue

            node_texts = []
            if isinstance(content, str):
                node_texts.append(content)
            elif isinstance(content, list):
                for comp in content:
                    if isinstance(comp, dict):
                        ctype = comp.get("type")
                        cdata = comp.get("data", {})
                        if ctype == "text":
                            node_texts.append(cdata.get("text", ""))
                        elif ctype == "image":
                            img_f = cdata.get("file") or cdata.get("url")
                            if img_f:
                                all_images.append(str(img_f))
                        elif ctype == "file":
                            f_path = cdata.get("file") or cdata.get("path")
                            if f_path:
                                all_files.append((f_path, cdata.get("name")))
                    elif isinstance(comp, str):
                        node_texts.append(comp)
                    else:
                        comp_type = getattr(comp, "comp_type", "")
                        if comp_type == "text" or hasattr(comp, "text"):
                            node_texts.append(getattr(comp, "text", ""))
                        elif comp_type == "image" or hasattr(comp, "file"):
                            all_images.append(str(getattr(comp, "file", "")))
                        elif comp_type == "file":
                            all_files.append((str(getattr(comp, "file", "")), getattr(comp, "name", None)))

            combined_node_text = "".join(node_texts).strip()
            if combined_node_text:
                prefix = f"💬 [{sender_name}]" if sender_name != "Bot" else "🤖"
                text_blocks.append(f"{prefix} {combined_node_text}")

        # 发送文件 (如 JM 下载完成的 PDF 等)
        for f_path, f_name in all_files:
            await self._send_document_to_telegram(chat_id, f_path, f_name)

        summary_text = "\n\n".join(text_blocks).strip()

        # 如果有图片，使用 sendMediaGroup 一次性发全部图片，避免刷屏
        if all_images:
            await self._send_media_group(chat_id, all_images, caption=summary_text)
            if len(summary_text) > 1000:
                await self._send_to_telegram(chat_id, summary_text)
        elif summary_text:
            await self._send_to_telegram(chat_id, summary_text)

    async def _send_to_telegram(self, chat_id: Any, message: Any):
        """
        将 OneBot v11 消息转为 Telegram 官方 API 请求:
        支持 Text, Image, File (Document), Reply, Voice 多种格式组合。
        若含有多张图片，同样使用 sendMediaGroup 批量发送。
        """
        if not chat_id:
            return

        text_parts = []
        images = []
        voices = []
        files = []
        reply_to_tg_msg_id = None

        if isinstance(message, str):
            text_parts.append(message)
        elif isinstance(message, list):
            for item in message:
                if isinstance(item, dict):
                    mtype = item.get("type")
                    data = item.get("data", {})
                    if mtype == "text":
                        text_parts.append(data.get("text", ""))
                    elif mtype == "image":
                        img_path = data.get("file") or data.get("url")
                        if img_path:
                            images.append(str(img_path))
                    elif mtype in ("record", "voice"):
                        voice_path = data.get("file") or data.get("url")
                        if voice_path:
                            voices.append(str(voice_path))
                    elif mtype == "file":
                        f_path = data.get("file") or data.get("path")
                        if f_path:
                            files.append((str(f_path), data.get("name")))
                    elif mtype == "reply":
                        ob_msg_id = data.get("id")
                        if ob_msg_id and int(ob_msg_id) in self.msg_id_to_tg:
                            reply_to_tg_msg_id = self.msg_id_to_tg[int(ob_msg_id)].get("tg_message_id")
                    elif mtype == "node":
                        await self._send_forward_nodes_to_telegram(chat_id, [item])
                        return
                elif isinstance(item, str):
                    text_parts.append(item)

        url_msg = f"https://api.telegram.org/bot{self.token}/sendMessage"
        url_voice = f"https://api.telegram.org/bot{self.token}/sendVoice"

        async with httpx.AsyncClient(proxy=self.proxy, timeout=60.0) as client:
            try:
                full_text = "".join(text_parts).strip()

                # 1. 如果有多张图片，使用 sendMediaGroup 批量发送；如果只有1张，附带 caption 发送
                if images:
                    if len(images) > 1:
                        await self._send_media_group(chat_id, images, caption=full_text if len(full_text) <= 1000 else "")
                        if len(full_text) > 1000:
                            msg_payload = {"chat_id": chat_id, "text": full_text}
                            if reply_to_tg_msg_id:
                                msg_payload["reply_parameters"] = json.dumps({"message_id": reply_to_tg_msg_id})
                            await client.post(url_msg, json=msg_payload)
                        full_text = ""
                    else:
                        img = images[0]
                        url_photo = f"https://api.telegram.org/bot{self.token}/sendPhoto"
                        photo_payload = {"chat_id": chat_id}
                        if reply_to_tg_msg_id:
                            photo_payload["reply_parameters"] = json.dumps({"message_id": reply_to_tg_msg_id})
                        if full_text and len(full_text) <= 1000:
                            photo_payload["caption"] = full_text
                            full_text = ""

                        local_file = self._resolve_local_path(img)
                        if img.startswith("http://") or img.startswith("https://"):
                            photo_payload["photo"] = img
                            resp = await client.post(url_photo, json=photo_payload)
                            if resp.status_code == 200:
                                self.logger.tg_info(f"[TelegramAdapter] 图片已成功发送至 TG {chat_id}")
                            else:
                                self.logger.tg_warning(f"[TelegramAdapter] 发送图片 URL 失败: {resp.status_code} {resp.text}")
                        elif local_file:
                            ext = os.path.splitext(local_file)[1] or ".jpg"
                            filename = f"image{ext}"
                            with open(local_file, "rb") as f:
                                upload_files = {"photo": (filename, f.read())}
                                resp = await client.post(url_photo, data=photo_payload, files=upload_files)
                                if resp.status_code == 200:
                                    self.logger.tg_info(f"[TelegramAdapter] 本地图片已成功发送至 TG {chat_id}")
                                elif resp.status_code == 400 and ("IMAGE_PROCESS_FAILED" in resp.text or "wrong file identifier" in resp.text):
                                    url_doc = f"https://api.telegram.org/bot{self.token}/sendDocument"
                                    f.seek(0)
                                    doc_files = {"document": (filename, f.read())}
                                    resp_doc = await client.post(url_doc, data=photo_payload, files=doc_files)
                                    if resp_doc.status_code == 200:
                                        self.logger.tg_info(f"[TelegramAdapter] 图片以文件形式成功发送至 TG {chat_id}")
                                    else:
                                        self.logger.tg_warning(f"[TelegramAdapter] 图片以文件发送失败: {resp_doc.status_code} {resp_doc.text}")
                                else:
                                    self.logger.tg_warning(f"[TelegramAdapter] 发送本地图片失败: {resp.status_code} {resp.text}")
                        else:
                            self.logger.tg_warning(f"[TelegramAdapter] 未找到本地图片文件: {img}")

                # 2. 发送文件 (File / Document)
                for f_path, f_name in files:
                    await self._send_document_to_telegram(chat_id, f_path, f_name)

                # 3. 发送语音
                for v in voices:
                    voice_payload = {"chat_id": chat_id}
                    if reply_to_tg_msg_id:
                        voice_payload["reply_parameters"] = json.dumps({"message_id": reply_to_tg_msg_id})
                    local_v = self._resolve_local_path(v)
                    if local_v:
                        with open(local_v, "rb") as f:
                            upload_voices = {"voice": ("voice.mp3", f.read())}
                            await client.post(url_voice, data=voice_payload, files=upload_voices)
                    elif v.startswith("http://") or v.startswith("https://"):
                        voice_payload["voice"] = v
                        await client.post(url_voice, json=voice_payload)

                # 4. 发送剩余文本
                if full_text:
                    max_len = 4000
                    for i in range(0, len(full_text), max_len):
                        chunk = full_text[i:i + max_len]
                        msg_payload = {
                            "chat_id": chat_id,
                            "text": chunk
                        }
                        if reply_to_tg_msg_id:
                            msg_payload["reply_parameters"] = json.dumps({"message_id": reply_to_tg_msg_id})
                        resp = await client.post(url_msg, json=msg_payload)
                        if resp.status_code == 200:
                            res_json = resp.json()
                            if res_json.get("ok"):
                                sent_id = res_json["result"]["message_id"]
                                self.logger.tg_info(f"[TelegramAdapter] 文本消息已发送至 TG {chat_id}, msg_id: {sent_id}")
                        else:
                            self.logger.tg_warning(f"[TelegramAdapter] 发送文本失败: {resp.status_code} {resp.text}")
            except Exception as e:
                self.logger.tg_error(f"[TelegramAdapter] 调用 Telegram 官方 API 出错: {e}")

    async def _poll_telegram_updates(self):
        """
        通过 Telegram 官方长轮询 getUpdates 获取消息
        使用 allowed_updates 涵盖所有消息类型
        """
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        allowed = json.dumps(["message", "edited_message", "channel_post", "edited_channel_post", "callback_query"])

        while self.is_running:
            try:
                params = {
                    "offset": self.tg_offset,
                    "timeout": 20,
                    "allowed_updates": allowed
                }
                async with httpx.AsyncClient(proxy=self.proxy, timeout=35.0) as client:
                    resp = await client.get(url, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("ok"):
                            updates = data.get("result", [])
                            for update in updates:
                                self.tg_offset = update["update_id"] + 1
                                self.logger.tg_info(f"[TelegramAdapter] 收到 Telegram 更新 (update_id={update.get('update_id')})")
                                await self._handle_telegram_message(update)
                    elif resp.status_code == 409:
                        self.logger.tg_warning(f"[TelegramAdapter] getUpdates HTTP 409 Conflict: 冲突检测，等待5秒后重试...")
                        await asyncio.sleep(5)
                    else:
                        self.logger.tg_warning(f"[TelegramAdapter] getUpdates HTTP {resp.status_code}: {resp.text}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.tg_error(f"[TelegramAdapter] 轮询异常: {e}")
                await asyncio.sleep(2)
            await asyncio.sleep(0.3)

    async def _handle_telegram_message(self, update: dict):
        """
        将 Telegram 消息转换为标准 OneBot v11 事件
        参考 Tele-KiraLink 处理逻辑：
        - 移除 @username 并转换为 OneBot At(self_id) 实体
        - 转换图片与文本
        - 统一转成以 11111 为前缀的数字 group_id
        """
        msg = update.get("message") or update.get("channel_post")
        if not msg:
            return

        chat = msg.get("chat", {})
        chat_id = chat.get("id")
        tg_msg_id = msg.get("message_id")
        chat_type = chat.get("type", "group")  # private, group, supergroup, channel
        from_user = msg.get("from", {})
        sender_id = from_user.get("id", chat_id)
        nickname = (from_user.get("first_name", "") + " " + from_user.get("last_name", "")).strip()
        if not nickname:
            nickname = chat.get("title", f"TG_{sender_id}")

        text = msg.get("text", "") or msg.get("caption", "")

        # 计算未绑定时的独立唯一虚拟 user_id (使用 sender_id，绝不共享他人记忆)
        clean_sid = str(abs(int(sender_id)))
        fallback_virtual_uid = int("11111" + clean_sid[:10])

        # 用户身份绑定: /bind <qq_id>
        if text.startswith("/bind"):
            parts = text.split()
            if len(parts) > 1 and parts[1].isdigit():
                bound_qq = int(parts[1])
                self.tg_user_bindings[str(sender_id)] = bound_qq
                self._save_bindings()
                await self._send_to_telegram(chat_id, f"✅ 成功绑定 QQ 账号: {bound_qq}！现在所有功能将共享该 QQ 的上下文与记忆。")
                return
            elif len(parts) == 1:
                cur_qq = self.tg_user_bindings.get(str(sender_id))
                if cur_qq:
                    await self._send_to_telegram(chat_id, f"当前绑定的 QQ 账号为: {cur_qq}\n发送 /bind <QQ号> 可随时切换绑定。")
                else:
                    await self._send_to_telegram(chat_id, f"当前未绑定任何 QQ 账号 (临时独立身份ID: {fallback_virtual_uid})。\n发送 /bind <你的QQ号> 即可共享你的 QQ 上下文与记忆。")
                return

        virtual_group_id = self.encode_to_virtual_group_id(chat_id)
        user_id = self.tg_user_bindings.get(str(sender_id), fallback_virtual_uid)

        # 构建 OneBot 消息段
        onebot_messages: List[Dict[str, Any]] = []

        # 1. 引用回复 (Reply)
        reply_to = msg.get("reply_to_message")
        if reply_to:
            rep_id = reply_to.get("message_id")
            onebot_messages.append({"type": "reply", "data": {"id": rep_id}})

        # 2. 检查是否 @ 了 Bot 自身
        is_mentioned = False
        clean_text = text
        if self.bot_username:
            at_tag = f"@{self.bot_username}"
            if at_tag.lower() in text.lower():
                is_mentioned = True
                clean_text = text.replace(at_tag, "").strip()

        # 频道 post、私聊或者显式 @ Bot 时添加 OneBot At，以便触发 Bot 逻辑
        if chat_type != "private":
            if is_mentioned or text.startswith("/") or chat_type == "channel":
                onebot_messages.append({"type": "at", "data": {"qq": self.bot_id}})

        # 3. 接收图片
        if "photo" in msg:
            photo = msg["photo"][-1]
            local_img = await self._download_file(photo["file_id"])
            if local_img:
                onebot_messages.append({"type": "image", "data": {"file": f"file:///{os.path.abspath(local_img)}"}})

        # 4. 文本内容
        if clean_text:
            onebot_messages.append({"type": "text", "data": {"text": clean_text}})

        if not onebot_messages:
            return

        now_ms = int(time.time() * 1000)
        # 记录 OneBot message_id 与 TG message_id 映射
        self.msg_id_to_tg[now_ms] = {
            "tg_message_id": tg_msg_id,
            "chat_id": chat_id
        }

        # 组装标准 OneBot v11 GroupMessageEvent
        onebot_event = {
            "self_id": self.bot_id,
            "user_id": user_id,
            "time": int(time.time()),
            "message_id": now_ms,
            "real_id": tg_msg_id if tg_msg_id else (now_ms % 2147483647),
            "message_seq": now_ms % 2147483647,
            "message_type": "group",
            "sender": {
                "user_id": user_id,
                "nickname": nickname,
                "card": "",
                "role": "admin" if (user_id == self.default_qq_id) else "member",
                "title": "Telegram"
            },
            "raw_message": clean_text,
            "font": 14,
            "sub_type": "normal",
            "message": onebot_messages,
            "message_format": "array",
            "post_type": "message",
            "group_id": virtual_group_id,
            "adapter_source": "telegram"
        }

        # 通过 WebSocket 注入 Hub
        if self.ws:
            event_json = json.dumps(onebot_event, ensure_ascii=False)
            await self.ws.send(event_json)
            self.logger.tg_info(
                f"[TelegramAdapter] 转发 TG 消息至 Hub -> 虚拟群: {virtual_group_id} (原TG: {chat_id}, 类型: {chat_type}), 内容: '{clean_text}'"
            )

    async def _download_file(self, file_id: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient(proxy=self.proxy, timeout=20.0) as client:
                r = await client.get(f"https://api.telegram.org/bot{self.token}/getFile", params={"file_id": file_id})
                if r.status_code == 200 and r.json().get("ok"):
                    file_path = r.json()["result"]["file_path"]
                    dl_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
                    res = await client.get(dl_url)
                    os.makedirs("data/pictures/tg_recv", exist_ok=True)
                    local_path = os.path.join("data/pictures/tg_recv", f"{file_id}.jpg")
                    with open(local_path, "wb") as f:
                        f.write(res.content)
                    return local_path
        except Exception as e:
            self.logger.tg_error(f"[TelegramAdapter] 下载 Telegram 图片异常: {e}")
        return None
