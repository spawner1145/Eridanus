import base64

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
    aim_url="http://apollodorus.xyz:8080/v1/images/generations"
    with open(image_path, "rb") as f:
        base64_str = base64.b64encode(f.read()).decode("utf-8")

    image_input = f"data:image/png;base64,{base64_str}"
    apikey=config.ai_generated_art.config["gptimage2"]["apikey"]
    headers = {"Authorization": f"Bearer {apikey}"}
    payload = {
        "prompt": prompt,
        "image": image_input,
        "aspect_ratio": "1:1",
        "quality": "medium"
    }
    async with httpx.AsyncClient( timeout=None,headers=headers) as client:
        response = await client.post(aim_url, data=payload)
        data=response.json()
        img_url = data["data"][0]["url"]
        await bot.send(event,Image(file=img_url))
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
        response = await client.post(base_url, data=payload)
        resp=response.json()
        img_url = resp.json()["data"][0]["url"]
        await bot.send(event,Image(file=img_url))