import asyncio
import json
import traceback
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import Text, File
from framework_common.database_util.User import get_user
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.utils.utils import delay_recall

from run.ai_generated_art.service.suno_api import generate_songs

SUNO_USAGE_FILE_PATH = Path("data/suno_uses.json")

suno_user_cache: Dict[int, Dict[str, Any]] = {}

def get_today_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def load_or_reset_suno_usage_data() -> Dict[str, Any]:
    today_str = get_today_date()
    SUNO_USAGE_FILE_PATH.parent.mkdir(exist_ok=True)
    if not SUNO_USAGE_FILE_PATH.exists():
        new_data = {"date": today_str, "usage_data": {}}
        save_suno_usage_data(new_data)
        return new_data
    try:
        with open(SUNO_USAGE_FILE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if data.get("date") != today_str:
            new_data = {"date": today_str, "usage_data": {}}
            save_suno_usage_data(new_data)
            return new_data
        else:
            return data
    except (json.JSONDecodeError, FileNotFoundError):
        new_data = {"date": today_str, "usage_data": {}}
        save_suno_usage_data(new_data)
        return new_data

def save_suno_usage_data(data: Dict[str, Any]):
    with open(SUNO_USAGE_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def init_suno_user_cache(user_id: int):
    if user_id not in suno_user_cache:
        suno_user_cache[user_id] = {
            "state": None,
            "prompt": None,
            "tags": None,
        }

def main(bot: ExtendBot, config):
    @bot.on(GroupMessageEvent)
    async def suno_message_handler(event: GroupMessageEvent):
        user_id = event.sender.user_id
        init_suno_user_cache(user_id)
        current_cache = suno_user_cache[user_id]
        pure_text = str(event.pure_text).strip()

        if pure_text.lower() == "#suno":
            if current_cache["state"] is not None:
                msg = await bot.send(event, [Text("你已处于Suno请求流程中，请继续操作或发送 #clear suno 清空")], True)
                await delay_recall(bot, msg, 20)
                return

            user_info = await get_user(event.user_id)
            unlimited_perm = config.ai_generated_art.config["suno"]["unlimited_permission"]
            
 
            if user_info.permission < unlimited_perm:
                usage_data = load_or_reset_suno_usage_data()
                user_uses = usage_data.get("usage_data", {}).get(str(user_id), 0)
                max_uses = config.ai_generated_art.config["suno"]["default_user_uses"]
                if user_uses >= max_uses:
                    await bot.send(event, [Text(f"你今天已经达到 {max_uses} 次调用上限，请明天再来吧！")], True)
                    return
            
            current_cache["state"] = "waiting_for_tags"
            msg = await bot.send(event, [Text("请输入歌曲风格标签 (tag)，发送 '1' 以留空，发送#clear suno退出监听")], True)
            await delay_recall(bot, msg, 30)
            return

        if pure_text.lower() == "#clear suno":
            if current_cache["state"] is None:
                return
            suno_user_cache[user_id] = {"state": None, "prompt": None, "tags": None}
            msg = await bot.send(event, [Text("已清空Suno缓存并退出请求")], True)
            await delay_recall(bot, msg, 10)
            return

        if pure_text.lower() == "#ok":
            if current_cache["state"] != "ready_to_generate":
                return
            
            processing_msg = await bot.send(event, [Text("已提交Suno请求，正在生成歌曲...")], True)
            
            prompt = current_cache["prompt"]
            tags = current_cache["tags"]
            cookie = config.ai_generated_art.config["suno"]["cookie"]
            proxy = config.common_config.basic_config["proxy"].get("http_proxy") or None

            suno_user_cache[user_id] = {"state": None, "prompt": None, "tags": None}

            try:
                files = await generate_songs(cookie, prompt, tags, proxy)
                await bot.recall(processing_msg)

                if files:
                    user_info = await get_user(event.user_id)
                    unlimited_perm = config.ai_generated_art.config["suno"]["unlimited_permission"]
                    remaining_uses_text = ""

                    if user_info.permission < unlimited_perm:
                        usage_data = load_or_reset_suno_usage_data()
                        current_uses = usage_data.get("usage_data", {}).get(str(user_id), 0)
                        new_uses = current_uses + 1
                        usage_data["usage_data"][str(user_id)] = new_uses
                        save_suno_usage_data(usage_data)
                        
                        max_uses = config.ai_generated_art.config["suno"]["default_user_uses"]
                        remaining = max_uses - new_uses
                        if remaining > 0:
                            remaining_uses_text = f"调用成功！你今天还剩下 {remaining} 次调用机会"
                        else:
                            remaining_uses_text = "今天没得🎵了"
                    else:
                        remaining_uses_text = "调用成功！"
                    
                    status_message = remaining_uses_text
                    await bot.send(event, [Text(status_message)], True)
                    
                    for file_path in files:
                        try:
                            await bot.send(event, [File(file=file_path)])
                            await asyncio.sleep(0.5) 
                        except Exception as send_error:
                            print(f"发送文件 {file_path} 失败: {send_error}")
                            await bot.send(event, [Text(f"发送其中一个文件时失败了")], True)

                else:
                    await bot.send(event, [Text("歌曲生成失败，未返回任何文件")], True)

            except Exception as e:
                await bot.recall(processing_msg)
                error_msg_text = f"Suno请求处理失败: {str(e)}"
                error_msg = await bot.send(event, [Text(error_msg_text)], True)
                print(f"Suno API调用失败详情: {traceback.format_exc()}")
                await delay_recall(bot, error_msg, 30)
            
            return
        
        if current_cache["state"] == "waiting_for_tags":
            current_cache["tags"] = None if pure_text == '1' else pure_text
            current_cache["state"] = "waiting_for_prompt"
            msg = await bot.send(event, [Text("请输入歌曲描述 (prompt)，发送 '1' 以留空")], True)
            await delay_recall(bot, msg, 30)
            return
            
        if current_cache["state"] == "waiting_for_prompt":
            current_cache["prompt"] = None if pure_text == '1' else pure_text
            current_cache["state"] = "ready_to_generate"
            
            tags_preview = current_cache['tags'] or "无"
            prompt_preview = current_cache['prompt'] or "无"
            
            reply_text = (
                f"发送 \"#ok\" 开始生成，或发送 \"#clear suno\" 取消"
            )
            
            msg = await bot.send(event, [Text(reply_text)], True)
            await delay_recall(bot, msg, 60)
            return
            
    return suno_message_handler
