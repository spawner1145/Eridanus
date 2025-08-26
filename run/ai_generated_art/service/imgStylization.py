import asyncio

import aiofiles
import httpx

from framework_common.utils.file2url import upload_image_with_quality

from framework_common.utils.utils import download_img

async def imgStylization(input_url, style_set, output_image_path):
    await download_img(input_url, output_image_path)
    url=await upload_image_with_quality(output_image_path, 60)
    async with httpx.AsyncClient() as client:
        url=f"https://api.xingzhige.com/API/AiStyle/?model={style_set}&url={url}"
        response = await client.get(url,timeout=60)
        new_url = response.json()["data"]["imageUrl"]
        response = await client.get(new_url)
        if response.status_code == 200:
            async with aiofiles.open(output_image_path, "wb") as f:
                await f.write(response.content)
            return output_image_path
#asyncio.run(imgStylization("https://multimedia.nt.qq.com.cn/download?appid=1407&fileid=EhTKAzpqLZd-FM5VkBOua7zbk8S_JRiEnAwg_woo3q63jcynjwMyBHByb2RQgL2jAVoQvm6yt8sCn2Niw92dDdA_NHoCAlE&rkey=CAMSOLgthq-6lGU_tSgj3OkfqsgzUFGTbNVBBI8rTjXFzkQsTPCK-kOxhEx4s67wDpt2ngGcmu7BQouR", "像素风格", "output.jpg"))