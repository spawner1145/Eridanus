import random
import asyncio
import httpx
import base64
import os
import re
from io import BytesIO
from asyncio import get_event_loop
from PIL import Image
from .common import get_abs_path, occupy_chart, data_dir, printf
import traceback
import subprocess
import os

async def download_img(url, gray_layer=False, proxy=None):
    if url.startswith("data:image"):
        match = re.match(r"data:image/(.*?);base64,(.+)", url)
        if not match:
            raise ValueError("Invalid Data URI format")

        img_type, base64_data = match.groups()
        img_data = base64.b64decode(base64_data)  # 解码 Base64 数据
        base64_img = base64.b64encode(img_data).decode('utf-8')
        return base64_img

    if proxy is not None and proxy != '':
        proxies = {"http://": proxy, "https://": proxy}
    else:
        proxies = None
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8"
    }
    #print(f'proxies:{proxies}')
    async with httpx.AsyncClient(proxies=proxies, headers=headers, timeout=30.0) as client:
        try:
            response = await client.get(url)
            #print(response)
            if response.status_code == 302:
                new_url = response.headers['Location']
                if new_url: response = await client.get(new_url)
        except Exception as e:
            print(f'绘图框架无法获取图片{url} ： {type(e)} {repr(e)}')
            #print(proxies)
            #traceback.print_exc()
            #重试一次
            await asyncio.sleep(2)
            try:
                response = await client.get(url)
                # print(response)
                if response.status_code == 302:
                    new_url = response.headers['Location']
                    if new_url: response = await client.get(new_url)
            except Exception as e:
                print(f'绘图框架无法获取图片{url} ： {type(e)} {repr(e)}')
                #无法获取图片，直接从本地读取占位图
                return Image.open(occupy_chart)
        if response.status_code != 200:
            return Image.open(occupy_chart)

        if gray_layer:
            try:
                with BytesIO(response.content) as img_buffer:
                    img = Image.open(img_buffer)
                    image_black_white = img.convert('1')  # 转换为黑白图像

                with BytesIO() as output_buffer:
                    image_black_white.save(output_buffer, format='PNG')
                    img_data = output_buffer.getvalue()
                    base64_img = base64.b64encode(img_data).decode('utf-8')

                img.close()
                image_black_white.close()

            except Exception as e:
                base64_img = base64.b64encode(response.content).decode('utf-8')
        else:
            try:
                pillow_img = Image.open(BytesIO(response.content))
            except Exception as e:
                printf(f'base64图片打开失败，尝试保存后打开')
                check_path = data_dir / 'cache' / 'img_check.webp'
                with open(check_path, 'wb') as f:
                    f.write(response.content)
                with open(check_path, 'rb') as f:
                    header = f.read(12)
                if b'ftypavif' in header:
                    printf('检测到为不支持的AVIF格式，转换后尝试读取')
                    check_convert_path = data_dir / 'cache' / 'img_check_convert.webp'
                    if check_convert_path.exists():
                        os.remove(check_convert_path)
                    #应该检测一下是否系统内安装了ffmpg，一般不会遇到此问题
                    command = [
                        'ffmpeg',
                        '-hide_banner',
                        '-loglevel', 'error',
                        '-i', check_path,
                        check_convert_path
                    ]
                    subprocess.run(command)
                    pillow_img = Image.open(check_convert_path)
                else:
                    pillow_img = Image.open(check_path)
            return pillow_img
        return base64_img

#对图像进行批量处理
async def process_img_download(img_list,is_abs_path_convert=True,gray_layer=False,proxy=None):
    #函数内部定义一个函数用于并发调用
    async def img_deal(content):
        return_img = None
        if isinstance(content, str) and os.path.splitext(content)[1].lower() in [".jpg", ".png", ".jpeg",'.webp'] and not content.startswith("http"):  # 若图片为本地文件，则转化为img对象
            if is_abs_path_convert is True: content = get_abs_path(content)
            return_img = Image.open(content)
        elif isinstance(content, str) and content.startswith("http"):
            try:
                content_deal = await download_img(content, proxy=proxy)
                if isinstance(content_deal, str):
                    return_img = Image.open(BytesIO(base64.b64decode(content_deal)))
                elif isinstance(content_deal, Image.Image):
                    return_img = content_deal
            except Exception as e: print(e)
        elif isinstance(content, Image.Image):
            return_img = content
        else:  # 最后判断是否为base64，若不是，则不添加本次图像
            bio = None
            img_data = None
            try:
                img_data = base64.b64decode(content)
                bio = BytesIO(img_data)
                return_img = Image.open(bio)
            except: pass
            finally:
                # 清理资源
                if img_data is not None:
                    del img_data
        #判断其是否为None
        if return_img is None:
            return_img = Image.open(occupy_chart)
        return return_img

    if not isinstance(img_list, list):
        img_list = [img_list]
    tasks = [img_deal(content) for content in img_list]  # 生成任务列表（协程对象列表）
    processed_img = await asyncio.gather(*tasks)    # 并发执行所有任务
    return processed_img

