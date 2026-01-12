import os

import aiofiles
import httpx
import pprint
import asyncio

from developTools.utils.logger import get_logger

logger=get_logger("cloud_music_parser")
class CloudMusicParser:
    def __init__(self,base_url=None,proxies=None):
        self.proxies=proxies
        self.client = httpx.AsyncClient(proxies=proxies,timeout=30.0)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0"
        }
        self.base_url = base_url

    async def getSongDetail(self, song_url):
        api_url=f"{self.base_url}/song"
        params = {
            'url': song_url,
            'type': 'json',
        }
        #print(api_url,params)
        async with httpx.AsyncClient(proxies=self.proxies,headers=self.headers) as client:
            response = await client.get(api_url,params=params,timeout=30.0)
            logger.info(response)
            #pprint.pprint(response.json())
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

    async def download_music_stream(self, song_id, save_path=None, level=None):
        api_url=f"{self.base_url}/download"
        if level is None:
            level = 'standard'
        if save_path is None:
            save_path = 'data/voice/cache/test.mp3'
        params = {
            'id': int(song_id),
            'quality': level,
        }
        try:
            #print(api_url,params)
            async with httpx.AsyncClient(proxies=self.proxies,headers=self.headers) as client:
                response = await client.get(api_url,params=params,timeout=30.0)
                if response.status_code == 200:
                    # 以二进制模式写入文件
                    with open(save_path, 'wb') as f:
                        f.write(response.content)
                    logger.info(f"音频文件已下载到: {save_path}")
                    return {"status": "success", "message": f"音频文件已下载到 {save_path}"}
                else:
                    logger.error(f"下载失败")
                    return {"status": "error", "message": str(e)}
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return {"status": "error", "message": str(e)}


async def test(url):
    music = CloudMusicParser(base_url='http://nas.manshuo.ink:5000/wyy')
    detail_result = await music.getSongDetail(url)
    #pprint.pprint(detail_result)
    song_id = detail_result['data']["id"]
    stream = await music.download_music_stream(song_id)
    pprint.pprint(stream)
    #name = await music.getSongName(url)

if __name__ == "__main__":#测试用，不用管
    url = 'https://163cn.tv/YNBQxuR'
    asyncio.run(test(url))