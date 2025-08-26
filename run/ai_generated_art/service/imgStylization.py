import asyncio

import aiofiles
import httpx

from framework_common.utils.file2url import upload_image_with_quality

from framework_common.utils.utils import download_img

import asyncio
import httpx
import aiofiles


async def retry_async(func, *args, retries=5, delay=1, **kwargs):
    """
    通用异步重试函数
    :param func: 可等待的函数
    :param retries: 最大重试次数
    :param delay: 出错后的等待时间（秒）
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exc = e
            print(f"⚠️ 第 {attempt} 次尝试失败: {e}")
            if attempt < retries:
                await asyncio.sleep(delay)
    raise last_exc

async def imgStylization(input_url, style_set, output_image_path):
    # 下载图片
    await retry_async(download_img, input_url, output_image_path)

    # 上传图片
    url = await retry_async(upload_image_with_quality, output_image_path, 60)

    async with httpx.AsyncClient() as client:
        # 调用风格化 API
        async def get_style_api():
            resp = await client.get(
                f"https://api.xingzhige.com/API/AiStyle/?model={style_set}&url={url}",
                timeout=60,
            )
            data = resp.json()
            print(data)
            return data["data"]["imageUrl"]

        new_url = await retry_async(get_style_api)

        # 下载生成后的图片
        async def download_result():
            resp = await client.get(new_url, timeout=60)
            if resp.status_code != 200:
                raise RuntimeError(f"下载失败，状态码 {resp.status_code}")
            async with aiofiles.open(output_image_path, "wb") as f:
                await f.write(resp.content)
            return output_image_path

        return await retry_async(download_result)

#asyncio.run(imgStylization("https://multimedia.nt.qq.com.cn/download?appid=1407&fileid=EhTKAzpqLZd-FM5VkBOua7zbk8S_JRiEnAwg_woo3q63jcynjwMyBHByb2RQgL2jAVoQvm6yt8sCn2Niw92dDdA_NHoCAlE&rkey=CAMSOLgthq-6lGU_tSgj3OkfqsgzUFGTbNVBBI8rTjXFzkQsTPCK-kOxhEx4s67wDpt2ngGcmu7BQouR", "像素风格", "output.jpg"))
