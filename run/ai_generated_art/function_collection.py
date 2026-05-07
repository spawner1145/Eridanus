import asyncio
import base64
import os
import re

import aiofiles
import httpx

from developTools.message.message_components import Image
from framework_common.database_util.User import get_user
from framework_common.utils.utils import download_img
from run.auto_reply.main import bot_name


async def image_edit(bot,event,config,prompt,image_url):
    user=await get_user(event.user_id)
    permission_need=config.ai_generated_art.config["gptimage2"]["权限要求"]
    if user.permission<permission_need:
        return
    image_path=await download_img(image_url)
    aim_url="http://api.apollodorus.xyz/v1/images/edits"

    file_objects = []
    f = open(image_path, "rb")
    # 格式: (字段名, (文件名, 文件流, MIME类型))
    # 使用 "images" 作为字段名，对应你 API 支持的多图上传
    file_objects.append(("images", (os.path.basename(image_path), f, "image/png")))


    apikey=config.ai_generated_art.config["gptimage2"]["apikey"]
    headers = {"Authorization": f"Bearer {apikey}"}

    data = {
        "prompt": prompt,
        "aspect_ratio": config.ai_generated_art.config["gptimage2"]["aspect_ratio"],
        "model": config.ai_generated_art.config["gptimage2"]["model"],
        "resolution": config.ai_generated_art.config["gptimage2"]["resolution"] or "1K",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            aim_url,
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
            await bot.send(event, f"请求失败 ({resp.status_code}): {resp.text}")


async def _send_bot_image_with_retry(bot, event, config, prompt, max_retries=5):
    """后台任务：生成bot相关图片，失败自动重试最多5次"""
    bot_name = config.common_config.basic_config["bot"]
    apikey = config.ai_generated_art.config["gptimage2"]["apikey"]
    headers = {"Authorization": f"Bearer {apikey}"}
    base_url = "http://api.apollodorus.xyz/v1"
    bot_oc = config.ai_generated_art.config["gptimage2"]["bot_oc"]
    extra_prompt = config.ai_generated_art.config["gptimage2"]["extra_prompt"]
    character_anchor = bot_name + config.ai_generated_art.config["gptimage2"]["character_anchor"]
    prompt_text = (
        f"【角色参考】附图为{bot_name}的设定图,仅作为外貌参考(发色、瞳色、发型),"
        f"请在保持角色辨识度的前提下进行完整重绘。\n"
        f"【角色特征锚点】{character_anchor}\n"
        f"【绘制任务】根据以下描述绘制{bot_name}:{prompt}。\n"
        f"必须为全新高分辨率重绘,而不是对原图进行模糊放大或局部修改。\n"
        f"【细节要求】全身清晰,服装、手部、背景细节完整且清楚。\n"
        f"【画质要求】masterpiece, best quality, ultra detailed, 4k, sharp focus。\n"
        f"【负面约束】no blur, no low resolution, no smudging, no soft focus。\n"
        f"【画风一致性】整体风格接近设定图,但允许自然细化。\n"
        f"【额外要求】{extra_prompt}"
    )

    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            async with aiofiles.open(bot_oc, "rb") as f1:
                file_content = await f1.read()

            async with httpx.AsyncClient(timeout=None, headers=headers) as client:
                resp = await client.post(
                    f"{base_url}/images/edits",
                    files=[
                        ("images", (os.path.basename(bot_oc), file_content, "image/png")),
                    ],
                    data={
                        "prompt": prompt_text,
                        "aspect_ratio": config.ai_generated_art.config["gptimage2"]["aspect_ratio"],
                        "resolution": config.ai_generated_art.config["gptimage2"]["resolution"] or "1K",
                        "model": config.ai_generated_art.config["gptimage2"]["model"],
                    },
                )
            await bot.send(event, Image(file=resp.json()["data"][0]["url"]),True)
            bot.logger.info(f"bot图片生成成功（第{attempt}次尝试）")
            return  # 成功则退出

        except Exception as e:
            last_exception = e
            bot.logger.warning(f"bot图片生成失败（第{attempt}/{max_retries}次）: {e}")
            if attempt < max_retries:
                await asyncio.sleep(2 ** (attempt - 1))  # 指数退避: 1s, 2s, 4s, 8s

    bot.logger.error(f"bot图片生成最终失败，已重试{max_retries}次，最后错误: {last_exception}")


async def text2img(bot, event, config, prompt, is_about_bot=False):
    user = await get_user(event.user_id)
    permission_need = config.ai_generated_art.config["gptimage2"]["权限要求"]
    if user.permission < permission_need:
        return
    bot.logger.info(f"用户 {event.user_id} 请求生成图片,提示词 {prompt} is_about_bot={is_about_bot}")

    if is_about_bot:
        # 丢到后台运行，不阻塞上游，无需等待结果
        asyncio.create_task(
            _send_bot_image_with_retry(bot, event, config, prompt)
        )
        #return "genrating....please wait..."

    else:
        apikey = config.ai_generated_art.config["gptimage2"]["apikey"]
        headers = {"Authorization": f"Bearer {apikey}"}
        base_url = "http://api.apollodorus.xyz/v1/images/generations"
        payload = {
            "prompt": prompt,
            "aspect_ratio": config.ai_generated_art.config["gptimage2"]["aspect_ratio"],
            "model": config.ai_generated_art.config["gptimage2"]["model"],
            "resolution": config.ai_generated_art.config["gptimage2"]["resolution"] or "1K",
            "response_format": "url",
            "n": 1,
        }
        async with httpx.AsyncClient(timeout=None, headers=headers) as client:
            response = await client.post(base_url, json=payload)
            resp = response.json()
            img_url = resp["data"][0]["url"]
            await bot.send(event, Image(file=img_url), True)