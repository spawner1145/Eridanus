import os
import sys
import asyncio
import importlib
import importlib.util
from pathlib import Path
from typing import Dict, List, Callable, Any
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import logging
from threading import Lock
from concurrent.futures import ThreadPoolExecutor

from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.utils.system_logger import get_logger


class PluginManager:
    def __init__(self, bot: ExtendBot, config: YAMLManager, plugins_dir: str = "run"):
        self.bot = bot
        self.config = config
        self.plugins_dir = Path(plugins_dir)
        self.loaded_plugins: Dict[str, Dict] = {}
        self.plugin_lock = Lock()
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.observer = None

        # 设置日志
        self.logger = get_logger("PluginManager")

        # 确保插件目录存在
        self.plugins_dir.mkdir(exist_ok=True)

    async def start(self):
        """启动插件管理器"""
        self.logger.info("启动插件管理器...")

        # 初始加载所有插件
        await self.load_all_plugins()

        # 启动文件监控
        self.start_file_watcher()

    async def stop(self):
        """停止插件管理器"""
        self.logger.info("停止插件管理器...")

        if self.observer:
            self.observer.stop()
            self.observer.join()

        self.executor.shutdown(wait=True)

    def start_file_watcher(self):
        """启动文件监控以支持热重载"""

        class PluginFileHandler(FileSystemEventHandler):
            def __init__(self, plugin_manager):
                self.plugin_manager = plugin_manager

            def on_modified(self, event):
                if event.is_directory:
                    return

                file_path = Path(event.src_path)
                # 只监控run目录下第一层插件目录的__init__.py文件
                if (file_path.name.lower() == '__init__.py' and
                        file_path.parent.parent == self.plugin_manager.plugins_dir):
                    plugin_name = file_path.parent.name
                    self.plugin_manager.logger.info(f"检测到插件 {plugin_name} 的 __init__.py 文件变化，准备重载...")

                    # 使用异步方式重载插件
                    asyncio.create_task(self.plugin_manager.reload_plugin(plugin_name))

        self.observer = Observer()
        # 只监控run目录，不递归监控子目录
        self.observer.schedule(
            PluginFileHandler(self),
            str(self.plugins_dir),
            recursive=False  # 关键：设置为False，只监控第一层
        )
        self.observer.start()
        self.logger.info("文件监控已启动（仅监控插件目录第一层）")

    async def load_all_plugins(self):
        """加载所有插件"""
        self.logger.info("开始加载所有插件...")

        # 只检查run文件夹下第一层的目录，不递归
        plugin_dirs = [d for d in self.plugins_dir.iterdir()
                       if d.is_dir() and not d.name.startswith('.')]

        # 使用异步方式并发加载插件
        tasks = []
        for plugin_dir in plugin_dirs:
            # 确保该目录有__init__.py文件才加载
            if (plugin_dir / "__init__.py").exists():
                task = self.load_plugin(plugin_dir.name)
                tasks.append(task)
            else:
                self.logger.debug(f"跳过目录 '{plugin_dir.name}' - 缺少 __init__.py 文件")

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 统计加载结果
            success_count = sum(1 for r in results if r is True)
            self.logger.info(f"插件加载完成: 成功 {success_count}/{len(tasks)}")
        else:
            self.logger.info("未找到可加载的插件")

    async def load_plugin(self, plugin_name: str) -> bool:
        """加载单个插件"""
        try:
            plugin_dir = self.plugins_dir / plugin_name
            init_file = plugin_dir / "__init__.py"

            if not init_file.exists():
                self.logger.warning(f"插件 {plugin_name} 缺少 __init__.py 文件")
                return False

            # 使用线程池执行导入操作，避免阻塞
            loop = asyncio.get_event_loop()
            plugin_info = await loop.run_in_executor(
                self.executor,
                self._import_plugin,
                plugin_name,
                str(init_file)
            )

            if not plugin_info:
                return False

            # 执行插件的入口函数
            await self._execute_plugin_functions(plugin_name, plugin_info)

            with self.plugin_lock:
                self.loaded_plugins[plugin_name] = plugin_info

            self.logger.info(f"插件 {plugin_name} 加载成功")
            return True

        except Exception as e:
            self.logger.error(f"加载插件 {plugin_name} 失败: {str(e)}")
            return False

    def _import_plugin(self, plugin_name: str, init_file_path: str) -> Dict:
        """导入插件模块（在线程池中执行）"""
        try:
            # 构造模块名
            module_name = f"run.{plugin_name}"

            # 如果模块已经导入过，先移除
            if module_name in sys.modules:
                del sys.modules[module_name]

            # 动态导入模块
            spec = importlib.util.spec_from_file_location(module_name, init_file_path)
            if not spec or not spec.loader:
                raise ImportError(f"无法创建模块规格: {module_name}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # 获取 entrance_func
            if not hasattr(module, 'entrance_func'):
                raise AttributeError(f"插件 {plugin_name} 的 __init__.py 缺少 entrance_func 变量")

            entrance_func = getattr(module, 'entrance_func')
            if not isinstance(entrance_func, list):
                raise TypeError(f"插件 {plugin_name} 的 entrance_func 必须是列表类型")

            return {
                'module': module,
                'entrance_func': entrance_func,
                'module_name': module_name
            }

        except Exception as e:
            self.logger.error(f"导入插件 {plugin_name} 失败: {str(e)}")
            return None

    async def _execute_plugin_functions(self, plugin_name: str, plugin_info: Dict):
        """执行插件的入口函数"""
        entrance_funcs = plugin_info['entrance_func']

        for func in entrance_funcs:
            try:
                if callable(func):
                    # 在独立线程中执行插件函数，避免事件循环冲突
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        self.executor,
                        self._run_plugin_function,
                        func,
                        self.bot,
                        self.config
                    )
                    self.logger.debug(f"插件 {plugin_name} 的函数 {func.__name__} 执行成功")
                else:
                    self.logger.warning(f"插件 {plugin_name} 的 entrance_func 中包含非可调用对象: {func}")

            except Exception as e:
                self.logger.error(f"执行插件 {plugin_name} 的函数 {func} 失败: {str(e)}")

    def _run_plugin_function(self, func, bot, config):
        """在线程池中运行插件函数"""
        try:
            # 如果是异步函数，创建新的事件循环来运行
            if asyncio.iscoroutinefunction(func):
                # 创建新的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(func(bot, config))
                finally:
                    loop.close()
            else:
                # 同步函数直接调用
                func(bot, config)

        except Exception as e:
            self.logger.error(f"插件函数执行失败: {str(e)}")
            raise

    async def reload_plugin(self, plugin_name: str):
        """重载指定插件"""
        self.logger.info(f"开始重载插件: {plugin_name}")

        try:
            # 先卸载插件
            await self.unload_plugin(plugin_name)

            # 等待一小段时间确保卸载完成
            await asyncio.sleep(0.1)

            # 重新加载插件
            success = await self.load_plugin(plugin_name)

            if success:
                self.logger.info(f"插件 {plugin_name} 重载成功")
            else:
                self.logger.error(f"插件 {plugin_name} 重载失败")

        except Exception as e:
            self.logger.error(f"重载插件 {plugin_name} 时发生错误: {str(e)}")

    async def unload_plugin(self, plugin_name: str):
        """卸载指定插件"""
        try:
            with self.plugin_lock:
                if plugin_name in self.loaded_plugins:
                    plugin_info = self.loaded_plugins[plugin_name]
                    module_name = plugin_info['module_name']

                    # 从系统模块中移除
                    if module_name in sys.modules:
                        del sys.modules[module_name]

                    # 移除相关的子模块
                    modules_to_remove = [
                        name for name in sys.modules.keys()
                        if name.startswith(f"run.{plugin_name}.")
                    ]
                    for mod_name in modules_to_remove:
                        del sys.modules[mod_name]

                    del self.loaded_plugins[plugin_name]
                    self.logger.info(f"插件 {plugin_name} 已卸载")

        except Exception as e:
            self.logger.error(f"卸载插件 {plugin_name} 失败: {str(e)}")

    async def reload_all_plugins(self):
        """重载所有插件"""
        self.logger.info("开始重载所有插件...")

        plugin_names = list(self.loaded_plugins.keys())

        for plugin_name in plugin_names:
            await self.reload_plugin(plugin_name)

        self.logger.info("所有插件重载完成")

    def get_loaded_plugins(self) -> List[str]:
        """获取已加载的插件列表"""
        with self.plugin_lock:
            return list(self.loaded_plugins.keys())

    async def get_plugin_status(self) -> Dict[str, Dict]:
        """获取插件状态信息"""
        status = {}

        # 只扫描run目录下第一层的插件目录
        plugin_dirs = [d for d in self.plugins_dir.iterdir()
                       if d.is_dir() and not d.name.startswith('.')]

        for plugin_dir in plugin_dirs:
            plugin_name = plugin_dir.name
            init_file = plugin_dir / "__init__.py"

            status[plugin_name] = {
                'loaded': plugin_name in self.loaded_plugins,
                'has_init': init_file.exists(),
                'path': str(plugin_dir)
            }

            if plugin_name in self.loaded_plugins:
                plugin_info = self.loaded_plugins[plugin_name]
                status[plugin_name]['entrance_func_count'] = len(plugin_info['entrance_func'])

        return status


# 完整的使用示例
class BotApplication:
    def __init__(self, bot: ExtendBot, config: YAMLManager):
        self.bot = bot
        self.config = config
        self.plugin_manager = PluginManager(bot, config)
        self.running = False

    async def start(self):
        """启动应用程序"""
        self.logger = logging.getLogger(__name__)
        self.logger.info("启动Bot应用程序...")

        # 启动插件管理器
        await self.plugin_manager.start()

        # 设置运行标志
        self.running = True

        # 启动bot（这里假设bot有start方法）
        if hasattr(self.bot, 'start'):
            await self.bot.start()

        self.logger.info("Bot应用程序启动完成")

    async def run(self):
        """运行应用程序主循环"""
        while self.running:
            try:
                # 这里可以添加其他定期任务
                await asyncio.sleep(1)

                # 如果bot断开连接，可以在这里处理重连逻辑
                if hasattr(self.bot, 'is_connected') and not self.bot.is_connected():
                    self.logger.warning("Bot连接断开，尝试重连...")
                    if hasattr(self.bot, 'reconnect'):
                        await self.bot.reconnect()

            except KeyboardInterrupt:
                self.logger.info("收到中断信号，正在停止...")
                break
            except Exception as e:
                self.logger.error(f"运行时错误: {str(e)}")
                await asyncio.sleep(5)  # 错误后等待5秒再继续

    async def stop(self):
        """停止应用程序"""
        self.logger.info("正在停止应用程序...")
        self.running = False

        # 停止插件管理器
        await self.plugin_manager.stop()

        # 停止bot
        if hasattr(self.bot, 'stop'):
            await self.bot.stop()

        self.logger.info("应用程序已停止")


# 使用示例
async def main():
    """使用示例"""
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 假设你已经有了 bot 和 config 实例
    # bot = ExtendBot()
    # config = YAMLManager()

    # 创建应用程序实例
    # app = BotApplication(bot, config)

    # 启动应用程序
    # await app.start()

    # 运行应用程序（这会持续运行直到收到停止信号）
    # try:
    #     await app.run()
    # finally:
    #     await app.stop()

    # 或者，如果你只想使用插件管理器：
    # plugin_manager = PluginManager(bot, config)
    # await plugin_manager.start()

    # 保持程序运行（在实际使用中，bot的事件循环会保持程序运行）
    # while True:
    #     await asyncio.sleep(1)

    pass


if __name__ == "__main__":
    asyncio.run(main())