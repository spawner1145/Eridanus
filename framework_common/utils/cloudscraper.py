import asyncio
import concurrent.futures
import os
import re
import threading
from functools import partial
from typing import Optional, Dict, Any

from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.utils.install_and_import import install_and_import

cloudscraper = install_and_import("cloudscraper")


class AsyncWebClient:
    """
    异步Web客户端单例类
    提供异步HTTP请求和文件下载功能，复用连接池和线程池以提高性能
    """

    _instance = None
    _lock = threading.Lock()

    # 默认 User-Agent（类属性）
    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super(AsyncWebClient, cls).__new__(cls)
                    # 在这里初始化所有属性，确保它们存在
                    instance._initialized = False
                    instance._current_ua = cls.DEFAULT_USER_AGENT
                    instance._ua_initialized = False
                    instance._scraper = None
                    instance._scraper_lock = threading.Lock()
                    instance._executor = None
                    instance.config = None
                    instance.local_config = None
                    instance.proxy = None
                    cls._instance = instance
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self.config = YAMLManager.get_instance()
        self.local_config = self.config.common_config.basic_config
        self.proxy = self.local_config.get("proxy", {}).get("http_proxy")

        # 线程池配置
        if self._executor is None:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=5,
                thread_name_prefix="AsyncWebClient"
            )

    @classmethod
    def get_instance(cls) -> 'AsyncWebClient':
        """获取单例实例"""
        return cls()

    async def get_current_ua_from_web(self) -> Optional[str]:
        """从网络服务获取当前的 User-Agent"""
        ua_services = [
            "https://httpbin.org/user-agent",
            "http://httpbin.org/user-agent",
        ]

        for service in ua_services:
            try:
                # 使用一个临时的简单请求来获取 UA
                loop = asyncio.get_event_loop()

                def _get_ua_sync():
                    import requests
                    response = requests.get(service, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        return data.get('user-agent', '')
                    return None

                ua = await loop.run_in_executor(self._executor, _get_ua_sync)
                if ua:
                    return ua.strip()

            except Exception as e:
                print(f"从 {service} 获取 UA 失败: {e}")
                continue

        return None

    async def init_user_agent_from_web(self):
        """从网络初始化 User-Agent"""
        if self._ua_initialized:
            return

        web_ua = await self.get_current_ua_from_web()
        if web_ua:
            self._current_ua = web_ua
            print(f"从网络获取到 UA: {web_ua}")
        else:
            print(f"网络获取 UA 失败，使用默认 UA: {self._current_ua}")

        self._ua_initialized = True

    def set_user_agent(self, user_agent: str):
        """手动设置 User-Agent"""
        self._current_ua = user_agent
        self.reset_scraper()

    def get_current_user_agent(self) -> str:
        """获取当前使用的 User-Agent"""
        return self._current_ua

    def _create_scraper(self):
        """创建cloudscraper实例"""
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )

        # 设置自定义 User-Agent
        scraper.headers.update({'User-Agent': self._current_ua})

        if self.proxy:
            scraper.proxies = {
                'http': self.proxy,
                'https': self.proxy
            }

        return scraper

    def get_scraper(self):
        """获取scraper实例（线程安全的懒加载）"""
        if self._scraper is None:
            with self._scraper_lock:
                if self._scraper is None:
                    self._scraper = self._create_scraper()
        return self._scraper

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """清理文件名中的非法字符"""
        return re.sub(r'[\\/*?:"<>|]', "", filename)

    def _sync_request(self, method: str, url: str, **kwargs):
        """同步请求的包装函数"""
        scraper = self.get_scraper()
        method = method.upper()

        if method == 'GET':
            return scraper.get(url, **kwargs)
        elif method == 'POST':
            return scraper.post(url, **kwargs)
        elif method == 'PUT':
            return scraper.put(url, **kwargs)
        elif method == 'DELETE':
            return scraper.delete(url, **kwargs)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

    async def request(self, method: str, url: str, **kwargs):
        """异步HTTP请求"""
        # 首次请求时自动从网络获取 UA
        if not self._ua_initialized:
            await self.init_user_agent_from_web()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            partial(self._sync_request, method, url, **kwargs)
        )

    async def get(self, url: str, **kwargs):
        """异步GET请求"""
        return await self.request('GET', url, **kwargs)

    async def post(self, url: str, **kwargs):
        """异步POST请求"""
        return await self.request('POST', url, **kwargs)

    async def put(self, url: str, **kwargs):
        """异步PUT请求"""
        return await self.request('PUT', url, **kwargs)

    async def delete(self, url: str, **kwargs):
        """异步DELETE请求"""
        return await self.request('DELETE', url, **kwargs)

    def _sync_download_file(self, url: str, file_path: str, chunk_size: int = 8192):
        """同步下载文件的包装函数"""
        scraper = self.get_scraper()

        with scraper.get(url, stream=True) as response:
            response.raise_for_status()

            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)

        return file_path

    async def download_file(self, url: str, file_path: str, chunk_size: int = 8192):
        """异步下载文件"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            partial(self._sync_download_file, url, file_path, chunk_size)
        )

    async def download_file_with_sanitized_name(self, url: str, directory: str, filename: str = None,
                                                chunk_size: int = 8192):
        """下载文件并自动清理文件名"""
        if filename is None:
            filename = os.path.basename(url.split('?')[0])  # 移除查询参数

        sanitized_filename = self.sanitize_filename(filename)
        file_path = os.path.join(directory, sanitized_filename)

        return await self.download_file(url, file_path, chunk_size)

    def reset_scraper(self):
        """重置scraper实例（例如当代理配置变更时）"""
        with self._scraper_lock:
            self._scraper = None

    def update_proxy(self, new_proxy: Optional[str]):
        """更新代理配置"""
        self.proxy = new_proxy
        self.reset_scraper()  # 重置scraper以应用新代理

    async def refresh_user_agent_from_web(self):
        """从网络刷新 User-Agent"""
        web_ua = await self.get_current_ua_from_web()
        if web_ua:
            self.set_user_agent(web_ua)
            print(f"UA 已更新为: {web_ua}")
            return True
        else:
            print("从网络刷新 UA 失败")
            return False

    def close(self):
        """清理资源"""
        if hasattr(self, '_executor') and self._executor:
            self._executor.shutdown(wait=True)

    def __del__(self):
        """析构函数，确保资源被清理"""
        try:
            self.close()
        except:
            pass


# 使用示例和便捷函数
def get_web_client() -> AsyncWebClient:
    """获取Web客户端实例的便捷函数"""
    return AsyncWebClient.get_instance()


# 向后兼容的函数（如果其他代码还在使用原来的函数）
async def async_request(method: str, url: str, **kwargs):
    """向后兼容的异步请求函数"""
    client = get_web_client()
    return await client.request(method, url, **kwargs)


async def async_download_file(url: str, file_path: str):
    """向后兼容的异步下载文件函数"""
    client = get_web_client()
    return await client.download_file(url, file_path)


def sanitize_filename(filename: str) -> str:
    """向后兼容的文件名清理函数"""
    return AsyncWebClient.sanitize_filename(filename)


# 使用示例
async def example_usage():
    """使用示例"""
    client = get_web_client()

    # 客户端会在第一次请求时自动从网络获取 UA
    print(f"当前 UA: {client.get_current_user_agent()}")

    # 手动从网络刷新 User-Agent
    success = await client.refresh_user_agent_from_web()
    if success:
        print(f"刷新后 UA: {client.get_current_user_agent()}")

    # 手动设置 User-Agent
    client.set_user_agent("Custom User Agent 1.0")
    print(f"自定义 UA: {client.get_current_user_agent()}")

    # 再次从网络获取
    web_ua = await client.get_current_ua_from_web()
    if web_ua:
        print(f"从网络获取的 UA: {web_ua}")
        client.set_user_agent(web_ua)

    # 发送请求测试
    try:
        response = await client.get('https://httpbin.org/headers')
        print("请求头:", response.json() if hasattr(response, 'json') else "请求成功")
    except Exception as e:
        print(f"请求失败: {e}")


if __name__ == "__main__":
    # 测试代码
    asyncio.run(example_usage())