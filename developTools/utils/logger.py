import logging
import os
from datetime import datetime
from logging import Logger

import colorlog

# 全局变量，用于存储 logger 实例和屏蔽的日志类别
_logger = None
_blocked_loggers = ["INFO_MSG", "DEBUG"]  # 默认禁用DEBUG


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

    # 自定义过滤器，用于屏蔽指定的日志类别
    class BlockLoggerFilter(logging.Filter):
        def filter(self, record):
            if record.levelname in _blocked_loggers:
                return False
            return True

    # 设置控制台日志格式和颜色
    console_handler = logging.StreamHandler()
    console_format = '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - [bot] %(message)s'
    console_colors = {
        'DEBUG': 'white',
        'INFO': 'cyan',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
    }
    console_formatter = colorlog.ColoredFormatter(console_format, log_colors=console_colors)
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(BlockLoggerFilter())
    logger.addHandler(console_handler)

    # --- 增加颜色区分消息、功能和服务器 ---
    console_format_msg = '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - [MSG] %(message)s'
    console_format_func = '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - [FUNC] %(message)s'
    console_format_server = '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - [SERVER] %(message)s'

    console_colors_msg = {
        'DEBUG': 'white',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
    }
    console_colors_func = {
        'DEBUG': 'white',
        'INFO': 'blue',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
    }
    console_colors_server = {
        'DEBUG': 'white',
        'INFO': 'purple',  # 使用紫色代替粉红色（colorlog 不支持直接的 pink，但 purple 接近）
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
    }

    console_formatter_msg = colorlog.ColoredFormatter(console_format_msg, log_colors=console_colors_msg)
    console_formatter_func = colorlog.ColoredFormatter(console_format_func, log_colors=console_colors_func)
    console_formatter_server = colorlog.ColoredFormatter(console_format_server, log_colors=console_colors_server)

    # 设置文件日志格式
    file_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    file_formatter = logging.Formatter(file_format)

    # 获取当前日期
    current_date = datetime.now().strftime("%Y-%m-%d")
    log_file_path = os.path.join(log_folder, f"{current_date}.log")

    # 创建文件处理器
    file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8')
    file_handler.setFormatter(file_formatter)
    file_handler.addFilter(BlockLoggerFilter())
    logger.addHandler(file_handler)

    # 定义一个函数来更新日志文件（按日期切换）
    def update_log_file():
        nonlocal log_file_path, file_handler
        new_date = datetime.now().strftime("%Y-%m-%d")
        new_log_file_path = os.path.join(log_folder, f"{new_date}.log")
        if new_log_file_path != log_file_path:
            logger.removeHandler(file_handler)
            file_handler.close()
            log_file_path = new_log_file_path
            file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8')
            file_handler.setFormatter(file_formatter)
            file_handler.addFilter(BlockLoggerFilter())
            logger.addHandler(file_handler)

    # 在 logger 上绑定更新日志文件的函数
    logger.update_log_file = update_log_file

    # --- 添加区分消息、功能和服务器的函数 ---
    def info_msg(self, message, *args, **kwargs):
        if self.isEnabledFor(logging.INFO) and "INFO_MSG" not in _blocked_loggers:
            console_handler.setFormatter(console_formatter_msg)
            self._log(logging.INFO, message, args, **kwargs)
            console_handler.setFormatter(console_formatter)

    def info_func(self, message, *args, **kwargs):
        if self.isEnabledFor(logging.INFO) and "INFO_FUNC" not in _blocked_loggers:
            console_handler.setFormatter(console_formatter_func)
            self._log(logging.INFO, message, args, **kwargs)
            console_handler.setFormatter(console_formatter)

    def server(self, message, *args, **kwargs):
        if self.isEnabledFor(logging.INFO) and "SERVER" not in _blocked_loggers:
            console_handler.setFormatter(console_formatter_server)
            self._log(logging.INFO, message, args, **kwargs)
            console_handler.setFormatter(console_formatter)

    # 将新函数绑定到 logger 类
    logging.Logger.info_msg = info_msg
    logging.Logger.info_func = info_func
    logging.Logger.server = server
    # --- 结束添加区分消息、功能和服务器的函数 ---

    _logger = logger


class LoggerWrapper:
    """Logger包装器，用于支持自定义name显示"""

    def __init__(self, logger, custom_name=None):
        self._logger = logger
        self._custom_name = custom_name or "Eridanus"

    def _log_with_custom_name(self, level, message, *args, **kwargs):
        # 临时修改logger的name
        original_name = self._logger.name
        self._logger.name = self._custom_name
        try:
            self._logger._log(level, message, args, **kwargs)
        finally:
            # 恢复原来的name
            self._logger.name = original_name

    def debug(self, message, *args, **kwargs):
        # DEBUG被禁用，直接返回
        pass

    def info(self, message, *args, **kwargs):
        if self._logger.isEnabledFor(logging.INFO):
            self._log_with_custom_name(logging.INFO, message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        if self._logger.isEnabledFor(logging.WARNING):
            self._log_with_custom_name(logging.WARNING, message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        if self._logger.isEnabledFor(logging.ERROR):
            self._log_with_custom_name(logging.ERROR, message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        if self._logger.isEnabledFor(logging.CRITICAL):
            self._log_with_custom_name(logging.CRITICAL, message, *args, **kwargs)

    def info_msg(self, message, *args, **kwargs):
        if self._logger.isEnabledFor(logging.INFO) and "INFO_MSG" not in _blocked_loggers:
            original_name = self._logger.name
            self._logger.name = self._custom_name
            try:
                # 获取console_handler并临时设置formatter
                for handler in self._logger.handlers:
                    if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                        console_format_msg = '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - [MSG] %(message)s'
                        console_colors_msg = {
                            'INFO': 'green',
                            'WARNING': 'yellow',
                            'ERROR': 'red',
                            'CRITICAL': 'bold_red',
                        }
                        temp_formatter = colorlog.ColoredFormatter(console_format_msg, log_colors=console_colors_msg)
                        original_formatter = handler.formatter
                        handler.setFormatter(temp_formatter)
                        try:
                            self._logger._log(logging.INFO, message, args, **kwargs)
                        finally:
                            handler.setFormatter(original_formatter)
                        break
            finally:
                self._logger.name = original_name

    def info_func(self, message, *args, **kwargs):
        if self._logger.isEnabledFor(logging.INFO) and "INFO_FUNC" not in _blocked_loggers:
            original_name = self._logger.name
            self._logger.name = self._custom_name
            try:
                for handler in self._logger.handlers:
                    if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                        console_format_func = '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - [FUNC] %(message)s'
                        console_colors_func = {
                            'INFO': 'blue',
                            'WARNING': 'yellow',
                            'ERROR': 'red',
                            'CRITICAL': 'bold_red',
                        }
                        temp_formatter = colorlog.ColoredFormatter(console_format_func, log_colors=console_colors_func)
                        original_formatter = handler.formatter
                        handler.setFormatter(temp_formatter)
                        try:
                            self._logger._log(logging.INFO, message, args, **kwargs)
                        finally:
                            handler.setFormatter(original_formatter)
                        break
            finally:
                self._logger.name = original_name

    def server(self, message, *args, **kwargs):
        if self._logger.isEnabledFor(logging.INFO) and "SERVER" not in _blocked_loggers:
            original_name = self._logger.name
            self._logger.name = self._custom_name
            try:
                for handler in self._logger.handlers:
                    if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                        console_format_server = '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - [SERVER] %(message)s'
                        console_colors_server = {
                            'INFO': 'purple',
                            'WARNING': 'yellow',
                            'ERROR': 'red',
                            'CRITICAL': 'bold_red',
                        }
                        temp_formatter = colorlog.ColoredFormatter(console_format_server,
                                                                   log_colors=console_colors_server)
                        original_formatter = handler.formatter
                        handler.setFormatter(temp_formatter)
                        try:
                            self._logger._log(logging.INFO, message, args, **kwargs)
                        finally:
                            handler.setFormatter(original_formatter)
                        break
            finally:
                self._logger.name = original_name

    def update_log_file(self):
        """更新日志文件"""
        if hasattr(self._logger, 'update_log_file'):
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
    if _logger is None:
        createLogger(blocked_loggers)
    _logger.update_log_file()
    return LoggerWrapper(_logger, name)


# 使用示例
if __name__ == "__main__":
    # 测试默认logger
    logger = get_logger()
    logger.debug("This is a debug message.")  # 不会显示（被禁用）
    logger.info("This is an info message.")  # 会显示
    logger.warning("This is a warning message.")  # 会显示
    logger.error("This is an error message.")  # 会显示
    logger.critical("This is a critical message.")  # 会显示

    logger.info_msg("This is a message.")  # 不会显示（被屏蔽）
    logger.info_func("This is a function info.")  # 会显示
    logger.server("This is a server-specific message.")  # 会显示（紫色）

    # 测试自定义name的logger
    custom_logger = get_logger("MyModule")
    custom_logger.info("This message is from MyModule")
    custom_logger.info_func("Function call from MyModule")
    custom_logger.server("Server message from MyModule")

    # 测试另一个自定义name的logger
    api_logger = get_logger("APIHandler")
    api_logger.info("API request received")
    api_logger.error("API error occurred")

    # 验证单例模式
    logger2 = get_logger()
    print(f"Both loggers use the same underlying instance: {logger._logger == logger2._logger}")