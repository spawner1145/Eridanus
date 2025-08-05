import os

import aiofiles
import httpx
import hashlib
import re
import json
import asyncio

"""
grok真好用
"""

class CloudMusicParsing:
    """网易云音乐链接解析类"""

    def __init__(self,proxies=None):
        self.api_urls = {
            "api1": {
                "token": "https://api.toubiec.cn/api/get-token.php",
                "parse": "https://api.toubiec.cn/api/music_v1.php"
            },
            "api2": {
                "token": "https://api1.toubiec.cn/api/get-token.php",
                "parse": "https://api1.toubiec.cn/api/music_v1.php"
            },
            "api3": {
                "token": "https://api2.toubiec.cn/api/get-token.php",
                "parse": "https://api2.toubiec.cn/api/music_v1.php"
            },
            "api4": {
                "token": "https://api3.toubiec.cn/api/get-token.php",
                "parse": "https://api3.toubiec.cn/api/music_v1.php"
            }
        }
        self.client = httpx.AsyncClient(proxies=proxies)  # 异步 HTTP 客户端

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.client.aclose()  # 确保关闭客户端

    async def get_token(self, api_type: str) -> str:
        """异步获取 token"""
        if api_type not in self.api_urls:
            raise ValueError("Invalid API type")

        try:
            response = await self.client.post(self.api_urls[api_type]["token"])
            response.raise_for_status()
            token = response.json().get("token", "").strip()  # 清理可能的换行符或空格
            print(f"原始 token: {token}")
            return token
        except Exception as e:
            print(f"获取 token 失败: {e}")
            return None

    def md5_encrypt(self, input_string: str, salt: str = None) -> str:
        """对输入字符串进行 MD5 加密，模拟 CryptoJS.MD5"""
        if not isinstance(input_string, str):
            input_string = str(input_string)
        input_string = input_string if not salt else input_string + salt
        return hashlib.md5(input_string.encode('utf-8')).hexdigest()

    def extract_url(self, input_string: str) -> str:
        """从输入字符串中提取 URL"""
        url_pattern = r"https?://\S+"
        match = re.search(url_pattern, input_string)
        return match.group(0) if match else ""

    async def parse_music(self, api_type: str, url: str, region: str, audio_type: str) -> dict:
        """异步解析音乐链接"""
        if api_type not in self.api_urls:
            raise ValueError("Invalid API type")

        # 获取 token
        token = await self.get_token(api_type)
        if not token:
            return {"status": "error", "message": "获取 token 失败"}

        # 尝试不同的 token 生成方式
        # 方式 1：对原始 token 进行 MD5
        encrypted_token = self.md5_encrypt(token)
        print(f"加密后的 token (仅 token): {encrypted_token}")

        # 方式 2：对 url + region + audio_type + token 进行 MD5
        combined_input = f"{self.extract_url(url)}{region}{audio_type}{token}"
        encrypted_token_combined = self.md5_encrypt(combined_input)
        print(f"加密后的 token (url + region + audio_type + token): {encrypted_token_combined}")

        # 构造请求体
        payload = {
            "url": self.extract_url(url),
            "level": region,
            "type": audio_type,
            "token": encrypted_token  # 默认使用仅对 token 加密的结果
            # 如果需要，可以切换为 encrypted_token_combined
        }
        print(f"请求体: {payload}")

        try:
            headers = {
                "Authorization": f"Bearer {token}"
            }
            response = await self.client.post(
                self.api_urls[api_type]["parse"],
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            if data.get("status") != 200:
                return {"status": "error", "message": data.get("msg", "解析失败，请重试！")}
            return {"status": "success", "data": data, "message": data.get("msg", "")}
        except Exception as e:
            print(f"解析失败: {e}")
            return {"status": "error", "message": str(e)}

    async def close(self):
        """关闭 HTTP 客户端"""
        await self.client.aclose()
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

                print(f"音频文件已下载到: {save_path}")
                return {"status": "success", "message": f"音频文件已下载到 {save_path}"}
        except Exception as e:
            print(f"下载失败: {e}")
            return {"status": "error", "message": str(e)}


async def main():
    async with CloudMusicParsing() as music:
        # 测试参数
        api_type = "api1"
        url = "https://music.163.com/song?id=2724695022&userid=305143326"  # 替换为实际的网易云音乐链接
        region = "exhigh"  # 音质：standard, exhigh, lossless, hires, jyeffect, sky, jymaster
        audio_type = "song"  # 类型：song, playlist, album, artist

        # 解析音乐链接
        result = await music.parse_music(api_type, url, region, audio_type)
        print(json.dumps(result, indent=2, ensure_ascii=False))

        # 如果解析成功，下载音频文件
        if result["status"] == "success" and "url_info" in result["data"]:
            audio_url = result["data"]["url_info"].get("url")
            if audio_url:
                save_path = "downloaded_music.mp3"  # 替换为实际保存路径
                result = result["data"]
                music_name = result["song_info"]["name"] + " - " + result["song_info"][
                    "artist"] + f".{result['url_info']['type']}"
                await music.download_music(result["url_info"]["url"],
                                           f"./{music_name.replace('/', '_')}")
                #download_result = await music.download_music(audio_url, save_path)
                #print(json.dumps(download_result, indent=2, ensure_ascii=False))

