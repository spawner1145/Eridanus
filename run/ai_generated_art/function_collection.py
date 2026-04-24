import base64
import os

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
        img_url = resp.json()["data"][0]["url"]
        await bot.send(event,Image(file=img_url))