from io import BytesIO

from framework_common.utils.install_and_import import install_and_import

cloudscraper=install_and_import("cloudscraper")
import asyncio
import os
import re
import urllib.parse
import concurrent.futures
from functools import partial

from PIL import Image

from framework_common.framework_util.yamlLoader import YAMLManager

# 全局变量
DOWNLOAD_LIMIT = 5  # 获取到的视频数量，或者信息条数
API_BASE_URL = "https://api.iwara.tv/videos"
RATING = "all"  # ecchi(r18), all（没啥用，因为就没有不是r18的）
DOWNLOAD_DIR = "data/pictures/cache"  # 视频下载目录

yaml_manager = YAMLManager.get_instance()

local_config = yaml_manager.common_config.basic_config
proxy = local_config.get("proxy").get("http_proxy")
if not proxy:
    proxy = None

# 创建线程池执行器
executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)


def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)


def get_scraper():
    """创建cloudscraper实例"""
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )

    if proxy:
        scraper.proxies = {
            'http': proxy,
            'https': proxy
        }

    return scraper


def _sync_request(scraper, method, url, **kwargs):
    """同步请求的包装函数"""
    if method.upper() == 'GET':
        return scraper.get(url, **kwargs)
    elif method.upper() == 'POST':
        return scraper.post(url, **kwargs)


async def async_request(method, url, **kwargs):
    """异步请求包装"""
    scraper = get_scraper()
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, partial(_sync_request, scraper, method, url, **kwargs))


def _sync_download_file(url, file_path, scraper=None):
    """同步下载文件的包装函数"""
    if scraper is None:
        scraper = get_scraper()

    with scraper.get(url, stream=True) as response:
        response.raise_for_status()
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    return file_path


async def async_download_file(url, file_path):
    """异步下载文件"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _sync_download_file, url, file_path)


async def download_video(client, video_id):
    print(f"\n正在处理视频 ID: {video_id}")
    video_details_url = f"https://api.iwara.tv/video/{video_id}"
    print(f"从以下地址获取详情: {video_details_url}")

    # 异步获取视频详情
    video_response = await async_request('GET', video_details_url)
    video_response.raise_for_status()
    video_data = video_response.json()

    title = video_data.get("title")
    file_url = video_data.get("fileUrl")

    if not file_url:
        print(f"未找到视频 ID: {video_id} 的文件 URL")
        return None

    download_links_response = await async_request('GET', file_url)
    download_links_response.raise_for_status()

    download_links = download_links_response.json()

    if not download_links or len(download_links) == 0:
        print(f"未找到视频 ID: {video_id} 的下载链接")
        return None

    # 查找 '360' 质量的下载链接
    first_download_link = None
    for link in download_links:
        if link.get("name") == "360":
            first_download_link = link["src"].get("download")
            break

    if not first_download_link:
        print(f"未找到视频 ID: {video_id} 的 '360' 质量下载链接")
        return None

    full_download_url = f"https:{first_download_link}"
    print(f"开始下载视频: {full_download_url}")

    sanitized_title = sanitize_filename(title)
    file_name = f"{sanitized_title}.mp4"
    absolute_file_path = os.path.abspath(os.path.join(DOWNLOAD_DIR, file_name)).replace("\\", "/")

    # 异步下载视频文件
    await async_download_file(full_download_url, absolute_file_path)

    print(f"视频已下载并保存为: {absolute_file_path}")
    return {
        "title": title,
        "video_id": video_id,
        "path": absolute_file_path
    }


async def fetch_video_info(sort, config):
    url = f"{API_BASE_URL}?rating={RATING}&sort={sort}&limit={DOWNLOAD_LIMIT}"

    response = await async_request('GET', url)
    response.raise_for_status()

    data = response.json()
    results = data.get("results", [])

    video_info_list = []

    # 并发处理多个视频
    tasks = []
    for item in results:
        task = process_video(None, item)
        tasks.append(task)

    video_infos = await asyncio.gather(*tasks, return_exceptions=True)

    for video_info in video_infos:
        if isinstance(video_info, Exception):
            print(f"处理视频时出错: {video_info}")
        elif video_info:
            video_info_list.append(video_info)

    return video_info_list


async def process_video(client, item, iwara_gray_layer=False):
    title = item.get("title")
    video_id = item.get("id")

    if not title or not video_id:
        return None

    thumbnail_path = await download_thumbnail(None, item, iwara_gray_layer)

    return {
        "title": title,
        "video_id": video_id,
        "path": thumbnail_path
    }


def _sync_download_thumbnail_content(url, iwara_gray_layer=False):
    """同步下载缩略图内容"""
    scraper = get_scraper()
    response = scraper.get(url)
    response.raise_for_status()

    img = Image.open(BytesIO(response.content))
    if iwara_gray_layer:
        img = img.convert('1')

    return img, response.status_code


async def download_thumbnail(client, item, iwara_gray_layer):
    title = item.get("title")
    thumbnail = item.get("thumbnail", 0)
    file_data = item.get("file", {})
    video_id = file_data.get("id")
    custom_thumbnail = item.get("customThumbnail")

    if not title or not video_id:
        return None

    sanitized_title = sanitize_filename(title)
    file_name = f"{sanitized_title}.jpg"
    absolute_file_path = os.path.abspath(os.path.join(DOWNLOAD_DIR, file_name)).replace("\\", "/")
    os.makedirs(os.path.dirname(absolute_file_path), exist_ok=True)

    if custom_thumbnail and custom_thumbnail.get("id"):
        thumbnail_id = custom_thumbnail.get("id")
        thumbnail_url = f"https://i.iwara.tv/image/thumbnail/{thumbnail_id}/{thumbnail_id}.jpg"

        try:
            loop = asyncio.get_event_loop()
            img, status_code = await loop.run_in_executor(
                executor,
                partial(_sync_download_thumbnail_content, thumbnail_url, iwara_gray_layer)
            )
            print(f"自定义缩略图内容请求成功, 状态码: {status_code}")

            img.save(absolute_file_path)
            return absolute_file_path

        except Exception as e:
            print(f"自定义缩略图下载失败: {e}")
            return None
    else:
        thumbnail_padded = f"{int(thumbnail):02d}"
        thumbnail_url = f"https://i.iwara.tv/image/thumbnail/{video_id}/thumbnail-{thumbnail_padded}.jpg"

        try:
            loop = asyncio.get_event_loop()
            img, status_code = await loop.run_in_executor(
                executor,
                partial(_sync_download_thumbnail_content, thumbnail_url, iwara_gray_layer)
            )

            img.save(absolute_file_path)
            return absolute_file_path
        except Exception as e:
            print(f"缩略图下载失败: {e}")
            return None


async def rank_videos(sort, config):
    url = f"{API_BASE_URL}?rating={RATING}&sort={sort}&limit={DOWNLOAD_LIMIT}"

    response = await async_request('GET', url)
    response.raise_for_status()

    data = response.json()
    results = data.get("results", [])

    video_download_list = []

    # 并发下载多个视频
    tasks = []
    for item in results:
        task = download_video(None, item.get("id"))
        tasks.append(task)

    video_infos = await asyncio.gather(*tasks, return_exceptions=True)

    for video_info in video_infos:
        if isinstance(video_info, Exception):
            print(f"下载视频时出错: {video_info}")
        elif video_info:
            video_download_list.append(video_info)


async def download_specific_video(videoid, config):
    video_info = await download_video(None, videoid)
    if video_info:
        return video_info
    else:
        return None


async def search_videos(word, config, iwara_gray_layer=False):
    query = urllib.parse.quote(word)
    url = f"https://api.iwara.tv/search?type=video&page=0&query={query}&limit={DOWNLOAD_LIMIT}"

    response = await async_request('GET', url)
    response.raise_for_status()

    data = response.json()
    results = data.get("results", [])

    video_info_list = []

    # 并发处理多个搜索结果
    tasks = []
    for item in results:
        task = process_video(None, item, iwara_gray_layer)
        tasks.append(task)

    video_infos = await asyncio.gather(*tasks, return_exceptions=True)

    for video_info in video_infos:
        if isinstance(video_info, Exception):
            print(f"处理搜索结果时出错: {video_info}")
        elif video_info:
            video_info_list.append(video_info)

    return video_info_list


def main(command):
    if command.startswith("下载"):
        videoid = command.replace("下载", "").strip()
        if videoid:
            asyncio.run(download_specific_video(videoid, None))
        else:
            return None
    elif command.startswith("搜索"):
        word = command.replace("搜索", "").strip()
        if word:
            asyncio.run(search_videos(word, None))
        else:
            return None
    elif command.startswith("榜单下载"):
        sort = command.replace("榜单下载", "").strip()
        asyncio.run(rank_videos(sort, None))
    elif command.startswith("榜单"):
        sort = command.replace("榜单", "").strip()
        asyncio.run(fetch_video_info(sort, None))


if __name__ == "__main__":
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    while True:
        print(
            "\nname可以是date(最新), popularity(热门), trending(趋势);所有结果个数为DOWNLOAD_LIMIT(代码开头去改)\n用的时候不要带大括号")
        command = input("请输入命令 (榜单{name}/榜单下载{name}/下载{video_id}/搜索{关键词}): ")
        main(command)