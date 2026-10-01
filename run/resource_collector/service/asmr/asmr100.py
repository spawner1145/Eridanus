import asyncio
import random
import re
import httpx


def _collect_tracks_recursive(node, results):
    """递归遍历 tracks 树，收集所有音频文件"""
    if isinstance(node, list):
        for item in node:
            _collect_tracks_recursive(item, results)
    elif isinstance(node, dict):
        if "children" in node and isinstance(node["children"], list):
            _collect_tracks_recursive(node["children"], results)

        media_url = node.get("mediaStreamUrl") or node.get("mediaDownloadUrl") or node.get("streamUrl")
        title = node.get("title", "")
        if media_url:
            ext = "." + title.split(".")[-1].lower() if "." in title else ""
            if ext in [".mp3", ".m4a", ".webm", ".ogg", ".flac", ".wav", ".aac"]:
                results.append([media_url, title])


async def get_info(data, proxies=None, mode="default"):
    if mode == "random":
        index = random.randint(0, len(data["works"]) - 1)
        id = data["works"][index]['id']
        source_id = data["works"][index]['source_id']
        title = data["works"][index]['title']
        nsfw = data["works"][index]['nsfw']
        mainCoverUrl = data["works"][index]['mainCoverUrl']
        new_url = f"https://api.asmr-200.com/api/tracks/{id}?v=1"
    elif mode == "download":
        id = data["id"]
        source_id = data["source_id"]
        title = data["title"]
        nsfw = data["nsfw"]
        mainCoverUrl = data["mainCoverUrl"]
        new_url = f"https://api.asmr-200.com/api/tracks/{id}?v=1"
    else:
        id = data["works"][0]['id']
        source_id = data["works"][0]['source_id']
        title = data["works"][0]['title']
        nsfw = data["works"][0]['nsfw']
        mainCoverUrl = data["works"][0]['mainCoverUrl']
        new_url = f"https://api.asmr-200.com/api/tracks/{id}?v=1"

    async with httpx.AsyncClient(proxies=proxies, timeout=30) as client:
        response = await client.get(new_url)
        tracks_data = response.json()

    media_urls = []
    _collect_tracks_recursive(tracks_data, media_urls)

    final_data = {
        "id": id,
        "title": title,
        "source_url": f"https://asmr.one/work/{source_id}",
        "nsfw": nsfw,
        "mainCoverUrl": mainCoverUrl,
        "media_urls": media_urls
    }
    return final_data


async def random_asmr_100(proxy=None):
    if proxy is not None and proxy != "":
        proxies = {"http://": proxy, "https://": proxy}
    else:
        proxies = None
    url = 'https://api.asmr-200.com/api/works?order=betterRandom'
    async with httpx.AsyncClient(proxies=proxies, timeout=30) as client:
        response = await client.get(url)
        data = response.json()
        return await get_info(data, proxies)


async def latest_asmr_100(proxy=None):
    if proxy is not None and proxy != "":
        proxies = {"http://": proxy, "https://": proxy}
    else:
        proxies = None
    url = 'https://api.asmr-200.com/api/works?order=create_date&sort=desc&page=1&subtitle=0'
    async with httpx.AsyncClient(proxies=proxies, timeout=30) as client:
        response = await client.get(url)
        data = response.json()
    return await get_info(data, proxies)


async def choose_from_latest_asmr_100(proxy=None):
    if proxy is not None and proxy != "":
        proxies = {"http://": proxy, "https://": proxy}
    else:
        proxies = None
    url = 'https://api.asmr-200.com/api/works?order=create_date&sort=desc&page=1&subtitle=0'
    async with httpx.AsyncClient(proxies=proxies, timeout=30) as client:
        response = await client.get(url)
        data = response.json()
    return await get_info(data, proxies, "random")


async def choose_from_hotest_asmr_100(proxy=None):
    if proxy is not None and proxy != "":
        proxies = {"http://": proxy, "https://": proxy}
    else:
        proxies = None
    url = "https://api.asmr-200.com/api/recommender/popular"
    payload = {"keyword": " ", "page": 1, "subtitle": 0, "localSubtitledWorks": [], "withPlaylistStatus": []}
    async with httpx.AsyncClient(proxies=proxies, timeout=30) as client:
        response = await client.post(url, json=payload)
        data = response.json()
        return await get_info(data, proxies, "random")


async def parse_from_asmr_id(id, proxy=None):
    """
    解析指定url中的asmr资源
    :param id:
    :param proxy:
    :return:
    """
    url = f"https://api.asmr-200.com/api/workInfo/{id}"
    if proxy is not None and proxy != "":
        proxies = {"http://": proxy, "https://": proxy}
    else:
        proxies = None
    async with httpx.AsyncClient(proxies=proxies, timeout=30) as client:
        response = await client.get(url)
        return await get_info(response.json(), proxies, "download")