import logging
import colorlog
from threading import Lock


class SingletonLogger:
    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:  # 保证线程安全
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        handler = colorlog.StreamHandler()
        handler.setFormatter(colorlog.ColoredFormatter(
            '%(log_color)s%(asctime)s - [Eridanus] %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'light_blue',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        ))

        self._root_logger = logging.getLogger()
        self._root_logger.setLevel(logging.INFO)

        # 避免重复添加 handler
        if not any(isinstance(h, colorlog.StreamHandler) for h in self._root_logger.handlers):
            self._root_logger.addHandler(handler)

        self._initialized = True

    def get_logger(self, name: str) -> logging.Logger:
        return logging.getLogger(name)


# 对外暴露的函数
def get_logger(name: str) -> logging.Logger:
    return SingletonLogger().get_logger(name)
