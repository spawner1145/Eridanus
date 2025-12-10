# -*- coding: utf-8 -*-
import os
import asyncio
import aiohttp
import re
import uuid
import json
import base64
import logging
from datetime import datetime, date
from typing import Dict, Optional, Tuple, Any

from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import Image, Text, File
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================= 配置区域 =================
class Config:
    # 临时文件存储路径
    TEMP_DIR = "grok_video_temp"

    # 配额数据存储路径
    QUOTA_FILE = "grok_video_quota.json"
    
    # 【必需】服务端地址（一般默认即可，实际情况需根据端口号而定）
    API_URL = "http://127.0.0.1:8001/v1/chat/completions"
    
    # 【必需】API Key（去这里申请你的GrokAPI：https://console.x.ai/team/473d5d36-c88f-402a-97a4-14c1f2e52d9a/api-keys）
    API_KEY = "xai-XXXXXXXXXXXXXXXXXXXX" 

    # 限制设置
    DAILY_LIMIT = 20        # 每日每人免费限制次数
    CONCURRENT_LIMIT = 1    # 单人同时运行的任务限制
    TIMEOUT = 300           # 请求超时时间 (秒)
    
    # 管理员 QQ 号
    ADMIN_QQ = 2702495766

    # /视频（触发指令）
    # /QQ号+次数（为指定用户增加额外次数，如：/123456+10，需要管理员才可以使用）
    # 取消、退出、/cancel（取消当前任务）

# 初始化目录
os.makedirs(Config.TEMP_DIR, exist_ok=True)

# ================= 配额与限制管理 =================
class QuotaManager:
    def __init__(self):
        self.file_path = Config.QUOTA_FILE
        self.data = self._load_data()
        self.active_tasks: Dict[str, int] = {} # 内存中记录并发任务数

    def _load_data(self) -> Dict:
        """加载本地配额数据"""
        if not os.path.exists(self.file_path):
            return {}
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}

    def _save_data(self):
        """保存配额数据到本地"""
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存配额数据失败: {e}")

    def _get_user_data(self, user_id: str) -> Dict:
        """获取并刷新用户数据"""
        today_str = str(date.today())
        user_data = self.data.get(user_id, {
            "date": today_str,
            "daily_usage": 0,  # 今日已用免费额度
            "extra_quota": 0   # 管理员增加的额外额度（永久，直到用完）
        })
        
        # 跨天重置：只重置 daily_usage，保留 extra_quota
        if user_data.get("date") != today_str:
            user_data["date"] = today_str
            user_data["daily_usage"] = 0
            # extra_quota 保持不变
            self.data[user_id] = user_data
            self._save_data()
            
        return user_data

    def get_remaining_count(self, user_id: int) -> int:
        """获取用户剩余总次数"""
        uid = str(user_id)
        user_data = self._get_user_data(uid)
        
        daily_left = max(0, Config.DAILY_LIMIT - user_data["daily_usage"])
        total_left = daily_left + user_data["extra_quota"]
        return total_left

    def deduct_quota(self, user_id: int) -> bool:
        """尝试扣除一次配额。优先扣除每日免费，再扣除额外额度。"""
        uid = str(user_id)
        user_data = self._get_user_data(uid)
        
        # 1. 尝试扣除每日额度
        if user_data["daily_usage"] < Config.DAILY_LIMIT:
            user_data["daily_usage"] += 1
            self.data[uid] = user_data
            self._save_data()
            logger.info(f"用户 {uid} 扣除每日额度。今日已用: {user_data['daily_usage']}/{Config.DAILY_LIMIT}")
            return True
            
        # 2. 尝试扣除额外额度
        if user_data["extra_quota"] > 0:
            user_data["extra_quota"] -= 1
            self.data[uid] = user_data
            self._save_data()
            logger.info(f"用户 {uid} 扣除额外额度。剩余额外: {user_data['extra_quota']}")
            return True
            
        return False

    def refund_quota(self, user_id: int):
        """退还一次配额（用于任务失败）"""
        uid = str(user_id)
        user_data = self._get_user_data(uid)
        
        if user_data["daily_usage"] > 0:
            user_data["daily_usage"] = max(0, user_data["daily_usage"] - 1)
        else:
            # 退还到额外额度
            user_data["extra_quota"] += 1
            
        self.data[uid] = user_data
        self._save_data()
        logger.info(f"用户 {uid} 配额已退还。")

    def admin_add_quota(self, target_uid: str, count: int) -> int:
        """管理员增加额外额度"""
        user_data = self._get_user_data(target_uid)
        user_data["extra_quota"] += count
        self.data[target_uid] = user_data
        self._save_data()
        
        # 计算当前总剩余
        return self.get_remaining_count(int(target_uid))

    def check_concurrent(self, user_id: int) -> bool:
        uid = str(user_id)
        current = self.active_tasks.get(uid, 0)
        return current < Config.CONCURRENT_LIMIT

    def add_active_task(self, user_id: int):
        uid = str(user_id)
        self.active_tasks[uid] = self.active_tasks.get(uid, 0) + 1

    def remove_active_task(self, user_id: int):
        uid = str(user_id)
        if uid in self.active_tasks:
            self.active_tasks[uid] = max(0, self.active_tasks[uid] - 1)

quota_manager = QuotaManager()

# ================= 工具函数 =================
def extract_first_image_url(event: GroupMessageEvent) -> Optional[str]:
    """提取第一张图片的链接"""
    try:
        if hasattr(event, "message") and isinstance(event.message, list):
            for msg in event.message:
                if hasattr(msg, "url") and msg.url: return str(msg.url)
                if hasattr(msg, "file") and msg.file and str(msg.file).startswith("http"): return str(msg.file)
                if isinstance(msg, dict):
                    url = msg.get("url") or msg.get("data", {}).get("url") or msg.get("file")
                    if url and str(url).startswith("http"): return str(url)
                if isinstance(msg, Image):
                    return getattr(msg, 'url', getattr(msg, 'file', None))

        if hasattr(event, "raw_message") and event.raw_message:
            match = re.search(r'(?:file|url)=(https?://[^,\]"\']+)', event.raw_message)
            if match: return match.group(1)
            url_match = re.search(r'(https?://[^\s]+(?:jpg|png|jpeg|gif|bmp)[\w\-\=&]*)', event.raw_message)
            if url_match: return url_match.group(1)
    except Exception as e:
        logger.error(f"提取图片链接异常: {e}")
    return None

def save_base64_video(base64_str: str) -> Optional[str]:
    """Base64 转文件"""
    try:
        if "base64," in base64_str:
            base64_str = base64_str.split("base64,")[1]
        base64_str = base64_str.strip()
        
        file_name = f"{uuid.uuid4().hex}.mp4"
        save_path = os.path.join(Config.TEMP_DIR, file_name)
        
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(base64_str))
        return save_path
    except Exception as e:
        logger.error(f"Base64 保存失败: {e}")
        return None

# ================= 核心 API 逻辑 =================
async def call_grok_video_api(image_url: str, prompt: str) -> Tuple[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {Config.API_KEY}"
    }
    
    payload = {
        "model": "grok-imagine-0.9",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            }
        ],
        "stream": False 
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(Config.API_URL, json=payload, headers=headers, timeout=Config.TIMEOUT) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return "error", f"API错误 {resp.status}: {text}"
                
                result_json = await resp.json()
                try:
                    choices = result_json.get('choices', [])
                    if not choices: return "error", "API返回空数据"
                    
                    content = choices[0]['message']['content']
                    
                    match = re.search(r'src=["\']([^"\']+)["\']', content)
                    if match:
                        src = match.group(1)
                        if src.startswith("data:"): return "base64", src
                        if src.startswith("http"): return "url", src
                        if src.startswith("/"): 
                            base = Config.API_URL.split("/v1")[0]
                            return "url", f"{base}{src}"
                    
                    if content.startswith("http"): return "url", content
                    return "error", "无法解析视频地址"
                except Exception as e:
                    return "error", f"解析异常: {e}"
    except asyncio.TimeoutError:
        return "error", "生成超时，请稍后重试"
    except Exception as e:
        return "error", f"网络错误: {e}"

async def process_download(res_type: str, res_content: str) -> Optional[str]:
    if res_type == "error": return None
    if res_type == "base64": return save_base64_video(res_content)
    if res_type == "url":
        try:
            save_path = os.path.join(Config.TEMP_DIR, f"{uuid.uuid4().hex}.mp4")
            async with aiohttp.ClientSession() as session:
                async with session.get(res_content, timeout=300) as resp:
                    if resp.status == 200:
                        with open(save_path, "wb") as f:
                            f.write(await resp.read())
                        return save_path
        except Exception as e:
            logger.error(f"下载失败: {e}")
    return None

# ================= 任务执行逻辑 =================
async def run_generation_task(bot: ExtendBot, event: GroupMessageEvent, image_url: str, prompt: str):
    user_id = event.user_id
    
    # 预先扣除次数
    if not quota_manager.deduct_quota(user_id):
        await bot.send(event, Text("次数扣除失败，请检查剩余次数。"))
        return

    # 标记并发
    quota_manager.add_active_task(user_id)
    
    try:
        await bot.send(event, Text("正在调用Grok生成视频，请耐心等待1-2分钟..."))
        
        # 调用 API
        res_type, res_content = await call_grok_video_api(image_url, prompt)
        
        # 如果 API 返回错误，退还次数
        if res_type == "error":
            quota_manager.refund_quota(user_id)
            await bot.send(event, Text(f"生成失败，已退还次数。错误原因：{res_content}"))
            return

        # 下载文件
        local_path = await process_download(res_type, res_content)
        
        if local_path and os.path.exists(local_path):
            # 发送视频
            await bot.send(event, File(file=local_path))
            
            # 发送剩余次数提示
            remaining = quota_manager.get_remaining_count(user_id)
            await bot.send(event, Text(f"视频生成完毕！你当前剩余生成次数为：{remaining}"))
            
            # 延时清理
            await asyncio.sleep(60)
            try: os.remove(local_path)
            except: pass
        else:
            # 下载或保存失败，退还次数
            quota_manager.refund_quota(user_id)
            await bot.send(event, Text("视频生成成功但保存失败，已退还次数。"))
            
    except Exception as e:
        logger.error(f"任务执行异常: {e}")
        # 发生未知异常，退还次数
        quota_manager.refund_quota(user_id)
        await bot.send(event, Text("系统内部发生错误，已退还次数。"))
    finally:
        # 任务结束，释放并发名额
        quota_manager.remove_active_task(user_id)

# ================= 会话状态管理 =================
class UserSession:
    def __init__(self):
        self.sessions = {} 

    def get_step(self, user_id):
        return self.sessions.get(user_id, {}).get("step")

    def get_img_url(self, user_id):
        return self.sessions.get(user_id, {}).get("img_url")

    def start_wait_img(self, user_id):
        self.sessions[user_id] = {"step": "waiting_img", "img_url": None}

    def set_img_wait_prompt(self, user_id, img_url):
        self.sessions[user_id] = {"step": "waiting_prompt", "img_url": img_url}

    def clear(self, user_id):
        if user_id in self.sessions:
            del self.sessions[user_id]

session_mgr = UserSession()

# ================= 主入口 =================
def main(bot: ExtendBot, config: YAMLManager):
    
    @bot.on(GroupMessageEvent)
    async def _(event: GroupMessageEvent):
        try:
            user_id = event.user_id
            text = event.pure_text.strip() if event.pure_text else ""
            
            if user_id == Config.ADMIN_QQ and text.startswith("/"):
                # 使用正则匹配
                match = re.match(r"^/(\d+)\+(\d+)$", text)
                if match:
                    target_qq = match.group(1)
                    add_count = int(match.group(2))
                    
                    # 执行增加
                    current_total = quota_manager.admin_add_quota(target_qq, add_count)
                    await bot.send(event, Text(f"操作成功！已为用户{target_qq}增加次数{add_count}，当前剩余次数为{current_total}"))
                    return

            # --- 取消指令 ---
            if text in ["取消", "/cancel", "退出"]:
                if session_mgr.get_step(user_id):
                    session_mgr.clear(user_id)
                    await bot.send(event, Text("操作已取消。"))
                return

            # --- 触发指令 ---
            if text == "/视频":
                # 检查限制
                if not quota_manager.check_concurrent(user_id):
                    await bot.send(event, Text("你当前任务已达上限，请稍后重试..."))
                    return
                
                # 预检查是否有剩余次数
                if quota_manager.get_remaining_count(user_id) <= 0:
                    await bot.send(event, Text("你今日的生成视频次数已经耗尽。"))
                    return

                session_mgr.start_wait_img(user_id)
                await bot.send(event, Text("请发送一张图片，或发送【取消】以终止任务。"))
                return

            # 获取当前状态
            current_step = session_mgr.get_step(user_id)

            # --- 接收图片 ---
            if current_step == "waiting_img":
                img_url = extract_first_image_url(event)
                
                if img_url:
                    session_mgr.set_img_wait_prompt(user_id, img_url)
                    await bot.send(event, Text("请发送提示词（如：让她的头发动起来。）"))
                elif text:
                    pass
                return

            # --- 接收提示词并生成 ---
            if current_step == "waiting_prompt":
                if not text:
                    return

                prompt = text
                img_url = session_mgr.get_img_url(user_id)
                
                # 清除会话
                session_mgr.clear(user_id)
                
                # 双重检查
                if not quota_manager.check_concurrent(user_id):
                    await bot.send(event, Text("你当前任务已达上限，请稍后重试..."))
                    return
                if quota_manager.get_remaining_count(user_id) <= 0:
                    await bot.send(event, Text("你今日的生成视频次数已经耗尽。"))
                    return

                # 启动后台任务
                asyncio.create_task(run_generation_task(bot, event, img_url, prompt))
                return

        except Exception as e:
            logger.error(f"主流程异常: {e}")