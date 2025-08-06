import subprocess
import sys
import os
import threading

from developTools.utils.logger import get_logger

logger=get_logger("PlaywrightAutoInstaller")
def check_and_install_playwright():
    """检查并自动安装Playwright浏览器"""

    def install_playwright():
        try:
            logger.info("检查Playwright Chromium安装状态...")
            # 尝试运行playwright install检查
            result = subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'],
                                    capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                logger.info("Playwright Chromium安装完成")
            else:
                logger.warning(f"Playwright安装可能失败: {result.stderr}")
        except subprocess.TimeoutExpired:
            logger.warning("Playwright安装超时")
        except Exception as e:
            logger.error(f"安装Playwright时出错: {e}")

    try:
        # 快速检查playwright命令是否可用
        subprocess.run([sys.executable, '-m', 'playwright', '--help'],
                       capture_output=True, timeout=5)
        # 非阻塞方式在后台安装
        threading.Thread(target=install_playwright, daemon=True).start()
    except:
        logger.warning("Playwright未正确安装，请手动运行: playwright install chromium")