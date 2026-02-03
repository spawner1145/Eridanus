
from typing import Optional
from .file import FileProcessor
from .image import ImageProcessor
from .network import NetworkProcessor
from .text import TextProcessor

class Util:
    _instance: Optional["Util"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_fields()
        return cls._instance

    @classmethod
    def get_instance(cls) -> "Util":
        return cls()

    def _init_fields(self):
        """仅在初次调用时实例化"""
        self._network: Optional[NetworkProcessor] = None
        self._image: Optional[ImageProcessor] = None
        self._file: Optional[FileProcessor] = None
        self._text: Optional[TextProcessor] = None

    @property
    def network(self) -> NetworkProcessor:
        """网络相关工具"""
        if self._network is None:
            self._network = NetworkProcessor()
        return self._network
    @property
    def image(self) -> ImageProcessor:
        """图像处理工具"""
        if self._image is None:
            self._image = ImageProcessor()
        return self._image
    @property
    def text(self) -> TextProcessor:
        """文本处理工具"""
        if self._text is None:
            self._text = TextProcessor()
        return self._text
    @property
    def file(self) -> FileProcessor:
        """文件处理工具"""
        if self._file is None:
            self._file = FileProcessor()
        return self._file
