import traceback

import httpx
import os
import asyncio
from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import Image, Text, Mface
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.utils.utils import get_img, download_img
from run.ai_generated_art.function_collection import gptimage2_text2img


# 假设这个函数已经在别处定义好
# from run.ai_generated_art.function_collection import gptimage2_text2img, image_edit

def main(bot: ExtendBot, config: YAMLManager):
    # 存储格式: {user_id: {"image": [path1, path2], "text": [prompt1, prompt2]}}
    user_dict = {}

    @bot.on(GroupMessageEvent)
    async def handle_group_message(event: GroupMessageEvent):
        nonlocal user_dict
        uid = event.user_id

        # 1. 基础生图指令
        if event.pure_text.startswith("/gpt"):
            prompt = event.pure_text.replace("/gpt", "", 1).strip()
            # 假设 gptimage2_text2img 是异步的
            await bot.send(event, "正在生成图片，请稍候...")
            await gptimage2_text2img(bot, event, config, prompt)
            return

        # 2. 进入编辑模式
        if event.pure_text == "/图像编辑":
            user_dict[uid] = {"image": [], "text": []}
            await bot.send(event, "进入添加模式，请发送文本描述和图像（可多张）\n全部发送完成后，请发送 /end 提交任务")
            return

        # 3. 提交任务
        elif event.pure_text == "/end":
            if uid not in user_dict or (not user_dict[uid]["image"] and not user_dict[uid]["text"]):
                await bot.send(event, "你还没有添加任何内容哦。")
                return

            # 获取配置
            api_config = config.ai_generated_art.config.get("gptimage2", {})
            base_url = api_config.get("base_url", "http://apollodorus.xyz:8009/v1")
            apikey = api_config.get("apikey", "")

            # 整合 Prompt（将多次发送的文本合并）
            full_prompt = " ".join(user_dict[uid]["text"])
            if not full_prompt:
                full_prompt = "编辑图像"  # 兜底 prompt

            await bot.send(event, "正在处理图片，请稍候...")

            try:
                # 准备文件流
                file_objects = []
                # 注意：这里需要保存打开的文件句柄，确保在请求发送前不被关闭
                for i, path in enumerate(user_dict[uid]["image"]):
                    if os.path.exists(path):
                        f = open(path, "rb")
                        # 格式: (字段名, (文件名, 文件流, MIME类型))
                        # 使用 "images" 作为字段名，对应你 API 支持的多图上传
                        file_objects.append(("images", (os.path.basename(path), f, "image/png")))

                headers = {"Authorization": f"Bearer {apikey}"}
                data = {
                    "prompt": full_prompt,
                    "size": "1024x1024"
                }
                user_dict.pop(uid)  # 立即清理用户数据，避免重复提交


                max_retry = 5

                async def request_api(retries=0):

                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            f"{base_url}/images/edits",
                            headers=headers,
                            files=file_objects,
                            data=data,
                            timeout=None  # 图像生成较慢，设置长一点的超时
                        )
                    if resp.status_code == 200:
                        res_json = resp.json()
                        img_url = res_json["data"][0]["url"]
                        # 发送结果图片
                        await bot.send(event, [Image(file=img_url)])
                    else:
                        retries+=1
                        await request_api(retries)
                        bot.logger.error(f"请求失败 ({resp.status_code}): {resp.text} 重试")
                        if retries >= max_retry:
                            await bot.send(event, f"请求失败 ({resp.status_code}): {resp.text}")


                await request_api(0)
                for _, (_, f, _) in file_objects:
                    f.close()

            except Exception as e:
                traceback.print_exc()
                await bot.send(event, f"发生错误: {str(e)}")
            finally:
                # 无论成功失败，清理该用户的临时数据和本地文件
                if uid in user_dict:
                    for path in user_dict[uid]["image"]:
                        if os.path.exists(path):
                            os.remove(path)  # 删除临时下载的图片
                    user_dict.pop(uid)
            return

        # 4. 收集模式：当用户在 user_dict 中时，记录他发的消息
        elif uid in user_dict:
            found_any = False
            for mes in event.message_chain:
                if isinstance(mes,Text):
                    user_dict[uid]["text"].append(mes.text.strip())
                    found_any = True
                elif isinstance(mes, Image) or isinstance(mes, Mface):
                    url = mes.url if hasattr(mes, 'url') and mes.url else mes.file
                    if url:
                        path = await download_img(url)
                        user_dict[uid]["image"].append(path)
                        found_any = True

            if found_any:
                # 可以选择不回复，或者小声提示
                await bot.send(event, "已添加")
                pass