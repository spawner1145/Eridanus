import logging
import os
from datetime import datetime
from logging import Logger
import threading

import colorlog

# 全局变量，用于存储 logger 实例和屏蔽的日志类别
_logger = None
_blocked_loggers = ["INFO_MSG", "DEBUG"]  # 默认禁用DEBUG
_lock = threading.Lock()  # 添加线程锁
_current_log_date = None

class CategoryHandler(logging.StreamHandler):
    """自定义Handler，根据消息类型使用不同的formatter"""

    def __init__(self):
        super().__init__()
        # 为不同类别创建不同的formatter
        self.formatters = {
            'default': self._create_formatter(
                '%(log_color)s%(asctime)s [%(name)s] - %(levelname)s - [bot] %(message)s',
                {'DEBUG': 'white', 'INFO': 'cyan', 'WARNING': 'yellow', 'ERROR': 'red', 'CRITICAL': 'bold_red'}
            ),
            'msg': self._create_formatter(
                '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - [MSG] %(message)s',
                {'DEBUG': 'white', 'INFO': 'green', 'WARNING': 'yellow', 'ERROR': 'red', 'CRITICAL': 'bold_red'}
            ),
            'func': self._create_formatter(
                '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - [FUNC] %(message)s',
                {'DEBUG': 'white', 'INFO': 'blue', 'WARNING': 'yellow', 'ERROR': 'red', 'CRITICAL': 'bold_red'}
            ),
            'server': self._create_formatter(
                '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - [SERVER] %(message)s',
                {'DEBUG': 'white', 'INFO': 'purple', 'WARNING': 'yellow', 'ERROR': 'red', 'CRITICAL': 'bold_red'}
            )
        }
        # 设置默认formatter
        self.setFormatter(self.formatters['default'])

    def _create_formatter(self, format_str, colors):
        return colorlog.ColoredFormatter(format_str, log_colors=colors)

    def emit(self, record):
        # 根据record中的category属性选择合适的formatter
        category = getattr(record, 'category', 'default')
        formatter = self.formatters.get(category, self.formatters['default'])

        # 使用线程锁确保formatter切换的原子性
        with _lock:
            original_formatter = self.formatter
            self.setFormatter(formatter)
            try:
                super().emit(record)
            finally:
                self.setFormatter(original_formatter)


def createLogger(blocked_loggers=None):
    global _logger, _blocked_loggers
    if blocked_loggers is not None:
        _blocked_loggers = blocked_loggers

    # 确保日志文件夹存在
    log_folder = "log"
    if not os.path.exists(log_folder):
        os.makedirs(log_folder)

    # 创建一个 logger 对象
    logger = logging.getLogger("Eridanus")
    logger.setLevel(logging.INFO)  # 设置为INFO级别，禁用DEBUG
    logger.propagate = False  # 防止重复日志

    # 清除已有的handlers，避免重复添加
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # 自定义过滤器，用于屏蔽指定的日志类别
    class BlockLoggerFilter(logging.Filter):
        def filter(self, record):
            if record.levelname in _blocked_loggers:
                return False
            # 检查自定义的category屏蔽
            category = getattr(record, 'category', None)
            if category and f"INFO_{category.upper()}" in _blocked_loggers:
                return False
            return True

    # 使用自定义的CategoryHandler
    console_handler = CategoryHandler()
    console_handler.addFilter(BlockLoggerFilter())
    logger.addHandler(console_handler)

    # 设置文件日志格式
    file_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    file_formatter = logging.Formatter(file_format)

    # 获取当前日期
    _current_log_date = datetime.now().strftime("%Y-%m-%d")
    log_file_path = os.path.join(log_folder, f"{_current_log_date}.log")

    # 创建文件处理器
    file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8')
    file_handler.setFormatter(file_formatter)
    file_handler.addFilter(BlockLoggerFilter())
    logger.addHandler(file_handler)

    def update_log_file():
        nonlocal file_handler 
        new_date = datetime.now().strftime("%Y-%m-%d")
        if new_date != _current_log_date:
            global _current_log_date  # 添加这一行
            new_log_file_path = os.path.join(log_folder, f"{new_date}.log")
    
            logger.removeHandler(file_handler)
            file_handler.close()
    
            file_handler = logging.FileHandler(new_log_file_path, mode='a', encoding='utf-8')
            file_handler.setFormatter(file_formatter)
            file_handler.addFilter(BlockLoggerFilter())
            logger.addHandler(file_handler)
    
            _current_log_date = new_date
            print(f"日志文件已切换到: {new_log_file_path}")

    def check_date_change():
        global _current_log_date
        current_date = datetime.now().strftime("%Y-%m-%d")
        return current_date != _current_log_date
    # 在 logger 上绑定更新日志文件的函数
    logger.check_date_change = check_date_change
    logger.update_log_file = update_log_file
    _logger = logger


class LoggerWrapper:
    """Logger包装器，用于支持自定义name显示"""

    def __init__(self, logger, custom_name=None):
        self._logger = logger
        self._custom_name = custom_name or "Eridanus"

    def _check_and_update_log_file(self):
        """检查并更新日志文件（如果日期发生变化）"""
        if hasattr(self._logger, 'check_date_change') and self._logger.check_date_change():
            with _lock:  # 使用锁确保线程安全
                # 再次检查（双重检查锁定模式）
                if self._logger.check_date_change():
                    self._logger.update_log_file()
    def _log_with_category(self, level, message, category=None, *args, **kwargs):
        """带类别的日志记录方法"""
        self._check_and_update_log_file()
        # 创建LogRecord
        record = self._logger.makeRecord(
            self._custom_name,  # 使用自定义名称
            level,
            __file__,
            0,
            message,
            args,
            None
        )

        # 添加category属性
        if category:
            record.category = category

        # 发送记录
        self._logger.handle(record)

    def debug(self, message, *args, **kwargs):
        # DEBUG被禁用，直接返回
        pass

    def info(self, message, *args, **kwargs):
        if self._logger.isEnabledFor(logging.INFO):
            self._log_with_category(logging.INFO, message, None, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        if self._logger.isEnabledFor(logging.WARNING):
            self._log_with_category(logging.WARNING, message, None, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        if self._logger.isEnabledFor(logging.ERROR):
            self._log_with_category(logging.ERROR, message, None, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        if self._logger.isEnabledFor(logging.CRITICAL):
            self._log_with_category(logging.CRITICAL, message, None, *args, **kwargs)

    def info_msg(self, message, *args, **kwargs):
        if self._logger.isEnabledFor(logging.INFO) and "INFO_MSG" not in _blocked_loggers:
            self._log_with_category(logging.INFO, message, 'msg', *args, **kwargs)

    def info_func(self, message, *args, **kwargs):
        if self._logger.isEnabledFor(logging.INFO) and "INFO_FUNC" not in _blocked_loggers:
            self._log_with_category(logging.INFO, message, 'func', *args, **kwargs)

    def server(self, message, *args, **kwargs):
        if self._logger.isEnabledFor(logging.INFO) and "SERVER" not in _blocked_loggers:
            self._log_with_category(logging.INFO, message, 'server', *args, **kwargs)

    def update_log_file(self):
        """手动更新日志文件"""
        if hasattr(self._logger, 'update_log_file'):
            with _lock:
                self._logger.update_log_file()


def get_logger(name=None, blocked_loggers=None) -> LoggerWrapper:
    """
    获取logger实例，支持自定义显示名称

    Args:
        name: 自定义的显示名称，如果为None则使用默认的"Eridanus"
        blocked_loggers: 要屏蔽的日志类别列表

    Returns:
        LoggerWrapper: 包装后的logger实例
    """
    global _logger
    with _lock:  # 使用锁确保线程安全
        if _logger is None:
            createLogger(blocked_loggers)
        _logger.update_log_file()
    return LoggerWrapper(_logger, name)


# 使用示例
if __name__ == "__main__":
    import time
    import threading


    def test_logger(thread_name):
        """测试函数，模拟多线程环境"""
        logger = get_logger(thread_name)

        for i in range(5):
            logger.info(f"Info message {i}")
            logger.info_msg(f"MSG message {i}")
            logger.info_func(f"FUNC message {i}")
            logger.server(f"SERVER message {i}")
            logger.warning(f"Warning message {i}")
            time.sleep(0.1)  # 模拟一些处理时间


    # 测试单线程
    print("=== 单线程测试 ===")
    test_logger("SingleThread")

    print("\n=== 多线程测试 ===")
    # 测试多线程
    threads = []
    for i in range(3):
        thread = threading.Thread(target=test_logger, args=[f"Thread-{i}"])
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    print("\n=== 测试完成 ===")

    # 验证单例模式
    logger1 = get_logger("Test1")
    logger2 = get_logger("Test2")
    print(f"Both loggers use the same underlying instance: {logger1._logger == logger2._logger}")
