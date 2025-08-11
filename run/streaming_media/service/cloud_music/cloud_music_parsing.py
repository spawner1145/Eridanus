import os

import aiofiles
import httpx

from developTools.utils.logger import get_logger

logger=get_logger("cloud_music_parser")
class CloudMusicParser:
    def __init__(self,proxies=None):
        self.proxies=proxies
        self.client = httpx.AsyncClient(proxies=proxies)
    def parse(self, url):
        pass
    async def getSongDetail(self, url):
        url=f"https://api.toubiec.cn/wyapi/getSongDetail.php?id={url}"
        async with httpx.AsyncClient(proxies=self.proxies) as client:
            response = await client.get(url)
            logger.info(response)
            return response.json()
    async def getMusicUrl(self, url,level="exhigh"):
        url=f"https://api.toubiec.cn/wyapi/getMusicUrl.php?id={url}&level={level}"
        async with httpx.AsyncClient(proxies=self.proxies) as client:
            response = await client.get(url)
            logger.info(response.json())
            return response.json()

    async def download_music(self, url: str, save_path: str):
        """异步下载音频文件到指定路径"""
        try:
            # 确保保存路径的目录存在
            os.makedirs(os.path.dirname(save_path), exist_ok=True)

            # 以流式方式下载文件
            async with self.client.stream("GET", url, follow_redirects=True) as response:
                response.raise_for_status()

                # 异步写入文件
                async with aiofiles.open(save_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        await f.write(chunk)

                logger.info(f"音频文件已下载到: {save_path}")
                return {"status": "success", "message": f"音频文件已下载到 {save_path}"}
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return {"status": "error", "message": str(e)}
