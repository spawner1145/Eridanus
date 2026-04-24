import base64
import os
import re

import httpx

from developTools.message.message_components import Image
from framework_common.database_util.User import get_user
from framework_common.utils.utils import download_img


async def image_edit(bot,event,config,prompt,image_url):
    user=await get_user(event.user_id)
    permission_need=config.ai_generated_art.config["gptimage2"]["权限要求"]
    if user.permission<permission_need:
        return
    image_path=await download_img(image_url)
    aim_url="http://apollodorus.xyz:8080/v1/images/edits"

    file_objects = []
    f = open(image_path, "rb")
    # 格式: (字段名, (文件名, 文件流, MIME类型))
    # 使用 "images" 作为字段名，对应你 API 支持的多图上传
    file_objects.append(("images", (os.path.basename(image_path), f, "image/png")))


    apikey=config.ai_generated_art.config["gptimage2"]["apikey"]
    headers = {"Authorization": f"Bearer {apikey}"}

    data = {
        "prompt": prompt,
        "size": "1024x1024"
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
async def gptimage2_text2img(bot,event,config,prompt):
    user=await get_user(event.user_id)
    permission_need=config.ai_generated_art.config["gptimage2"]["权限要求"]
    if user.permission<permission_need:
        return

    def clean_prompt(prompt):
        remove_list = [
            "round face:1.2",
            "Rella:1.2",
            "chen bin:1.3",
            "virtual youtuber",
            "starshadowmagician:1.2",
            "lineart",
            "hand-drawn:1.3",
            "sketch:1.2",
            "Picasso style",
            "<lora:curearcanashadow_v1.0_IL:0.5>",
            "Van Gogh's almond blossoms",
            "Van Gogh’s almond blossoms",
        ]

        for p in remove_list:
            # 匹配带括号 / 不带括号 / 前后空格 / 可选逗号
            pattern = r"\s*\(?" + re.escape(p) + r"\)?\s*,?"
            prompt = re.sub(pattern, "", prompt)

        # 清理多余逗号和空格
        prompt = re.sub(r",\s*,+", ",", prompt)
        prompt = prompt.strip(", ").strip()

        prompt += "\n以上为stable diffusion的提示词，请基于这些提示词进行创作，如提示词未特别说明，则一般采用二次元/日漫风格"
        return prompt
    prompt=clean_prompt(prompt)
    apikey=config.ai_generated_art.config["gptimage2"]["apikey"]
    headers = {"Authorization": f"Bearer {apikey}"}

    base_url="http://apollodorus.xyz:8009/v1/images/generations"
    payload = {
            "prompt": prompt,
            "size": "1024x1024",  # 映射为 16:9
            "response_format": "url",  # 或 "b64_json"
            "n": 1,
        }

    async with httpx.AsyncClient( timeout=None,headers=headers) as client:
        response = await client.post(base_url, json=payload)
        resp=response.json()
        img_url = resp["data"][0]["url"]
        await bot.send(event,Image(file=img_url),True)