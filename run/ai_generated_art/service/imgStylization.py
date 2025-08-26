import asyncio

import aiofiles
import httpx

from framework_common.utils.file2url import upload_image_with_quality

from framework_common.utils import UTIL
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
asyncio.run(imgStylization("https://multimedia.nt.qq.com.cn/download?appid=1407&fileid=EhT29kTnsUuV-DeapJrF8gNZLrowkxil914g_woozIrq98KnjwMyBHByb2RQgL2jAVoQ7BTLO_cIYlj_92z-hFayhXoCaEU&rkey=CAMSOLgthq-6lGU_4rzLAOm5njgmpqEsd8RApIRhKSljH7YYRrBR--u-URNxMXbRnrVuD_hoFd9O8oA-", "像素风格", "output.jpg"))