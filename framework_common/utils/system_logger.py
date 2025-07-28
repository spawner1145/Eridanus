import logging
import colorlog
from threading import Lock
import sys


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

        # 完全重置logging系统
        logging.getLogger().handlers.clear()
        logging.getLogger().setLevel(logging.NOTSET)

        # 创建新的handler
        handler = colorlog.StreamHandler(sys.stdout)

        # 创建formatter
        formatter = colorlog.ColoredFormatter(
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

        handler.setFormatter(formatter)

        # 配置root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)

        self._initialized = True

    def get_logger(self, name: str) -> logging.Logger:
        return logging.getLogger(name)


def get_logger(name: str) -> logging.Logger:
    return SingletonLogger().get_logger(name)