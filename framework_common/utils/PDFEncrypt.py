import asyncio
import aiofiles
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from framework_common.utils.install_and_import import install_and_import

pypdf=install_and_import("pypdf")
from pypdf import PdfReader, PdfWriter
from io import BytesIO


class AsyncPDFEncryptor:
    def __init__(self, max_workers=4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def _encrypt_pdf(self, input_data: bytes, password: str) -> bytes:
        """同步加密逻辑，在线程池中执行"""
        reader = PdfReader(BytesIO(input_data))
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        writer.encrypt(password)

        output = BytesIO()
        writer.write(output)
        return output.getvalue()

    async def encrypt_pdf_bytes(self, input_data: bytes, password: str) -> bytes:
        """异步加密PDF字节数据"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor, self._encrypt_pdf, input_data, password
        )

    async def encrypt_pdf_file(self, input_path: str, output_path: str, password: str):
        """异步加密PDF文件"""
        async with aiofiles.open(input_path, 'rb') as f:
            input_data = await f.read()

        encrypted_data = await self.encrypt_pdf_bytes(input_data, password)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(output_path, 'wb') as f:
            await f.write(encrypted_data)

    def close(self):
        """关闭线程池"""
        self.executor.shutdown(wait=True)


async def main():
    encryptor = AsyncPDFEncryptor()

    try:
        await encryptor.encrypt_pdf_file("input.pdf", "output.pdf", "123456")
        print("PDF加密完成")
        with open("input.pdf", "rb") as f:
            pdf_data = f.read()

        encrypted_data = await encryptor.encrypt_pdf_bytes(pdf_data, "123456")
        print(f"加密完成，大小: {len(encrypted_data)} 字节")

    finally:
        encryptor.close()

if __name__ == "__main__":
    asyncio.run(main())