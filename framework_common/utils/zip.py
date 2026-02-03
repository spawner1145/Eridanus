import zipfile
import os
from typing import Union, List
import re

from framework_common.ToolKits import Util

util=Util.get_instance()
def sanitize_filename(name: str, replacement: str = "_") -> str:
    return util.file.sanitize_filename(name, replacement)
def compress_files(sources: Union[str, List[str]], output_dir: str, zip_name: str = "archive.zip"):
    """
    压缩文件或文件夹，支持单个路径或路径列表。

    :param sources: 文件/文件夹路径或其列表
    :param output_dir: 压缩文件保存的目录
    :param zip_name: 压缩文件的名称（默认 archive.zip）
    """
    return util.file.compress_files(sources, output_dir, zip_name)

