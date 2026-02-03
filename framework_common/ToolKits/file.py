import os
import re
from typing import Union, List, Optional

import httpx
import zipfile

import pyzipper

from .base import BaseTool
from pydub import AudioSegment

from ..utils.PDFEncrypt import AsyncPDFEncryptor


class FileProcessor(BaseTool):
    def __init__(self):
        super().__init__(__class__.__name__)
        self.encryptor = AsyncPDFEncryptor() #pdf加密器
    async def encrypt_pdf_file(self, input_path: str, output_path: str, password: str):
        """加密pdf"""
        return await self.encryptor.encrypt_pdf_file(input_path, output_path, password)
    async def download_file(self,url,path,proxy=None)->str:
        """下载文件"""
        if proxy is not None and proxy != '':
            proxies = {"http://": proxy, "https://": proxy}
        else:
            proxies = None
        async with httpx.AsyncClient(proxies=proxies, timeout=None) as client:
            response = await client.get(url)
            with open(path, 'wb') as f:
                f.write(response.content)
            return path

    def sanitize_filename(self,name: str, replacement: str = "_") -> str:
        # 替换所有非法字符
        return re.sub(r'[\\/:"*?<>|]', replacement, name)

    def compress_files(self,sources: Union[str, List[str]], output_dir: str, zip_name: str = "archive.zip"):
        """
        压缩文件或文件夹，支持单个路径或路径列表。

        :param sources: 文件/文件夹路径或其列表
        :param output_dir: 压缩文件保存的目录
        :param zip_name: 压缩文件的名称（默认 archive.zip）
        """
        zip_name = self.sanitize_filename(zip_name)
        if isinstance(sources, str):
            sources = [sources]

        os.makedirs(output_dir, exist_ok=True)
        output_zip = os.path.join(output_dir, zip_name)

        with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for source in sources:
                if os.path.isfile(source):
                    zipf.write(source, os.path.basename(source))
                elif os.path.isdir(source):
                    for root, _, files in os.walk(source):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, os.path.dirname(source))
                            zipf.write(file_path, arcname)
                else:
                    self.logger.warning(f"跳过无效路径：{source}")

        self.logger.info(f"压缩完成，文件保存在：{output_zip}")
    def compress_files_with_pwd(self,
        sources: Union[str, List[str]],
        output_dir: str,
        zip_name: str = "archive.zip",
        password: Optional[str] = None):
        """
        压缩文件或文件夹，支持设置密码。

        :param sources: 文件/文件夹路径或其列表
        :param output_dir: 压缩文件保存的目录
        :param zip_name: 压缩文件的名称（默认 archive.zip）
        :param password: 设置压缩包密码（可选）
        """
        zip_name = self.sanitize_filename(zip_name)
        if isinstance(sources, str):
            sources = [sources]

        os.makedirs(output_dir, exist_ok=True)
        output_zip = os.path.join(output_dir, zip_name)

        with pyzipper.AESZipFile(output_zip, 'w', compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zipf:
            if password:
                zipf.setpassword(password.encode('utf-8'))
                zipf.setencryption(pyzipper.WZ_AES, nbits=256)

            for source in sources:
                if os.path.isfile(source):
                    zipf.write(source, os.path.basename(source))
                elif os.path.isdir(source):
                    for root, _, files in os.walk(source):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, os.path.dirname(source))
                            zipf.write(file_path, arcname)
                else:
                    self.logger.warning(f"跳过无效路径：{source}")

        self.logger.info(f"压缩完成，文件保存在：{output_zip}")

    def merge_audio_files(self,audio_files: list, output_file: str) -> str:
        """
        合并音频文件列表并保存为一个文件，支持 MP3、FLAC、WAV 等格式。

        :param audio_files: 音频文件路径列表（支持 wav, mp3, flac 等格式）。
        :param output_file: 输出的合并音频文件路径。
        :return: 输出文件路径。
        """
        self.logger.info(f"合并音频文件...{audio_files}")
        if not audio_files:
            raise ValueError("音频文件列表不能为空。")

        combined = AudioSegment.empty()

        for file in audio_files:
            audio = AudioSegment.from_file(file)
            combined += audio

        file_format = output_file.split('.')[-1].lower()
        if file_format not in ['mp3', 'wav', 'flac']:
            raise ValueError(f"不支持的输出格式：{file_format}")

        combined.export(output_file, format=file_format)
        return output_file