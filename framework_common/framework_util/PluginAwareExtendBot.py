import gc
import os
import sys
import asyncio
import importlib
import importlib.util
import traceback

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Callable, Any, Set
import time
import weakref

import psutil
from watchdog.watchmedo import load_config

from framework_common.utils.install_and_import import install_and_import

watchdog = install_and_import("watchdog")
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import logging
from threading import Lock
from concurrent.futures import ThreadPoolExecutor

from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.utils.system_logger import get_logger


class LoadStrategy(Enum):
    """插件加载策略"""
    ALL_AT_ONCE = "all_at_once"
    BATCH_LOADING = "batch_loading"
    MEMORY_AWARE = "memory_aware"


@dataclass
class PluginLoadConfig:
    """插件加载配置"""
    batch_size: int = 4  # 每批加载的插件数量
    batch_delay: float| int = 2.0  # 批次间延迟（秒）
    max_retries: int = 3  # 最大重试次数
    retry_delay: float | int = 1.0  # 重试延迟（秒）
    memory_threshold_mb: int = 100  # 内存阈值（MB）
    enable_gc_between_batches: bool = True  # 批次间是否强制垃圾回收
    load_strategy: LoadStrategy = LoadStrategy.BATCH_LOADING


@dataclass
class PluginLoadResult:
    """插件加载结果"""
    plugin_name: str
    success: bool
    error: str = None
    retry_count: int = 0
    load_time: float = 0.0
    memory_used: float = 0.0


class MemoryMonitor:
    """内存监控器"""

    @staticmethod
    def get_memory_usage() -> float:
        try:
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except:
            return 0.0

    @staticmethod
    def get_available_memory() -> float:
        try:
            return psutil.virtual_memory().available / 1024 / 1024
        except:
            return 1000.0

    @staticmethod
    def is_memory_sufficient(threshold_mb: int = 100) -> bool:
        return MemoryMonitor.get_available_memory() > threshold_mb
class PluginAwareExtendBot(ExtendBot):
    """继承ExtendBot，添加插件感知的事件管理功能"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 插件名 -> {事件类型: {处理器函数}}
        self._plugin_handlers: Dict[str, Dict[type, Set[Callable]]] = {}
        self._current_plugin: str = None
        self._handler_lock = Lock()

    def _set_current_plugin(self, plugin_name: str):
        """设置当前正在加载的插件名（内部使用）"""
        self._current_plugin = plugin_name

    def _clear_current_plugin(self):
        """清除当前插件名（内部使用）"""
        self._current_plugin = None

    def on(self, event):
        """重写on方法，添加插件感知功能"""

        def decorator(func):
            # 先调用父类的on方法注册事件
            result = super(PluginAwareExtendBot, self).on(event)(func)

            # 如果在插件上下文中，记录这个处理器
            if self._current_plugin:
                with self._handler_lock:
                    plugin_name = self._current_plugin
                    if plugin_name not in self._plugin_handlers:
                        self._plugin_handlers[plugin_name] = {}
                    if event not in self._plugin_handlers[plugin_name]:
                        self._plugin_handlers[plugin_name][event] = set()
                    self._plugin_handlers[plugin_name][event].add(func)

            return result

        return decorator

    def _unload_plugin_handlers(self, plugin_name: str):
        """卸载指定插件的所有事件处理器（内部使用）"""
        with self._handler_lock:
            if plugin_name not in self._plugin_handlers:
                return 0

            handler_count = 0
            plugin_handlers_map = self._plugin_handlers[plugin_name]

            for event_type, handlers in plugin_handlers_map.items():
                if event_type in self.event_bus.handlers:
                    # 从事件总线中移除这些处理器
                    for handler in handlers:
                        self.event_bus.handlers[event_type].discard(handler)
                        handler_count += 1

                    # 如果该事件类型没有处理器了，清理空集合
                    if not self.event_bus.handlers[event_type]:
                        del self.event_bus.handlers[event_type]

            # 清理插件的处理器记录
            del self._plugin_handlers[plugin_name]
            return handler_count

    def _get_plugin_handlers_count(self, plugin_name: str) -> int:
        """获取插件注册的处理器数量（内部使用）"""
        with self._handler_lock:
            if plugin_name not in self._plugin_handlers:
                return 0
            return sum(len(handlers) for handlers in self._plugin_handlers[plugin_name].values())


class PluginManager:
    def __init__(self, bot: ExtendBot, config: YAMLManager,
                 plugins_dir: str = "run",
                 load_config: PluginLoadConfig = None):
        # 如果传入的不是PluginAwareExtendBot，则需要动态增强原bot
        if isinstance(bot, PluginAwareExtendBot):
            self.bot = bot
        else:
            # 直接在原bot实例上添加插件感知功能，而不是创建新实例
            self._enhance_bot_instance(bot)
            self.bot = bot

        self.config = config
        self.plugins_dir = Path(plugins_dir)
        self.loaded_plugins: Dict[str, Dict] = {}
        self.plugin_lock = Lock()
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.observer = None

        # 文件修改时间缓存，用于防止重复热重载
        self._file_mod_times: Dict[str, float] = {}
        self._reload_debounce_time = 0.5  # 防抖时间（秒）

        # 设置日志
        self.logger = get_logger("PluginManager")

        # 确保插件目录存在
        self.plugins_dir.mkdir(exist_ok=True)

        # 添加新属性
        self.load_config = load_config or PluginLoadConfig()
        self.failed_plugins: Dict[str, PluginLoadResult] = {}
        self.memory_monitor = MemoryMonitor()
        self.load_statistics = {
            'total_attempts': 0,
            'successful_loads': 0,
            'failed_loads': 0,
            'retry_count': 0,
            'total_memory_used': 0.0
        }

    def _enhance_bot_instance(self, bot: ExtendBot):
        """动态增强现有bot实例，添加插件感知功能"""
        # 添加插件相关属性
        bot._plugin_handlers = {}
        bot._current_plugin = None
        bot._handler_lock = Lock()

        # 保存原始的on方法
        bot._original_on = bot.on

        # 定义新的on方法
        def enhanced_on(event):
            def decorator(func):
                # 先调用原始的on方法注册事件
                result = bot._original_on(event)(func)

                # 如果在插件上下文中，记录这个处理器
                if hasattr(bot, '_current_plugin') and bot._current_plugin:
                    with bot._handler_lock:
                        plugin_name = bot._current_plugin
                        if plugin_name not in bot._plugin_handlers:
                            bot._plugin_handlers[plugin_name] = {}
                        if event not in bot._plugin_handlers[plugin_name]:
                            bot._plugin_handlers[plugin_name][event] = set()
                        bot._plugin_handlers[plugin_name][event].add(func)

                return result

            return decorator

        # 定义插件管理方法
        def _set_current_plugin(plugin_name: str):
            bot._current_plugin = plugin_name

        def _clear_current_plugin():
            bot._current_plugin = None

        def _unload_plugin_handlers(plugin_name: str):
            """改进的处理器清理方法"""
            if not hasattr(bot, '_plugin_handlers'):
                return 0

            with bot._handler_lock:
                handler_count = 0

                # 方法1: 使用插件记录的方式清理
                if plugin_name in bot._plugin_handlers:
                    plugin_handlers_map = bot._plugin_handlers[plugin_name]
                    self.logger.debug(f"开始清理插件 {plugin_name} 的事件处理器")

                    for event_type, handlers in plugin_handlers_map.items():
                        self.logger.debug(f"事件类型 {event_type.__name__}: 需要清理 {len(handlers)} 个处理器")

                        if event_type in bot.event_bus.handlers:
                            original_count = len(bot.event_bus.handlers[event_type])

                            # 从事件总线中移除这些处理器
                            for handler in handlers:
                                if handler in bot.event_bus.handlers[event_type]:
                                    bot.event_bus.handlers[event_type].discard(handler)
                                    handler_count += 1
                                    self.logger.debug(f"已移除处理器: {handler.__name__}")

                            final_count = len(bot.event_bus.handlers[event_type])
                            self.logger.debug(
                                f"事件类型 {event_type.__name__}: 清理前 {original_count} 个，清理后 {final_count} 个")

                            # 如果该事件类型没有处理器了，清理空集合
                            if not bot.event_bus.handlers[event_type]:
                                del bot.event_bus.handlers[event_type]
                                self.logger.debug(f"已删除空的事件类型: {event_type.__name__}")

                    # 清理插件的处理器记录
                    del bot._plugin_handlers[plugin_name]

                # 方法2: 强制按模块名清理（备用方案）
                force_cleared = _force_clear_all_handlers_for_plugin(plugin_name)
                handler_count += force_cleared

                if force_cleared > 0:
                    self.logger.warning(f"强制清理了额外的 {force_cleared} 个处理器")

                self.logger.debug(f"插件 {plugin_name} 的处理器清理完成，共清理 {handler_count} 个")
                return handler_count

        def _force_clear_all_handlers_for_plugin(plugin_name: str):
            """强制清理插件的所有处理器（按模块名匹配）"""
            if not hasattr(bot, 'event_bus') or not hasattr(bot.event_bus, 'handlers'):
                return 0

            cleared_count = 0
            module_prefix = f"run.{plugin_name}"

            # 遍历所有事件类型的处理器
            for event_type in list(bot.event_bus.handlers.keys()):
                handlers_to_remove = set()

                for handler in list(bot.event_bus.handlers[event_type]):
                    # 检查处理器所属的模块
                    if hasattr(handler, '__module__') and handler.__module__:
                        if (handler.__module__.startswith(module_prefix + ".") or
                                handler.__module__ == module_prefix):
                            handlers_to_remove.add(handler)

                # 移除找到的处理器
                for handler in handlers_to_remove:
                    if handler in bot.event_bus.handlers[event_type]:
                        bot.event_bus.handlers[event_type].discard(handler)
                        cleared_count += 1
                        self.logger.debug(f"强制清理处理器: {handler.__name__} (模块: {handler.__module__})")

                # 如果该事件类型没有处理器了，清理空集合
                if not bot.event_bus.handlers[event_type]:
                    del bot.event_bus.handlers[event_type]

            return cleared_count

        def _get_plugin_handlers_count(plugin_name: str) -> int:
            if not hasattr(bot, '_plugin_handlers'):
                return 0
            with bot._handler_lock:
                if plugin_name not in bot._plugin_handlers:
                    return 0
                return sum(len(handlers) for handlers in bot._plugin_handlers[plugin_name].values())

        # 动态添加方法到bot实例
        bot.on = enhanced_on
        bot._set_current_plugin = _set_current_plugin
        bot._clear_current_plugin = _clear_current_plugin
        bot._unload_plugin_handlers = _unload_plugin_handlers
        bot._get_plugin_handlers_count = _get_plugin_handlers_count
        bot._force_clear_all_handlers_for_plugin = _force_clear_all_handlers_for_plugin

    async def start(self):
        """启动插件管理器"""
        self.logger.info(f"启动优化插件管理器 (策略: {self.load_config.load_strategy.value})")

        # 记录初始内存使用
        initial_memory = self.memory_monitor.get_memory_usage()
        self.logger.info(f"初始内存使用: {initial_memory:.2f} MB")

        # 根据策略加载插件
        if self.load_config.load_strategy == LoadStrategy.BATCH_LOADING:
            await self.batch_load_all_plugins()
        elif self.load_config.load_strategy == LoadStrategy.MEMORY_AWARE:
            await self.memory_aware_load_plugins()
        else:
            await self.load_all_plugins()

        # 启动文件监控
        self.start_file_watcher()

        # 输出加载统计
        self._log_load_statistics()

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

                # 监控插件目录下的所有.py文件变化
                if (file_path.suffix.lower() == '.py' and
                        self._is_plugin_file(file_path)):

                    plugin_name = self._get_plugin_name_from_path(file_path)
                    if plugin_name: #and plugin_name not in self.plugin_manager._reloading_plugins:
                        # 防抖处理
                        current_time = time.time()
                        file_key = str(file_path)

                        if (file_key in self.plugin_manager._file_mod_times and
                                current_time - self.plugin_manager._file_mod_times[file_key] <
                                self.plugin_manager._reload_debounce_time):
                            return

                        self.plugin_manager._file_mod_times[file_key] = current_time

                        self.plugin_manager.logger.info(
                            f"检测到插件 {plugin_name} 的文件 {file_path.name} 变化，准备重载...")

                        # 使用线程安全的方式调度重载任务
                        self.plugin_manager._schedule_reload(plugin_name)

            def _is_plugin_file(self, file_path: Path) -> bool:
                """检查是否是插件相关的文件"""
                try:
                    # 确保文件在run目录下的某个插件目录中
                    relative_path = file_path.relative_to(self.plugin_manager.plugins_dir)
                    parts = relative_path.parts

                    # 至少要有两个部分：插件目录名和文件名
                    if len(parts) >= 2:
                        plugin_dir = self.plugin_manager.plugins_dir / parts[0]
                        return plugin_dir.is_dir() and (plugin_dir / "__init__.py").exists()

                    return False
                except ValueError:
                    # 文件不在plugins_dir中
                    return False

            def _get_plugin_name_from_path(self, file_path: Path) -> str:
                """从文件路径提取插件名"""
                try:
                    relative_path = file_path.relative_to(self.plugin_manager.plugins_dir)
                    return relative_path.parts[0]  # 第一部分就是插件目录名
                except (ValueError, IndexError):
                    return None

        self.observer = Observer()
        # 递归监控run目录及其子目录
        self.observer.schedule(
            PluginFileHandler(self),
            str(self.plugins_dir),
            recursive=True  # 改为True，监控所有子目录
        )
        self.observer.start()
        self.logger.info("文件监控已启动（递归监控所有插件文件）")



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

    async def batch_load_all_plugins(self):
        """分批加载所有插件"""
        self.logger.info("开始分批加载插件...")

        all_plugins = self._discover_plugins()
        if not all_plugins:
            self.logger.info("未找到可加载的插件")
            return

        total_batches = (len(all_plugins) + self.load_config.batch_size - 1) // self.load_config.batch_size

        for batch_idx in range(total_batches):
            start_idx = batch_idx * self.load_config.batch_size
            end_idx = min(start_idx + self.load_config.batch_size, len(all_plugins))
            batch_plugins = all_plugins[start_idx:end_idx]

            self.logger.info(f"加载批次 {batch_idx + 1}/{total_batches}: {batch_plugins}")

            # 检查内存是否充足
            if not self.memory_monitor.is_memory_sufficient(self.load_config.memory_threshold_mb):
                self.logger.warning(f"内存不足，跳过批次 {batch_idx + 1}")
                continue

            # 并发加载当前批次的插件
            batch_tasks = [self.load_plugin_with_retry(name) for name in batch_plugins]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            # 统计批次结果
            successful_in_batch = sum(1 for r in batch_results if isinstance(r, PluginLoadResult) and r.success)
            self.logger.info(f"批次 {batch_idx + 1} 完成: {successful_in_batch}/{len(batch_plugins)} 成功")

            # 批次间清理和延迟
            if batch_idx < total_batches - 1:
                if self.load_config.enable_gc_between_batches:
                    await self._force_garbage_collection()

                if self.load_config.batch_delay > 0:
                    await asyncio.sleep(self.load_config.batch_delay)

    async def memory_aware_load_plugins(self):
        """内存感知的插件加载"""
        self.logger.info("开始内存感知加载插件...")

        all_plugins = self._discover_plugins()
        loaded_count = 0

        for plugin_name in all_plugins:
            # 检查可用内存
            available_memory = self.memory_monitor.get_available_memory()

            if available_memory < self.load_config.memory_threshold_mb:
                self.logger.warning(f"内存不足 ({available_memory:.2f}MB)，暂停加载插件 {plugin_name}")

                # 尝试垃圾回收释放内存
                await self._force_garbage_collection()

                # 重新检查内存
                available_memory = self.memory_monitor.get_available_memory()
                if available_memory < self.load_config.memory_threshold_mb:
                    self.logger.error(f"内存回收后仍不足，跳过插件 {plugin_name}")
                    continue

            # 加载插件
            result = await self.load_plugin_with_retry(plugin_name)
            if result.success:
                loaded_count += 1
                self.logger.info(f"已加载 {loaded_count}/{len(all_plugins)} 个插件")

            await asyncio.sleep(0.1)  # 小延迟

    async def load_plugin_with_retry(self, plugin_name: str) -> PluginLoadResult:
        """带重试机制的插件加载"""
        result = PluginLoadResult(plugin_name=plugin_name, success=False)

        for attempt in range(self.load_config.max_retries + 1):
            try:
                start_time = time.time()
                memory_before = self.memory_monitor.get_memory_usage()

                success = await self.load_plugin(plugin_name)

                if success:
                    result.success = True
                    result.load_time = time.time() - start_time
                    result.memory_used = self.memory_monitor.get_memory_usage() - memory_before
                    result.retry_count = attempt

                    self.load_statistics['successful_loads'] += 1
                    self.load_statistics['total_memory_used'] += result.memory_used
                    return result
                else:
                    raise Exception(f"插件 {plugin_name} 加载失败，load_plugin返回False")

            except Exception as e:
                result.error = str(e)
                result.retry_count = attempt

                self.logger.warning(
                    f"插件 {plugin_name} 加载失败 (尝试 {attempt + 1}/{self.load_config.max_retries + 1}): {str(e)}")

                if attempt < self.load_config.max_retries:
                    await self._force_garbage_collection()
                    await asyncio.sleep(self.load_config.retry_delay * (attempt + 1))
                    self.load_statistics['retry_count'] += 1

        # 所有重试都失败了
        self.failed_plugins[plugin_name] = result
        self.load_statistics['failed_loads'] += 1
        self.logger.error(f"插件 {plugin_name} 加载最终失败")
        return result

    def _discover_plugins(self) -> List[str]:
        """发现所有可加载的插件"""
        plugin_dirs = [d for d in self.plugins_dir.iterdir()
                       if d.is_dir() and not d.name.startswith('.')]

        plugins = []
        for plugin_dir in plugin_dirs:
            if (plugin_dir / "__init__.py").exists():
                plugins.append(plugin_dir.name)
        return plugins

    async def _force_garbage_collection(self):
        """强制垃圾回收"""
        loop = asyncio.get_event_loop()

        def gc_task():
            collected = 0
            for i in range(3):
                round_collected = gc.collect()
                collected += round_collected
                if round_collected == 0:
                    break
            return collected

        collected = await loop.run_in_executor(self.executor, gc_task)
        if collected > 0:
            memory_after = self.memory_monitor.get_memory_usage()
            self.logger.debug(f"垃圾回收: 回收了 {collected} 个对象，当前内存: {memory_after:.2f} MB")

    def _log_load_statistics(self):
        """输出加载统计信息"""
        stats = self.load_statistics
        current_memory = self.memory_monitor.get_memory_usage()

        self.logger.info("=== 插件加载统计 ===")
        self.logger.info(f"成功加载: {stats['successful_loads']}")
        self.logger.info(f"加载失败: {stats['failed_loads']}")
        self.logger.info(f"重试次数: {stats['retry_count']}")
        self.logger.info(f"当前内存: {current_memory:.2f} MB")

        if self.failed_plugins:
            self.logger.warning(f"失败的插件: {list(self.failed_plugins.keys())}")

    async def retry_failed_plugins(self):
        """重试所有失败的插件"""
        if not self.failed_plugins:
            self.logger.info("没有失败的插件需要重试")
            return

        failed_list = list(self.failed_plugins.keys())
        self.logger.info(f"开始重试 {len(failed_list)} 个失败的插件")

        self.failed_plugins.clear()

        retry_tasks = [self.load_plugin_with_retry(name) for name in failed_list]
        results = await asyncio.gather(*retry_tasks, return_exceptions=True)

        success_count = sum(1 for r in results if isinstance(r, PluginLoadResult) and r.success)
        self.logger.info(f"重试完成: {success_count}/{len(failed_list)} 个插件成功加载")
    async def load_plugin(self, plugin_name: str) -> bool:
        """加载单个插件"""
        try:
            self.load_statistics['total_attempts'] += 1  # 添加这行
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
                self.logger.warning(f"插件 {plugin_name} 导入失败")
                return False
            #print(plugin_info)
            # 执行插件的入口函数（在插件上下文中）
            await self._execute_plugin_functions(plugin_name, plugin_info)

            with self.plugin_lock:
                self.loaded_plugins[plugin_name] = plugin_info

            # 记录插件注册的处理器数量
            handler_count = self.bot._get_plugin_handlers_count(plugin_name)
            self.logger.info(f"插件 {plugin_name} 加载成功，注册了 {handler_count} 个事件处理器")
            return True

        except Exception as e:
            traceback.print_exc()
            self.logger.error(f"加载插件 {plugin_name} 失败: {str(e)}")
            raise e

    def _clear_plugin_modules_from_cache(self, plugin_name: str):
        """彻底清理插件相关的模块缓存"""
        module_prefix = f"run.{plugin_name}"
        modules_to_remove = []
        self.logger.debug(f"开始清理插件 {plugin_name} 的模块缓存...")
        # 找出所有相关模块
        for module_name in sys.modules.keys():
            if (module_name == module_prefix or
                    module_name.startswith(module_prefix + ".")):
                modules_to_remove.append(module_name)
        self.logger.debug(f"需要清理 {len(modules_to_remove)} 个模块: {modules_to_remove}")
        # 删除模块
        for module_name in modules_to_remove:
            try:
                #print(sys.modules)
                #print(sys.modules[module_name])
                del sys.modules[module_name]
                self.logger.debug(f"已清理模块缓存: {module_name}")
            except KeyError:
                self.logger.error(sys.modules)
                self.logger.error(sys.modules[module_name])
                error_msg = f"模块 {module_name} 不在缓存中"
                self.logger.error(error_msg)

    def _import_plugin(self, plugin_name: str, init_file_path: str) -> Dict:
        """导入插件模块（在线程池中执行）"""
        try:
            # 构造模块名
            module_name = f"run.{plugin_name}"

            # 彻底清理相关模块缓存
            self._clear_plugin_modules_from_cache(plugin_name)

            # 重新导入模块
            spec = importlib.util.spec_from_file_location(module_name, init_file_path)
            if not spec or not spec.loader:
                raise ImportError(f"无法创建模块规格: {module_name}")

            module = importlib.util.module_from_spec(spec)

            # 先加入sys.modules再执行，这样可以处理循环导入
            sys.modules[module_name] = module

            try:
                spec.loader.exec_module(module)
            except Exception as e:
                # 如果执行失败，从sys.modules中移除
                if module_name in sys.modules:
                    del sys.modules[module_name]
                raise e

            # 直接在这里执行 load_main_functions 的逻辑，而不是依赖 __init__.py 中的定义
            entrance_func = self._load_plugin_main_functions(plugin_name, init_file_path)

            # 如果 __init__.py 中已经定义了 entrance_func，则使用它；否则使用我们加载的
            if hasattr(module, 'entrance_func') and isinstance(getattr(module, 'entrance_func'), list):
                entrance_func = getattr(module, 'entrance_func')

            if not entrance_func:
                self.logger.warning(f"插件 {plugin_name} 没有找到可用的 entrance_func")
                entrance_func = []

            return {
                'module': module,
                'entrance_func': entrance_func,
                'module_name': module_name,
                'load_time': time.time()
            }

        except Exception as e:
            traceback.print_exc()
            self.logger.error(f"导入插件 {plugin_name} 失败: {str(e)}")
            # 清理可能残留的模块
            self._clear_plugin_modules_from_cache(plugin_name)
            return None

    def _check_has_main(self, module_name: str) -> tuple[bool, object]:
        """检查模块是否包含 main() 方法"""
        try:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                self.logger.warning(f"⚠️ 未找到模块 {module_name}")
                return False, None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            return hasattr(module, "main") and callable(getattr(module, "main")), module
        except Exception as e:
            self.logger.warning(f"⚠️ 加载模块 {module_name} 失败 {str(e)}")
            return False, None

    def _load_plugin_main_functions(self, plugin_name: str, init_file_path: str) -> List[Callable]:
        """
        从插件目录加载包含 main 函数的模块
        参数 plugin_name: 插件名称
        参数 init_file_path: __init__.py 的文件路径
        返回 entrance_func 列表，包含所有 main 函数
        """
        entrance_func: List[Callable] = []
        module_names: List[str] = []

        # 获取 __init__.py 所在目录
        dir_path = Path(init_file_path).parent
        package = "run"  # 固定为 run
        subpackage = plugin_name  # 当前插件名

        # 遍历目录下的 .py 文件
        for file_path in dir_path.glob("*.py"):
            if file_path.name == "__init__.py":  # 跳过 __init__.py
                continue

            module_name = file_path.stem
            # 构造模块路径（例如 run.a_example.example）
            full_module_name = f"{package}.{subpackage}.{module_name}"

            # 检查是否包含 main 函数
            has_main, module = self._check_has_main(full_module_name)

            if has_main:
                entrance_func.append(module.main)
                module_names.append(module_name)
                self.logger.debug(f"成功导入 {module_name}.main")
            else:
                self.logger.debug(f"跳过 {module_name}：无 callable main 函数")

        # 输出加载结果
        if module_names:
            self.logger.info(f"插件 {plugin_name} 加载了 {len(module_names)} 个 main 函数: {module_names}")
        else:
            self.logger.warning(f"插件 {plugin_name} 未找到任何可用的 main 函数")

        return entrance_func

    async def _execute_plugin_functions(self, plugin_name: str, plugin_info: Dict):
        """执行插件的入口函数"""
        entrance_funcs = plugin_info['entrance_func']

        # 设置插件上下文
        self.bot._set_current_plugin(plugin_name)

        try:
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

        finally:
            # 清理插件上下文
            self.bot._clear_current_plugin()

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
                    # 重要：清理事件循环策略避免内存泄漏
                    asyncio.set_event_loop(None)
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
            self.logger.error(f"插件 {plugin_name} 开始卸载...")
            #self.logger.error(sys.modules)
            #self.logger.error(sys.modules[self.loaded_plugins[plugin_name]['module_name']])
            await self.unload_plugin(plugin_name)

            # 等待一小段时间确保卸载完成
            await asyncio.sleep(1)

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
        self.logger.debug(f"0开始卸载插件: {plugin_name}")
        try:
            with self.plugin_lock:
                if plugin_name in self.loaded_plugins:
                    plugin_info = self.loaded_plugins[plugin_name]
                    module_name = plugin_info['module_name']
                    del sys.modules[module_name]
                    # 获取当前处理器数量并卸载插件的所有事件处理器
                    handler_count = self.bot._unload_plugin_handlers(plugin_name)

                    # 彻底清理模块缓存
                    self.logger.debug(f"插件 {plugin_name} 开始清理模块缓存...")
                    self._clear_plugin_modules_from_cache(plugin_name)

                    del self.loaded_plugins[plugin_name]
                    self.logger.info(f"插件 {plugin_name} 已卸载，清理了 {handler_count} 个事件处理器")

                    # 强制垃圾回收
                    import gc
                    gc.collect()

        except Exception as e:
            self.logger.error(f"卸载插件 {plugin_name} 失败: {str(e)}")

    async def reload_all_plugins(self):
        """重载所有插件 - 最彻底的方案"""
        self.logger.info("开始全量重载所有插件...")

        try:
            # 记录当前加载的插件
            current_plugins = list(self.loaded_plugins.keys())
            total_handlers_before = sum(self.bot._get_plugin_handlers_count(name) for name in current_plugins)

            self.logger.info(f"准备重载 {len(current_plugins)} 个插件，当前总处理器数: {total_handlers_before}")

            # 第一步：卸载所有插件
            for plugin_name in current_plugins:
                try:
                    await self.unload_plugin(plugin_name)
                except Exception as e:
                    self.logger.error(f"卸载插件 {plugin_name} 失败: {e}")

            # 第二步：核弹式清理所有run模块
            self._nuclear_clear_all_run_modules()

            # 第三步：等待确保清理完成
            await asyncio.sleep(1)

            # 第四步：重新加载所有插件
            await self.load_all_plugins()

            # 统计结果
            reloaded_plugins = list(self.loaded_plugins.keys())
            total_handlers_after = sum(self.bot._get_plugin_handlers_count(name) for name in reloaded_plugins)

            success_count = len(reloaded_plugins)
            self.logger.info(f"全量重载完成: {success_count}/{len(current_plugins)} 个插件成功重载")
            self.logger.info(f"事件处理器: {total_handlers_before} -> {total_handlers_after}")

            if success_count < len(current_plugins):
                failed_plugins = set(current_plugins) - set(reloaded_plugins)
                self.logger.warning(f"重载失败的插件: {failed_plugins}")

        except Exception as e:
            self.logger.error(f"全量重载过程中发生错误: {str(e)}")

    def _nuclear_clear_all_run_modules(self):
        """核清理所有run模块"""
        import gc

        self.logger.debug("开始核清理所有run模块...")

        # 找出所有run模块
        run_modules = []
        for module_name in list(sys.modules.keys()):
            if module_name.startswith("run."):
                run_modules.append(module_name)

        self.logger.debug(f"发现 {len(run_modules)} 个run模块需要清理")

        # 按深度倒序清理（子模块先清理）
        run_modules.sort(key=lambda x: x.count('.'), reverse=True)

        # 清理所有run模块
        cleared_count = 0
        for module_name in run_modules:
            try:
                if module_name in sys.modules:
                    module = sys.modules[module_name]

                    # 清空模块内容
                    if hasattr(module, '__dict__'):
                        module.__dict__.clear()

                    # 从缓存删除
                    del sys.modules[module_name]
                    del module
                    cleared_count += 1

            except Exception as e:
                self.logger.debug(f"清理模块 {module_name} 时出错: {e}")

        # 清理importlib缓存
        try:
            if hasattr(importlib, 'invalidate_caches'):
                importlib.invalidate_caches()

            # 清理模块锁
            if hasattr(importlib, '_bootstrap') and hasattr(importlib._bootstrap, '_module_locks'):
                locks_to_clear = []
                for lock_name in list(importlib._bootstrap._module_locks.keys()):
                    if isinstance(lock_name, str) and lock_name.startswith("run."):
                        locks_to_clear.append(lock_name)

                for lock_name in locks_to_clear:
                    try:
                        del importlib._bootstrap._module_locks[lock_name]
                    except KeyError:
                        pass

        except Exception as e:
            self.logger.debug(f"清理importlib缓存时出错: {e}")

        # 强制垃圾回收
        collected = 0
        for i in range(3):
            round_collected = gc.collect()
            collected += round_collected
            if round_collected == 0:
                break

        self.logger.info(f"清理完成: 清理了 {cleared_count} 个模块，回收了 {collected} 个对象")

    def _schedule_reload(self, plugin_name: str):
        """调度全量重载（避免频繁重载）"""

        # 防抖：如果已经有重载任务在进行，就不再创建新的
        if hasattr(self, '_reload_in_progress') and self._reload_in_progress:
            self.logger.debug(f"重载已在进行中，跳过插件 {plugin_name} 的重载请求")
            return

        def reload_task():
            try:
                # 设置重载标志
                self._reload_in_progress = True

                # 获取事件循环
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        raise RuntimeError("Event loop is closed")
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                # 执行全量重载
                if loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        self.reload_plugin(plugin_name), loop)
                    future.result(timeout=60)  # 增加超时时间
                else:
                    loop.run_until_complete(self.reload_plugin(plugin_name))

            except Exception as e:
                self.logger.error(f"全量重载失败: {str(e)}")
            finally:
                # 清除重载标志
                self._reload_in_progress = False

        # 在线程池中执行
        self.executor.submit(reload_task)

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
                'path': str(plugin_dir),
                'event_handlers_count': self.bot._get_plugin_handlers_count(plugin_name)
            }

            if plugin_name in self.loaded_plugins:
                plugin_info = self.loaded_plugins[plugin_name]
                status[plugin_name]['entrance_func_count'] = len(plugin_info['entrance_func'])
                status[plugin_name]['load_time'] = plugin_info.get('load_time', 0)

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