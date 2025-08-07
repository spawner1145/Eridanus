import random
import asyncio
import httpx
import base64
import os
import re
from io import BytesIO
from asyncio import get_event_loop
from PIL import Image
from .common import get_abs_path


async def download_img(url, gray_layer=False, proxy="http://127.0.0.1:7890"):
    if url.startswith("data:image"):
        match = re.match(r"data:image/(.*?);base64,(.+)", url)
        if not match:
            raise ValueError("Invalid Data URI format")

        img_type, base64_data = match.groups()
        img_data = base64.b64decode(base64_data)  # 解码 Base64 数据
        base64_img = base64.b64encode(img_data).decode('utf-8')
        return base64_img

    if proxy is not None and proxy != '':
        proxies = {"http://": proxy, "https://": proxy}
    else:
        proxies = None
    async with httpx.AsyncClient(proxies=proxies) as client:
        try:
            response = await client.get(url)
        except Exception as e:
            try:
                response = await client.get('https://gal.manshuo.ink/usr/uploads/galgame/zatan.png')
            except Exception:
                response = await client.get(
                    'https://gal.manshuo.ink/usr/uploads/galgame/img/%E4%B8%96%E4%BC%8AGalgame.png')
        if response.status_code != 200:
            response = await client.get('https://gal.manshuo.ink/usr/uploads/galgame/img/%E4%B8%96%E4%BC%8AGalgame.png')

        if gray_layer:
            try:
                with BytesIO(response.content) as img_buffer:
                    img = Image.open(img_buffer)
                    image_black_white = img.convert('1')  # 转换为黑白图像

                with BytesIO() as output_buffer:
                    image_black_white.save(output_buffer, format='PNG')
                    img_data = output_buffer.getvalue()
                    base64_img = base64.b64encode(img_data).decode('utf-8')

                img.close()
                image_black_white.close()

            except Exception as e:
                base64_img = base64.b64encode(response.content).decode('utf-8')
        else:
            base64_img = base64.b64encode(response.content).decode('utf-8')

        return base64_img

#对图像进行批量处理
async def process_img_download(img_list,is_abs_path_convert=True,gray_layer=False,proxy=None):
    if not isinstance(img_list, list):
        img_list = [img_list]
    processed_img=[]
    bio = None
    img_data = None
    temp_path = None
    for content in img_list:
        if isinstance(content, str) and os.path.splitext(content)[1].lower() in [".jpg", ".png", ".jpeg",'.webp'] and not content.startswith("http"):  # 若图片为本地文件，则转化为img对象
            if is_abs_path_convert is True: content = get_abs_path(content)
            processed_img.append(Image.open(content))
        elif isinstance(content, str) and content.startswith("http"):
            processed_img.append(Image.open(BytesIO(base64.b64decode(await download_img(content,proxy=proxy)))))
        elif isinstance(content, Image.Image):
            processed_img.append(content)
        else:  # 最后判断是否为base64，若不是，则不添加本次图像
            bio = None
            img_data = None
            try:
                img_data = base64.b64decode(content)
                bio = BytesIO(img_data)
                processed_img.append(Image.open(bio))
            except:
                pass
            finally:
                # 清理资源
                if img_data is not None:
                    del img_data
    return processed_img