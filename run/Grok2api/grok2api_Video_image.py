# -*- coding: utf-8 -*-
import os
import asyncio
import aiohttp
import re
import uuid
import json
import base64
import logging
from datetime import date
from typing import Dict, Optional, Tuple, Any

from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import Image, Text, File
from framework_common.ToolKits.logger import get_logger
from framework_common.database_util.User import get_user
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
config=YAMLManager.get_instance()
logger = get_logger("grok2api")

# ================= 配置区域 =================
class Config:
    # 临时文件存储路径
    TEMP_DIR_VIDEO = config.Grok2api.config["TEMP_DIR_VIDEO"]

    # 临时文件存储路径
    TEMP_DIR_IMAGE =config.Grok2api.config["TEMP_DIR_IMAGE"]

    # 配额数据存储路径
    QUOTA_FILE = "grok_video_quota.json"

    # 【必需】服务端地址（一般默认即可，实际情况需根据端口号而定）
    BASE_URL = config.Grok2api.config["BASE_URL"]
    API_URL_VIDEO = f"{BASE_URL}/v1/chat/completions"
    API_URL_IMAGE = f"{BASE_URL}/v1/images/generations"

    # 【必需】API Key（去这里创建API：https://console.x.ai/team/473d5d36-c88f-402a-97a4-14c1f2e52d9a/api-keys/create）
    API_KEY = config.Grok2api.config["API_KEY"]

    # 【必须】视频模型以及图像模型，保持默认即可
    MODEL_VIDEO = config.Grok2api.config["MODEL_VIDEO"]
    MODEL_IMAGE = config.Grok2api.config["MODEL_IMAGE"]

    # 限制设置
    DAILY_LIMIT = config.Grok2api.config["DAILY_LIMIT"]        # 每日每人免费限制次数
    PERMISSION_NEED=config.Grok2api.config["PERMISSION_NEED"]
    CONCURRENT_LIMIT = config.Grok2api.config["CONCURRENT_LIMIT"]    # 单人同时运行的任务限制
    TIMEOUT = config.Grok2api.config["TIMEOUT"]           # 请求超时时间 (秒)
    ADMIN_QQ = config.common_config.basic_config["master"]["id"]  # 管理员QQ号

os.makedirs(Config.TEMP_DIR_VIDEO, exist_ok=True)
os.makedirs(Config.TEMP_DIR_IMAGE, exist_ok=True)

# ================= 配额管理器 =================
class QuotaManager:
    def __init__(self):
        self.file_path = Config.QUOTA_FILE
        self.active_tasks: Dict[str, int] = {}

    def _load_from_disk(self) -> Dict:
        if not os.path.exists(self.file_path):
            return {}
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取数据库失败: {e}")
            return {}

    def _save_to_disk(self, data: Dict):
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"写入数据库失败: {e}")

    def _get_and_refresh_user(self, all_data: Dict, user_id: str) -> Dict:
        today_str = str(date.today())
        user_data = all_data.get(user_id, {"date": today_str, "daily_usage": 0, "extra_quota": 0})

        # 次日刷新逻辑，如果日期不对，重置数据
        if user_data.get("date") != today_str:
            user_data["date"] = today_str
            user_data["daily_usage"] = 0
            user_data["extra_quota"] = 0
            all_data[user_id] = user_data
        return user_data

    def get_remaining_count(self, user_id: int) -> int:
        """实时查询剩余次数"""
        all_data = self._load_from_disk()
        u = self._get_and_refresh_user(all_data, str(user_id))
        return max(0, Config.DAILY_LIMIT - u["daily_usage"]) + u["extra_quota"]

    def deduct_quota(self, user_id: int) -> bool:
        """实时扣除次数"""
        all_data = self._load_from_disk()
        uid_str = str(user_id)
        u = self._get_and_refresh_user(all_data, uid_str)

        success = False
        if u["daily_usage"] < Config.DAILY_LIMIT:
            u["daily_usage"] += 1
            success = True
        elif u["extra_quota"] > 0:
            u["extra_quota"] -= 1
            success = True

        if success:
            all_data[uid_str] = u
            self._save_to_disk(all_data)
        return success

    def refund_quota(self, user_id: int):
        """实时返还次数"""
        all_data = self._load_from_disk()
        uid_str = str(user_id)
        u = self._get_and_refresh_user(all_data, uid_str)

        if u["daily_usage"] > 0:
            u["daily_usage"] -= 1
        else:
            u["extra_quota"] += 1

        all_data[uid_str] = u
        self._save_to_disk(all_data)

    def add_extra_quota(self, user_id: str, amount: int):
        """管理员增加额外次数"""
        all_data = self._load_from_disk()
        u = self._get_and_refresh_user(all_data, user_id)
        u["extra_quota"] += amount
        all_data[user_id] = u
        self._save_to_disk(all_data)

    def check_concurrent(self, user_id: int) -> bool:
        return self.active_tasks.get(str(user_id), 0) < Config.CONCURRENT_LIMIT
    def add_active_task(self, user_id: int):
        uid = str(user_id)
        self.active_tasks[uid] = self.active_tasks.get(uid, 0) + 1
    def remove_active_task(self, user_id: int):
        uid = str(user_id)
        if uid in self.active_tasks: self.active_tasks[uid] = max(0, self.active_tasks[uid] - 1)

quota_manager = QuotaManager()

# ================= LLM 提示优化 =================
async def auto_optimize_prompt(bot: ExtendBot, config: YAMLManager, user_id: int, original_prompt: str) -> str:
    error_keywords = [
        "Maximum recursion depth exceeded",
        "Please try again later",
        "quota exhausted",
        "rate limit",
        "rate limited",
        "429",
        "error",
        "Error",
        "ERROR",
        "fail",
        "Fail",
        "FAIL",
        "exception",
        "Exception"
    ]

    # 重试次数
    max_retries = 1

    for attempt in range(max_retries):
        try:
            try:
                from run.ai_llm.service.aiReplyCore import aiReplyCore
            except ImportError:
                logger.warning("提示词优化失败，将使用原始提示")
                return original_prompt

            # 构造优化消息
            messages = [
                {
                    "text": f"请优化以下AI生成提示词，使其更详细、清晰、具体，易于AI图像/视频生成模型理解，但必须严格保留用户的原始意图，不能添加无关的元素或风格。只返回优化后的提示词，不要任何解释或额外文字。原始提示：{original_prompt}"
                }
            ]

            # 进行提示优化
            optimized_prompt = await aiReplyCore(
                messages,
                user_id,
                config,
                bot=bot,
                tools=None,
                system_instruction="你是一个提示词优化助手，专门优化AI生成提示词。用户会给你一个可能比较简单或抽象的描述,你需要将其转化为详细、具体、适合AI生成的提示词，但要严格保持用户原始意图不变。"
            )

            if not optimized_prompt or not optimized_prompt.strip():
                logger.warning(f"优化返回空，使用原始提示")
                return original_prompt

            optimized_prompt = optimized_prompt.strip()

            # 检查是否包含错误信息
            is_error_response = False
            for error_keyword in error_keywords:
                if error_keyword in optimized_prompt:
                    is_error_response = True
                    logger.warning(f"优化返回包含错误信息'{error_keyword}'，使用原始提示词")
                    break

            if is_error_response:
                return original_prompt

            # 清理可能的额外文本
            optimized_prompt = optimized_prompt.replace('"', '').replace("'", "")
            if optimized_prompt.startswith("优化后的提示："):
                optimized_prompt = optimized_prompt[6:].strip()
            if optimized_prompt.startswith("提示："):
                optimized_prompt = optimized_prompt[3:].strip()

            # 验证优化结果是否有效
            if (len(optimized_prompt) > 3 and
                optimized_prompt != original_prompt and
                len(optimized_prompt) < 500):  # 防止过长

                logger.info(f"用户 {user_id} 提示词优化成功: {original_prompt} -> {optimized_prompt}")
                return optimized_prompt
            else:
                logger.debug(f"优化结果无效或与原提示相同，使用原始提示")
                return original_prompt

        except Exception as e:
            logger.warning(f"优化尝试出错: {e}，使用原始提示")
            return original_prompt

    # 如果循环结束，返回原始提示词
    return original_prompt

# ================= 核心 API 逻辑 =================
async def call_grok_video_api(image_url: str, prompt: str) -> Tuple[str, str]:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {Config.API_KEY}"}
    payload = {
        "model": Config.MODEL_VIDEO,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": image_url}}]}],
        "stream": False
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(Config.API_URL_VIDEO, json=payload, headers=headers, timeout=Config.TIMEOUT) as resp:
                if resp.status != 200: return "error", f"API响应错误 {resp.status}"
                result = await resp.json()
                content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                # 解析 URL 或 路径
                http_match = re.search(r'(https?://[^\s"\'><\)]+\.mp4)', content)
                if http_match: return "url", http_match.group(1)
                path_match = re.search(r'(users/[^\s"\'><\)]+\.mp4)', content)
                if path_match: return "url", f"{Config.BASE_URL}/files/{path_match.group(1)}"
                return "error", "无法从回复中解析视频链接"
    except Exception as e: return "error", f"网络异常: {str(e)}"

async def call_grok_image_api(prompt: str) -> Tuple[str, str]:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {Config.API_KEY}"}
    payload = {"model": Config.MODEL_IMAGE, "prompt": prompt, "n": 1}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(Config.API_URL_IMAGE, json=payload, headers=headers, timeout=Config.TIMEOUT) as resp:
                if resp.status != 200: return "error", f"API响应错误 {resp.status}"
                result = await resp.json()
                data_list = result.get("data", [])
                if not data_list: return "error", "未返回有效数据"
                item = data_list[0]
                if "b64_json" in item:
                    path = os.path.join(Config.TEMP_DIR_IMAGE, f"{uuid.uuid4().hex}.jpg")
                    b64_str = item["b64_json"].split(",")[1] if "," in item["b64_json"] else item["b64_json"]
                    with open(path, "wb") as f: f.write(base64.b64decode(b64_str))
                    return "path", path
                img_url = item.get("url", "")
                if not img_url.startswith("http"): img_url = f"{Config.BASE_URL}/v1/files/{img_url.lstrip('/')}"
                return "url", img_url
    except Exception as e: return "error", f"请求异常: {str(e)}"

async def download_resource(url: str, is_video: bool) -> Optional[str]:
    folder = Config.TEMP_DIR_VIDEO if is_video else Config.TEMP_DIR_IMAGE
    ext = ".mp4" if is_video else ".jpg"
    path = os.path.join(folder, f"{uuid.uuid4().hex}{ext}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=180) as resp:
                if resp.status == 200:
                    with open(path, "wb") as f: f.write(await resp.read())
                    return path
    except: pass
    return None

# ================= 任务执行流程 =================
async def handle_video_generation(bot, event, img_url, prompt):
    uid = event.user_id
    if not quota_manager.deduct_quota(uid):
        return await bot.send(event, Text("今日生成次数已用完。"))

    quota_manager.add_active_task(uid)
    local_path = None
    try:
        await bot.send(event, Text("正在调用Grok生成视频，请耐心等待1-2分钟..."))
        # 在调用Grok API前，先优化提示词
        optimized_prompt = await auto_optimize_prompt(bot, bot.config, uid, prompt)

        # 如果优化后的提示词包含错误信息，使用原始提示词
        error_keywords = ["Maximum recursion depth exceeded", "Please try again later", "quota exhausted"]
        for keyword in error_keywords:
            if keyword in optimized_prompt:
                logger.warning(f"检测到优化提示包含错误信息 '{keyword}'，使用原始提示")
                optimized_prompt = prompt
                break

        logger.info(f"用户 {uid} 视频生成使用提示: {optimized_prompt}")

        res_type, res_content = await call_grok_video_api(img_url, optimized_prompt)
        if res_type == "error":
            quota_manager.refund_quota(uid)
            await bot.send(event, Text(f"视频生成失败: {res_content}"))
        else:
            local_path = await download_resource(res_content, True)
            if local_path:
                await bot.send(event, File(file=local_path))
                await bot.send(event, Text(f"视频生成成功！今日剩余总次数：{quota_manager.get_remaining_count(uid)}"))
            else:
                quota_manager.refund_quota(uid)
                await bot.send(event, Text("视频下载失败，已退还次数。"))
    finally:
        quota_manager.remove_active_task(uid)
        if local_path and os.path.exists(local_path):
            await asyncio.sleep(60); os.remove(local_path)

async def handle_image_generation(bot, event, prompt):
    uid = event.user_id
    if not quota_manager.deduct_quota(uid):
        return await bot.send(event, Text("今日生成次数已用完。"))

    quota_manager.add_active_task(uid)
    local_path = None
    try:
        await bot.send(event, Text("正在调用Grok生成图像，请耐心等待1-2分钟..."))
        # 在调用Grok API前，先优化提示词
        optimized_prompt = await auto_optimize_prompt(bot, bot.config, uid, prompt)

        # 如果优化后的提示词包含错误信息，使用原始提示词
        error_keywords = ["Maximum recursion depth exceeded", "Please try again later", "quota exhausted"]
        for keyword in error_keywords:
            if keyword in optimized_prompt:
                logger.warning(f"检测到优化提示包含错误信息 '{keyword}'，使用原始提示")
                optimized_prompt = prompt
                break

        logger.info(f"用户 {uid} 图像生成使用提示: {optimized_prompt}")

        res_type, res_content = await call_grok_image_api(optimized_prompt)
        if res_type == "error":
            quota_manager.refund_quota(uid)
            await bot.send(event, Text(f"画图失败: {res_content}"))
        else:
            local_path = res_content if res_type == "path" else await download_resource(res_content, False)
            if local_path:
                await bot.send(event, Image(file=local_path))
                await bot.send(event, Text(f"图像生成成功！今日剩余总次数：{quota_manager.get_remaining_count(uid)}"))
            else:
                quota_manager.refund_quota(uid)
                await bot.send(event, Text("图像保存失败，已退还次数。"))
    finally:
        quota_manager.remove_active_task(uid)
        if local_path and os.path.exists(local_path):
            await asyncio.sleep(60); os.remove(local_path)

# ================= 会话管理 =================
class SessionManager:
    def __init__(self): self.sessions = {}
    def set(self, uid, step, extra=None): self.sessions[uid] = {"step": step, "extra": extra}
    def get(self, uid): return self.sessions.get(uid, {})
    def clear(self, uid): self.sessions.pop(uid, None)

session_mgr = SessionManager()

def main(bot: ExtendBot, config: YAMLManager):
    @bot.on(GroupMessageEvent)
    async def _(event: GroupMessageEvent):
        uid = event.user_id
        text = event.pure_text.strip() if event.pure_text else ""

        # 管理员加次数指令
        if uid == Config.ADMIN_QQ and text.startswith("/"):
            admin_match = re.match(r'^/(\d+)\+(\d+)$', text)
            if admin_match:
                target_uid, count = admin_match.group(1), int(admin_match.group(2))
                quota_manager.add_extra_quota(target_uid, count)
                await bot.send(event, Text(f"成功为 {target_uid} 增加 {count} 次额度。\n当前剩余总次数：{quota_manager.get_remaining_count(int(target_uid))}"))
                return
        if text.startswith("/grok"):
            user_info = await get_user(event.user_id, event.sender.nickname)
            if not user_info.permission >= config.Grok2api.config["PERMISSION_NEED"]:
                await bot.send(event, "你没有足够的权限使用该功能哦~")
                return
        # 取消操作
        if text in ["/grok取消", "/grok【取消】", "/grok cancel"]:
            if session_mgr.get(uid):
                session_mgr.clear(uid)
                await bot.send(event, Text("操作已取消。"))
            return

        # 视频指令
        elif text == "/grok视频":
            if not quota_manager.check_concurrent(uid): return await bot.send(event, "您当前已有任务正在运行。")
            if quota_manager.get_remaining_count(uid) <= 0: return await bot.send(event, Text("今日生成次数已用完。"))
            session_mgr.set(uid, "v_waiting_img")
            await bot.send(event, Text("请发送一张图片，或发送【取消】以终止任务。"))
            return

        elif text == "/grok图片":
            if not quota_manager.check_concurrent(uid): return await bot.send(event, Text("您当前已有任务正在运行。"))
            if quota_manager.get_remaining_count(uid) <= 0: return await bot.send(event, Text("今日生成次数已用完。"))
            session_mgr.set(uid, "i_waiting_prompt")
            await bot.send(event, Text("请发送生成图片的提示词，或发送【取消】以终止任务。"))
            return

        # 状态机逻辑
        state = session_mgr.get(uid)
        if not state: return

        if state["step"] == "v_waiting_img":
            url = None
            if isinstance(event.message, list):
                for m in event.message:
                    url = getattr(m, 'url', None) or (m.get('data', {}).get('url') if isinstance(m, dict) else None)
                    if url: break
            if url:
                session_mgr.set(uid, "v_waiting_prompt", url)
                await bot.send(event, Text("请发送提示词（如：让她的头发动起来。）"))
            return

        if state["step"] == "v_waiting_prompt" and text:
            img_url = state["extra"]
            session_mgr.clear(uid)
            asyncio.create_task(handle_video_generation(bot, event, img_url, text))
            return

        if state["step"] == "i_waiting_prompt" and text:
            session_mgr.clear(uid)
            asyncio.create_task(handle_image_generation(bot, event, text))
            return
