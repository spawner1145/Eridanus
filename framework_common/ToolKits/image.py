import base64
import random
import re
import string
from io import BytesIO
import os

import httpx

from PIL import Image
from .base import BaseTool


class ImageProcessor(BaseTool):
    def __init__(self):
        super().__init__(__class__.__name__)
    async def Image2Base64(self, url: str) -> str:
        """
        将图片转为base64，支持网络URL、本地文件路径、data:image base64字符串
        """
        if url.startswith("data:image"):
            match = re.match(r"data:image/(.*?);base64,(.+)", url)
            if not match:
                raise ValueError("Invalid Data URI format")
            _, base64_data = match.groups()
            return base64_data
        if not url.startswith(("http://", "https://")):
            if not os.path.isfile(url):
                raise FileNotFoundError(f"本地图片不存在：{url}")
            with open(url, "rb") as f:
                image_bytes = f.read()
        else:
            async with httpx.AsyncClient(timeout=9000) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    raise Exception(f"图片下载失败，状态码：{response.status_code}")
                image_bytes = response.content
        return base64.b64encode(image_bytes).decode("utf-8")
    async def download_img(self,url, path=None, gray_layer=False, proxy=None, headers=None)->str:
        """下载一张图片"""
        if path is None:
            characters = string.ascii_letters + string.digits
            random_string = ''.join(random.choice(characters) for _ in range(10))
            path = f'data/pictures/cache/{random_string}.jpg'
        if url.startswith("data:image"):
            match = re.match(r"data:image/(.*?);base64,(.+)", url)
            if not match:
                raise ValueError("Invalid Data URI format")
            img_type, base64_data = match.groups()
            img_data = base64.b64decode(base64_data)
            try:
                with open(path, "wb") as f:
                    f.write(img_data)
            finally:
                del img_data
            return path

        if proxy is not None and proxy != '':
            proxies = {"http://": proxy, "https://": proxy}
        else:
            proxies = None

        async with httpx.AsyncClient(proxies=proxies, headers=headers,timeout=60) as client:
            response = await client.get(url)

            if gray_layer:
                img = None
                try:
                    img = Image.open(BytesIO(response.content))  # 从二进制数据创建图片对象
                    image_raw = img
                    image_black_white = image_raw.convert('1')
                    image_black_white.save(path)
                finally:
                    if img is not None:
                        img.close()
                    del response
            else:
                try:
                    with open(path, 'wb') as f:
                        f.write(response.content)
                finally:
                    del response

            return path
