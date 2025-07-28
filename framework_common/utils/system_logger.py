import logging
import sys
from threading import Lock

import colorlog
for logger_name in ['apscheduler', 'apscheduler.scheduler', 'httpx', 'httpcore']:
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())  # 添加 NullHandler
    logger.propagate = False  # 禁止传播
    logger.setLevel(logging.WARNING)

class SingletonLogger:
    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 创建 handler 和 formatter
        self.handler = colorlog.StreamHandler(sys.stdout)
        self.formatter = colorlog.ColoredFormatter(
            fmt='%(log_color)s%(asctime)s - [Eridanus] %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'light_blue',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            },
            reset=True
        )
        self.handler.setFormatter(self.formatter)

        self._initialized = True

    def get_logger(self, name: str) -> logging.Logger:
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.handlers.clear()  # 清除已有 handler
        logger.addHandler(self.handler)  # 添加你的 handler
        logger.propagate = False  # 禁止传播到 root logger
        return logger


def get_logger(name: str) -> logging.Logger:
    return SingletonLogger().get_logger(name)