import os
from typing import Union, List, Optional

from framework_common.utils.install_and_import import install_and_import

pyzipper=install_and_import("pyzipper")

import re
from framework_common.ToolKits import Util

util=Util.get_instance()
def compress_files_with_pwd(
        sources: Union[str, List[str]],
        output_dir: str,
        zip_name: str = "archive.zip",
        password: Optional[str] = None
):
    """
    压缩文件或文件夹，支持设置密码。

    :param sources: 文件/文件夹路径或其列表
    :param output_dir: 压缩文件保存的目录
    :param zip_name: 压缩文件的名称（默认 archive.zip）
    :param password: 设置压缩包密码（可选）
    """
    return util.file.compress_files_with_pwd(sources, output_dir, zip_name, password)
