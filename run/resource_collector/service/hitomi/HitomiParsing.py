import asyncio
import httpx
import os
import secrets
from pathlib import Path
from bs4 import BeautifulSoup
from typing import List, Dict
from urllib.parse import urlparse

URL = "https://hitomi.si/"
CACHE_DIR = Path("data/pictures/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ------------------ 抓页面 ------------------

async def fetch_html(url: str) -> str:
    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text


# ------------------ 解析 ------------------

def parse_popular(soup: BeautifulSoup) -> List[Dict]:
    results = []

    slider = soup.select_one("div.row-slider")
    if not slider:
        return results

    for li in slider.select("li.splide__slide"):
        title_tag = li.select_one("div.r-title a")
        img_tag = li.select_one("div.r-img img")
        if not title_tag or not img_tag:
            continue

        results.append({
            "title": title_tag.get_text(strip=True),
            "url": "https://hitomi.si" + title_tag["href"],
            "preview": img_tag.get("src"),
        })

    return results


def parse_latest(soup: BeautifulSoup) -> List[Dict]:
    results = []

    container = soup.select_one("div.pda.manga-list")
    if not container:
        return results

    for item in container.select("div.m-item"):
        title_tag = item.select_one("div.m-title a")
        img_tag = item.select_one("div.m-img img")
        if not title_tag or not img_tag:
            continue

        preview = img_tag.get("data-src") or img_tag.get("src")

        results.append({
            "title": title_tag.get_text(strip=True),
            "url": "https://hitomi.si" + title_tag["href"],
            "preview": preview,
        })

    return results


# ------------------ 图片下载器（核心） ------------------

def _random_filename(url: str) -> str:
    ext = os.path.splitext(urlparse(url).path)[1] or ".jpg"
    return f"{secrets.token_hex(3)}{ext}"  # 6 位随机字符串


async def _download_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    item: Dict,
):
    url = item.get("preview")
    if not url or not url.startswith("http"):
        return

    async with sem:
        try:
            r = await client.get(url)
            r.raise_for_status()

            filename = _random_filename(url)
            filepath = CACHE_DIR / filename

            filepath.write_bytes(r.content)

            # 替换为相对路径
            item["preview"] = str(filepath.as_posix())

        except Exception:
            # 下载失败就保留原 preview，不抛异常
            pass


async def download_and_replace_previews(
    items: List[Dict],
    *,
    concurrency: int = 10,
):
    """
    批量异步下载图片，并替换 preview 为本地相对路径
    """
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(timeout=None) as client:
        tasks = [
            _download_one(client, sem, item)
            for item in items
        ]
        await asyncio.gather(*tasks)


# ------------------ 对外主函数 ------------------

async def HitomiPage() -> list[list]:
    html = await fetch_html(URL)
    soup = BeautifulSoup(html, "lxml")

    popular = parse_popular(soup)
    latest = parse_latest(soup)

    # 并发下载图片（两个列表一起）
    await asyncio.gather(
        download_and_replace_previews(popular),
        download_and_replace_previews(latest),
    )

    return [popular, latest]


# ------------------ 调试 ------------------

if __name__ == "__main__":
    r = asyncio.run(HitomiPage())
    print(r)
