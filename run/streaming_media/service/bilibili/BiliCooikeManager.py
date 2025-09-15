import asyncio
import json
import time
import traceback
from pathlib import Path
from typing import Optional, List, Dict, Any
from playwright.async_api import async_playwright, Browser, Page
import subprocess
import sys
import os
import threading
from developTools.utils.logger import get_logger
from framework_common.utils.PlayWrightAutoInstaller import check_and_install_playwright
from bilibili_api import hot, sync,Credential,dynamic
check_and_install_playwright()

logger = get_logger("bili_cookie_manager")
is_login_check = False
cookie_content = {}

class BiliCookieManager:
    """
    B站Cookie管理器 - 异步单例模式
    功能:
    - 自动登录获取Cookie
    - Cookie有效性验证
    - 定期自动更新Cookie
    - 异步非阻塞操作
    """

    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BiliCookieManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return

        self._initialized = True
        self.cookies: List[Dict[str, Any]] = []
        self.cookie_file = Path(__file__).parent.resolve() / 'bilibili_cookies.json'
        self.qr_file = Path(__file__).parent.resolve() / 'bilibili_qr.png'
        self.last_update_time = 0
        self.update_interval = 3600 * 12  # 12小时检查一次
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.is_updating = False
        self._background_task: Optional[asyncio.Task] = None
        self._playwright = None

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self._initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self._cleanup()

    async def _initialize(self):
        """初始化浏览器和页面"""
        if self.browser is None:
            try:
                self._playwright = await async_playwright().start()
                self.browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor'
                    ]
                )
            except Exception as e:
                #traceback.print_exc()
                pass


    async def _cleanup(self):
        """清理资源"""
        if self._background_task and not self._background_task.done():
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass

        if self.page:
            try:
                await self.page.close()
            except Exception as e:
                logger.warning(f"关闭页面时出错: {e}")
            finally:
                self.page = None

        if self.browser:
            try:
                await self.browser.close()
            except Exception as e:
                logger.warning(f"关闭浏览器时出错: {e}")
            finally:
                self.browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.warning(f"停止Playwright时出错: {e}")
            finally:
                self._playwright = None

    async def get_cookies(self, auto_login: bool = True,bot=None,group_id=None,check_cookie=True,login=False) -> List[Dict[str, Any]]:
        """
        获取Cookie

        Args:
            auto_login: 如果Cookie无效，是否自动登录

        Returns:
            Cookie列表
        """
        async with self._lock:

            global is_login_check
            if login is True:
                is_login_check = False
                cookies = await self._login_and_get_cookies(bot,group_id)
                if cookies:
                    self.cookies = cookies
                    await self._save_cookies()
                    return self.cookies.copy()

            # 先尝试加载本地Cookie
            await self._load_cookies()
            if not check_cookie:return self.cookies.copy()

            # 验证Cookie有效性
            if self.cookies and await self._validate_cookies() and group_id is None:
                #logger.info("使用本地有效Cookie")
                return self.cookies.copy()

            # Cookie无效或不存在，尝试自动登录
            if auto_login:
                logger.info("Cookie无效或不存在，开始自动登录...")
                cookies = await self._login_and_get_cookies(bot,group_id)
                if cookies:
                    self.cookies = cookies
                    await self._save_cookies()
                    return self.cookies.copy()

            logger.warning("无法获取有效Cookie")
            return []

    async def _load_cookies(self):
        """从文件加载Cookie"""
        global cookie_content
        if cookie_content != {}: self.cookies = cookie_content
        if self.cookie_file.exists() and cookie_content == {}:
            try:
                with open(self.cookie_file, 'r', encoding='utf-8') as f:
                    self.cookies = json.load(f)
                    cookie_content = self.cookies
                #logger.info(f"已加载 {len(self.cookies)} 个Cookie")
            except Exception as e:
                logger.error(f"加载Cookie失败: {e}")
                self.cookies = []

    async def _save_cookies(self):
        """保存Cookie到文件"""
        global cookie_content
        try:
            with open(self.cookie_file, 'w', encoding='utf-8') as f:
                json.dump(self.cookies, f, indent=2, ensure_ascii=False)
            cookie_content = self.cookies
            self.last_update_time = time.time()
            logger.info(f"Cookie已保存到: {self.cookie_file.absolute()}")
        except Exception as e:
            logger.error(f"保存Cookie失败: {e}")

    async def _validate_cookies(self) -> bool:
        """验证Cookie有效性"""
        if not self.cookies:
            return False

        BILI_SESSDATA, bili_jct, buvid3, DedeUserID = '', '', '', ''
        for cookie in self.cookies:
            if cookie['name'] == 'SESSDATA':
                BILI_SESSDATA = cookie['value']
            elif cookie['name'] == 'bili_jct':
                bili_jct = cookie['value']
            elif cookie['name'] == 'buvid3':
                buvid3 = cookie['value']
            elif cookie['name'] == 'DedeUserID':
                DedeUserID = cookie['value']
        credential = Credential(sessdata=BILI_SESSDATA, bili_jct=bili_jct, buvid3=buvid3, dedeuserid=DedeUserID)
        if sync(credential.check_refresh()):
            return False
        else:
            return True


    async def _login_and_get_cookies(self,bot=None,group_id=None) -> Optional[List[Dict[str, Any]]]:
        """登录并获取Cookie"""
        global is_login_check
        if is_login_check:return None
        is_login_check = True
        page = None
        try:
            await self._initialize()
            page = await self.browser.new_page(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

            logger.info("正在打开B站...")
            await page.goto('https://www.bilibili.com', wait_until='networkidle')

            logger.info("正在悬停在登录入口...")
            login_entry = await page.wait_for_selector('.header-login-entry', timeout=30000)
            await login_entry.hover()

            logger.info("等待立即登录按钮出现...")
            await page.wait_for_timeout(500)

            logger.info("正在点击立即登录按钮...")
            immediate_login_btn = await page.wait_for_selector('text=立即登录', timeout=30000)
            await immediate_login_btn.click()

            logger.info("等待登录弹窗出现...")
            await page.wait_for_selector('.login-scan-box', timeout=30000)

            logger.info("等待二维码加载...")
            # 多种方式尝试获取二维码
            qr_img = None
            for selector in ['.login-scan-box img', 'img[src*="qr"]',
                             'xpath=/html/body/div[5]/div/div[2]/div[2]/div[1]/div/img']:
                try:
                    qr_img = await page.wait_for_selector(selector, timeout=5000)
                    break
                except:
                    continue

            if not qr_img:
                logger.error("无法找到二维码")
                return None

            # 保存二维码
            await qr_img.screenshot(path=str(self.qr_file))
            logger.info(f"二维码已保存到: {self.qr_file.absolute()}")
            try:
                from developTools.message.message_components import Image
                #print(bot.master,type(bot.master))
                if group_id is not None:
                    recall_id1=await bot.send_group_message(group_id, Image(file=str(self.qr_file.absolute())))
                    recall_id2=await bot.send_group_message(group_id, "请使用bilibili扫描二维码登录...")
                elif group_id is None:
                    await bot.send_friend_message(bot.master,Image(file=str(self.qr_file.absolute())))
                    await bot.send_friend_message(bot.master,"请使用bilibili扫描二维码登录...")
                is_login_check = False
            except:
                traceback.print_exc()
            logger.info("请扫描二维码登录...")

            # 等待登录成功
            login_success = await self._wait_for_login_success(page)
            if login_success:
                logger.info("登录成功！正在获取cookies...")
                if bot is not None:
                    if group_id is not None:
                        await bot.recall(recall_id1['data']['message_id'])
                        await bot.recall(recall_id2['data']['message_id'])
                        await bot.send_group_message(group_id, "登录成功！")
                    elif group_id is None:
                        await bot.send_friend_message(bot.master,"登录成功！")
                cookies = await page.context.cookies()
                bilibili_cookies = [cookie for cookie in cookies if 'bilibili.com' in cookie['domain']]

                # 记录重要Cookie信息
                important_cookies = ['SESSDATA', 'bili_jct', 'DedeUserID']
                for cookie in bilibili_cookies:
                    if cookie['name'] in important_cookies:
                        logger.info(f"{cookie['name']}: {cookie['value'][:20]}...")

                return bilibili_cookies
            else:
                logger.error("登录超时")
                return None

        except Exception as e:
            logger.error(f"登录过程出错: {e}")
            print(self.qr_file)
            return None
        finally:
            if page:
                try:
                    await page.close()
                except Exception as e:
                    logger.warning(f"关闭登录页面时出错: {e}")

    async def _wait_for_login_success(self, page: Page, timeout: int = 300) -> bool:
        """等待登录成功"""
        start_time = time.time()

        while (time.time() - start_time) < timeout:
            try:
                # 检查登录状态的多种方式
                current_url = page.url
                if 'space.bilibili.com' in current_url:
                    return True

                user_avatar = await page.query_selector('.header-avatar-wrap')
                if user_avatar:
                    return True

                # 检查登录弹窗是否消失
                login_popup = await page.query_selector('.login-scan-box')
                if not login_popup:
                    await page.reload(wait_until='networkidle')
                    user_info = await page.query_selector('.header-avatar-wrap')
                    if user_info:
                        return True

                await asyncio.sleep(2)

            except Exception as e:
                logger.warning(f"检测登录状态时出错: {e}")
                await asyncio.sleep(2)

        return False

    async def start_background_monitor(self):
        """启动后台监控任务，定期检查Cookie有效性"""
        if self._background_task and not self._background_task.done():
            return

        self._background_task = asyncio.create_task(self._background_monitor())
        logger.info("后台Cookie监控已启动")

    async def _background_monitor(self):
        """后台监控任务"""
        while True:
            try:
                await asyncio.sleep(self.update_interval)

                if self.is_updating:
                    continue

                logger.info("开始定期Cookie有效性检查...")
                self.is_updating = True

                if not await self._validate_cookies():
                    logger.info("Cookie失效，尝试自动更新...")
                    new_cookies = await self._login_and_get_cookies()
                    if new_cookies:
                        self.cookies = new_cookies
                        await self._save_cookies()
                        logger.info("Cookie自动更新成功")
                    else:
                        logger.error("Cookie自动更新失败")
                else:
                    logger.info("Cookie仍然有效")

                self.is_updating = False

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"后台监控任务出错: {e}")
                self.is_updating = False

    def get_cookie_dict(self) -> Dict[str, str]:
        """获取Cookie字典格式"""
        cookie_dict = {}
        for cookie in self.cookies:
            cookie_dict[cookie['name']] = cookie['value']
        return cookie_dict

    def get_cookie_string(self) -> str:
        """获取Cookie字符串格式"""
        cookie_pairs = []
        for cookie in self.cookies:
            cookie_pairs.append(f"{cookie['name']}={cookie['value']}")
        return '; '.join(cookie_pairs)

    async def force_refresh_cookies(self) -> bool:
        """强制刷新Cookie"""
        logger.info("强制刷新Cookie...")
        async with self._lock:
            cookies = await self._login_and_get_cookies()
            if cookies:
                self.cookies = cookies
                await self._save_cookies()
                return True
            return False


# 便捷函数
async def get_bili_cookies(auto_login: bool = True,bot=None,check=True) -> List[Dict[str, Any]]:
    """
    获取B站Cookie的便捷函数

    Args:
        auto_login: 如果Cookie无效，是否自动登录

    Returns:
        Cookie列表
    """
    async with BiliCookieManager() as manager:
        cookies = await manager.get_cookies(auto_login,bot,check_cookie=check)
        await manager._cleanup()
        return cookies


# 使用示例
async def example():
    """使用示例"""
    cookies = await get_bili_cookies()
    logger.info(f"便捷函数获取到 {len(cookies)} 个Cookie")
    print(cookies)



if __name__ == "__main__":
    asyncio.run(example())