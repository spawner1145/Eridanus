import asyncio
from pathlib import Path

import httpx
import requests
from concurrent.futures import ThreadPoolExecutor
from typing import Optional


class Util:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls) -> "Util":
        """获取单例实例（同步方法）"""
        return cls()

    def __init__(self):
        if not hasattr(self, "_initialized"):  # 避免重复初始化
            self._executor = ThreadPoolExecutor(max_workers=2)
            self.headers = {}
            self.user_agent = None
            self._initialized = True

    async def init(self):
        """初始化时获取当前 UA 并设置 header"""
        if not self.user_agent:  # 避免重复获取
            # 用 asyncio.to_thread 包装同步方法，避免阻塞
            ua = await asyncio.to_thread(self.get_current_ua_from_web)
            if ua:
                self.user_agent = ua
                self.headers["User-Agent"] = ua

    def get_current_ua_from_web(self) -> Optional[str]:
        """从网络服务获取当前的 User-Agent（同步方法，只调用一次）"""
        ua_services = [
            "https://httpbin.org/user-agent",
            "http://httpbin.org/user-agent",
        ]

        for service in ua_services:
            try:
                response = requests.get(service, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    ua = data.get("user-agent", "")
                    if ua:
                        return ua.strip()
            except Exception as e:
                print(f"从 {service} 获取 UA 失败: {e}")
                continue

        return None

    async def upload_image_with_quality(self,
            image_path: str,
            quality: int = 60,
            token: str = None,
            referer: str = None
    ):
        """
        使用 httpx 异步上传图片
        :param image_path: 图片文件路径
        :param quality: 图片质量 (默认60)
        :param token: PHPSESSID (必填)
        :param referer: 可选的 Referer
        :return: httpx.Response
        """

        url = "https://dev.ruom.top/api.php"

        # Cookies
        cookies = {
            "upload_count": '{"date":"2025-08-26","count":1}',  # 可根据实际情况改
            "PHPSESSID": token if token else "",  # 必须带上
        }

        # Headers
        headers = {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "origin": "https://dev.ruom.top",
            "referer": "https://dev.ruom.top/",
            "sec-ch-ua": '"Not;A=Brand";v="99", "Microsoft Edge";v="139", "Chromium";v="139"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": self.user_agent,
        }

        # 文件 & 表单
        files = {
            "image": (Path(image_path).name, open(image_path, "rb"), "image/jpeg"),
        }
        data = {
            "quality": str(quality),
        }

        async with httpx.AsyncClient(cookies=cookies, headers=headers, timeout=60) as client:
            response = await client.post(url, data=data, files=files)
            print(response.json())
            return response.json()["data"]["url"]


