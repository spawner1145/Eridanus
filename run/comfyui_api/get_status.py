from developTools.event.events import GroupMessageEvent
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager        
import asyncio
import random
import os
import json
from developTools.message.message_components import File, Image, Video, Node, Text
from framework_common.utils.utils import delay_recall # 撤回防刷屏

from .comfy_api.client import ComfyUIClient

# 可配置的 base_url 映射，之后就可以用别名代替 base_url 防止泄密
base_url_mapping = {
    "local": "http://127.0.0.1:8188",
    "cloud": "http://your-comfy-cloud-server:8188",
    "dev": "http://dev.comfy.example:8188",
    # 可继续添加
}

def resolve_base_url(input_str: str) -> str:
    try:
        if not input_str or not input_str.strip():
            raise ValueError("输入为空")
        key = input_str.strip()
        return base_url_mapping.get(key, key)
    except Exception as e:
        raise ValueError(f"解析 base_url 失败: {e}")

def main(bot: ExtendBot, config: YAMLManager):
    @bot.on(GroupMessageEvent)
    async def handle_group_message(event: GroupMessageEvent):
        try:
            text = event.pure_text.strip()
            if not text:
                return

            if text.startswith("view "):
                arg = text[len("view "):].strip()
                if not arg:
                    msg = await bot.send(event, "❌ 用法：view <base_url 或别名>\n例如：view local 或 view http://127.0.0.1:8188")
                    await delay_recall(bot, msg, 10)
                    return

                try:
                    base_url = resolve_base_url(arg)
                except Exception as e:
                    msg = await bot.send(event, f"❌ 无法解析服务器地址：{e}")
                    await delay_recall(bot, msg, 10)
                    return

                msg = await bot.send(event, f"正在连接到服务器...")
                await delay_recall(bot, msg, 10)

                try:
                    async with ComfyUIClient(
                        base_url=base_url,
                        proxy=config.common_config.basic_config["proxy"]["http_proxy"]
                        if config.common_config.basic_config["proxy"].get("http_proxy") else None
                    ) as client:
                        tasks = await client.view_tasks()

                    message_parts = []
                    message_parts.append("[🏃‍➡️ Running]")
                    if tasks.get('running'):
                        message_parts.extend([f" - ID: {task['prompt_id']}" for task in tasks['running']])
                    else:
                        message_parts.append(" (无)")

                    message_parts.append("\n[⏳ Queued]")
                    if tasks.get('queued'):
                        message_parts.extend([f" - ID: {task['prompt_id']}" for task in tasks['queued']])
                    else:
                        message_parts.append(" (无)")

                    message_parts.append("\n[✅ Completed] (按最新完成的顺序显示, 最多10条)")
                    completed = tasks.get('completed', [])
                    if completed:
                        for task in completed[:10]:
                            outputs_preview = task.get('outputs_preview', '未知')
                            message_parts.append(f" - ID: {task['prompt_id']} (输出: {outputs_preview})")
                        if len(completed) > 10:
                            message_parts.append("  ...")
                    else:
                        message_parts.append(" (无)")

                    final_message = "\n".join(message_parts)
                    msg = await bot.send(event, final_message)
                    await delay_recall(bot, msg, 30)

                except asyncio.TimeoutError:
                    msg = await bot.send(event, "❌ 请求超时，请检查服务器是否可达或网络状况。")
                    await delay_recall(bot, msg, 10)
                except ConnectionError:
                    msg = await bot.send(event, "❌ 连接被拒绝，请检查服务器地址和端口是否正确。")
                    await delay_recall(bot, msg, 10)
                except Exception as e:
                    msg = await bot.send(event, f"❌ 获取任务列表失败：{str(e)}")
                    await delay_recall(bot, msg, 10)

            elif text.startswith("interrupt "):
                arg = text[len("interrupt "):].strip()
                if not arg:
                    msg = await bot.send(event, "❌ 用法：interrupt <base_url 或别名>")
                    await delay_recall(bot, msg, 10)
                    return

                try:
                    base_url = resolve_base_url(arg)
                except Exception as e:
                    msg = await bot.send(event, f"❌ 无法解析服务器地址：{e}")
                    await delay_recall(bot, msg, 10)
                    return

                try:
                    async with ComfyUIClient(
                        base_url=base_url,
                        proxy=config.common_config.basic_config["proxy"]["http_proxy"]
                        if config.common_config.basic_config["proxy"].get("http_proxy") else None
                    ) as client:
                        success = await client.interrupt_running_task()
                        if success:
                            msg = await bot.send(event, "✅ 中断请求已成功发送。")
                            await delay_recall(bot, msg, 10)
                        else:
                            msg = await bot.send(event, "⚠️ 无正在运行的任务，或中断无效。")
                            await delay_recall(bot, msg, 10)
                except asyncio.TimeoutError:
                    msg = await bot.send(event, "❌ 中断请求超时。")
                    await delay_recall(bot, msg, 10)
                except ConnectionError:
                    msg = await bot.send(event, "❌ 无法连接到目标服务器，请检查地址和网络。")
                    await delay_recall(bot, msg, 10)
                except Exception as e:
                    msg = await bot.send(event, f"❌ 执行中断时出错：{str(e)}")
                    await delay_recall(bot, msg, 10)

            elif text.startswith("delete "):
                args = text[len("delete "):].strip().split(" ", 1)
                if len(args) != 2:
                    msg = await bot.send(event, "❌ 用法错误！请使用：delete <base_url 或别名> <prompt_id>")
                    await delay_recall(bot, msg, 10)
                    return

                input_base, prompt_id_str = args
                prompt_id_str = prompt_id_str.strip()

                if not prompt_id_str.isdigit():
                    msg = await bot.send(event, "❌ prompt_id 必须是一个数字。")
                    await delay_recall(bot, msg, 10)
                    return

                try:
                    prompt_id = int(prompt_id_str)
                except Exception:
                    msg = await bot.send(event, "❌ prompt_id 格式无效。")
                    await delay_recall(bot, msg, 10)
                    return

                try:
                    base_url = resolve_base_url(input_base)
                except Exception as e:
                    msg = await bot.send(event, f"❌ 无法解析服务器地址：{e}")
                    await delay_recall(bot, msg, 10)
                    return

                try:
                    async with ComfyUIClient(
                        base_url=base_url,
                        proxy=config.common_config.basic_config["proxy"]["http_proxy"]
                        if config.common_config.basic_config["proxy"].get("http_proxy") else None
                    ) as client:
                        success = await client.delete_queued_tasks(prompt_id)
                        if success:
                            msg = await bot.send(event, "✅ 删除请求已成功发送。")
                            await delay_recall(bot, msg, 10)
                        else:
                            msg = await bot.send(event, "⚠️ 未找到指定任务，或任务已完成/运行中。")
                            await delay_recall(bot, msg, 10)
                except asyncio.TimeoutError:
                    msg = await bot.send(event, "❌ 删除请求超时。")
                    await delay_recall(bot, msg, 10)
                except ConnectionError:
                    msg = await bot.send(event, "❌ 无法连接到服务器。")
                    await delay_recall(bot, msg, 10)
                except Exception as e:
                    msg = await bot.send(event, f"❌ 删除任务时发生错误：{str(e)}")
                    await delay_recall(bot, msg, 10)
        except json.JSONDecodeError as e:
            msg = await bot.send(event, "❌ 服务器返回了无效数据格式。")
            await delay_recall(bot, msg, 10)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            try:
                msg = await bot.send(event, f"❌ 机器人内部发生未知错误，请联系管理员。{e}")
                await delay_recall(bot, msg, 10)
            except:
                pass