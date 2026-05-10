# -*- coding: utf-8 -*-
"""
jmComic 业务逻辑封装
重构要点：
  - 统一使用新版 jmcomic API（Feature、JmDownloader.use()）
  - 彻底废弃全局可变类变量控制 Downloader 的旧写法
  - 预览下载器通过工厂函数按需构造，互不影响
  - downloadALLAndToPdf 的 filename_rule 改为合法的 'Aid'（本子ID）
  - 消除 YAML 文件被反复读写修改 base_dir 的副作用
  - 排行榜函数每次实时请求，无缓存
"""

import asyncio
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

import jmcomic
from jmcomic import (
    JmOption, JmAlbumDetail, JmPhotoDetail,
    JmSearchPage, JmCategoryPage,
    JmModuleConfig, JmMagicConstants,
    download_album, Feature,
)
from PIL import Image

from framework_common.utils.random_str import random_str
from run.ai_generated_art.service.antiSFW import process_folder, compress_gifs
from run.resource_collector.service.img_obfuscation import download_cover_bw, obfuscate_cover

_OPTION_FILE = 'run/resource_collector/jmcomic.yml'

# 月榜仍保留缓存，因为它只用于「随机本子」，不需要实时性，且数据量大
from datetime import date
_jm_month_cache: dict = {}


# ──────────────────────────────────────────────
# 内部工具
# ──────────────────────────────────────────────

def _load_option(base_dir: str | None = None) -> JmOption:
    """
    从配置文件加载 Option。
    若传入 base_dir，通过代码动态覆盖，不再改写磁盘上的 YAML 文件。
    """
    option = jmcomic.create_option_by_file(_OPTION_FILE)
    if base_dir is not None:
        option.dir_rule.base_dir = base_dir
    return option


def _make_preview_downloader(start: int, end: int, album_index: int):
    """
    工厂函数：每次调用都返回一个全新的预览用 Downloader 类。
    使用局部 class 避免全局状态污染，彻底解决并发/复用时参数串用问题。
    """
    _start = start
    _end = end
    _album_index = album_index

    class _PreviewDownloader(jmcomic.JmDownloader):
        def do_filter(self, detail):
            if detail.is_album():
                album: JmAlbumDetail = detail
                idx = max(0, min(_album_index - 1, len(album) - 1))
                return [album[idx]]

            if detail.is_photo():
                photo: JmPhotoDetail = detail
                s = max(0, _start)
                e = _end if _end > 0 else len(photo)
                e = min(e, len(photo))
                if s >= e:
                    s, e = 0, len(photo)
                return photo[s:e]

            return detail

    return _PreviewDownloader


# ──────────────────────────────────────────────
# 搜索 API
# ──────────────────────────────────────────────

def JM_search(name: str) -> str:
    """关键字站内搜索，返回格式化文本（最多 30 条）。"""
    client = JmOption.default().new_jm_client()
    page: JmSearchPage = client.search_site(search_query=name, page=1)
    lines = []
    for album_id, title in page:
        lines.append(f'[{album_id}]: {title}')
        if len(lines) >= 30:
            break
    return '\n'.join(lines)


async def JM_search_id(comic_id) -> str:
    """通过车牌号查询本子标题（返回第一条结果）。"""
    client = JmOption.default().new_jm_client()
    page: JmSearchPage = client.search_site(search_query=str(comic_id), page=1)
    for _, title in page:
        return title
    return str(comic_id)


def JM_search_week() -> str:
    """本周排行，返回纯文本（兼容旧接口）。"""
    return '\n'.join(f'[{aid}]: {title}' for aid, title in JM_ranking_week())


def JM_search_month() -> list:
    """本月热门榜，返回 album_id 列表，有日级缓存（供随机本子使用）。"""
    today = date.today()
    cache_key = f'{today}_month'
    if cache_key in _jm_month_cache:
        return _jm_month_cache[cache_key]

    cl = JmOption.default().new_jm_client()
    result = []
    for page in cl.categories_filter_gen(
        page=1,
        time=JmMagicConstants.TIME_MONTH,
        category=JmMagicConstants.CATEGORY_ALL,
        order_by=JmMagicConstants.ORDER_BY_VIEW,
    ):
        for aid, _ in page:
            result.append(aid)
        if len(result) >= 50:
            break

    _jm_month_cache[cache_key] = result
    return result


# ── 实时排行榜（无缓存）─────────────────────────────────────────

def JM_ranking_week(limit: int = 10) -> list[tuple[str, str]]:
    """本周热门榜，每次实时请求，返回 [(album_id, title), ...]。"""
    cl = JmOption.default().new_jm_client()
    result = []
    for page in cl.categories_filter_gen(
        page=1,
        time=JmMagicConstants.TIME_WEEK,
        category=JmMagicConstants.CATEGORY_ALL,
        order_by=JmMagicConstants.ORDER_BY_VIEW,
    ):
        for aid, atitle in page:
            result.append((str(aid), atitle))
            if len(result) >= limit:
                break
        break  # 只取第一页
    return result


def JM_ranking_today(limit: int = 10) -> list[tuple[str, str]]:
    """今日热门榜，每次实时请求，返回 [(album_id, title), ...]。"""
    cl = JmOption.default().new_jm_client()
    result = []
    for page in cl.categories_filter_gen(
        page=1,
        time=JmMagicConstants.TIME_TODAY,
        category=JmMagicConstants.CATEGORY_ALL,
        order_by=JmMagicConstants.ORDER_BY_VIEW,
    ):
        for aid, atitle in page:
            result.append((str(aid), atitle))
            if len(result) >= limit:
                break
        break
    return result


# ──────────────────────────────────────────────
# 封面下载（排行榜图文专用）
# ──────────────────────────────────────────────




def download_covers_concurrent(
    id_title_list: list[tuple[str, str]],
    anti_nsfw: str = "black_and_white",
    max_workers: int = 5,
) -> list[tuple[str, str, str | None]]:
    """
    并发下载一批封面，返回 [(album_id, title, cover_path_or_None), ...]。
    顺序与输入 id_title_list 保持一致。
    """
    results: dict[str, tuple[str, str | None]] = {}

    def _fetch(aid: str, title: str):
        return aid, title, download_cover_bw(aid, anti_nsfw=anti_nsfw)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch, aid, title): aid for aid, title in id_title_list}
        for future in as_completed(futures):
            aid, title, cover = future.result()
            results[aid] = (title, cover)

    return [(aid, results[aid][0], results[aid][1]) for aid, _ in id_title_list]


# ──────────────────────────────────────────────
# 下载 API
# ──────────────────────────────────────────────

def downloadComic(
    comic_id,
    start: int = 1,
    end: int = 5,
    anti_nsfw: str = "black_and_white",
    gif_compress: bool = False,
) -> list[str]:
    """
    预览下载：下载本子第一章的第 start～end 张图，返回处理后的本地文件路径列表。

    参数:
        comic_id    : 禁漫车牌号
        start       : 图片起始下标（1-based，含）
        end         : 图片结束下标（1-based，不含）；0 表示全部
        anti_nsfw   : "black_and_white" / "gif" / "no_censor"
        gif_compress: 是否压缩 gif
    """
    temp_dir = f'data/pictures/benzi/temp{comic_id}'
    os.makedirs(temp_dir, exist_ok=True)

    slice_start = max(0, start - 1)  # 外部 1-based → 内部 0-based
    slice_end = end

    PreviewDownloader = _make_preview_downloader(
        start=slice_start,
        end=slice_end,
        album_index=1,
    )
    PreviewDownloader.use()

    option = _load_option(base_dir=temp_dir)
    jmcomic.download_album(comic_id, option)
    jmcomic.JmDownloader.use()  # 恢复默认 Downloader

    file_names = sorted(os.listdir(temp_dir))
    new_files: list[str] = []

    if anti_nsfw == "gif":
        asyncio.run(process_folder(input_folder=temp_dir, output_folder=temp_dir))
        for filename in sorted(os.listdir(temp_dir)):
            if filename.lower().endswith('.gif'):
                dst = f'data/pictures/cache/{random_str()}.gif'
                shutil.move(os.path.join(temp_dir, filename), dst)
                new_files.append(dst)
        if gif_compress:
            asyncio.run(compress_gifs(new_files))

    elif anti_nsfw == "black_and_white":
        for fname in file_names:
            img = Image.open(os.path.join(temp_dir, fname)).convert('1')
            dst = f'data/pictures/cache/{random_str()}.png'
            img.save(dst)
            new_files.append(dst)

    elif anti_nsfw == "no_censor":
        for fname in file_names:
            dst = os.path.join('data/pictures/cache', fname)
            shutil.move(os.path.join(temp_dir, fname), dst)
            new_files.append(dst)
    elif anti_nsfw == "obfuscate":
        for fname in file_names:
            dst = f'data/pictures/cache/{random_str()}.png'
            img = Image.open(os.path.join(temp_dir, fname))
            obfuscated_img = obfuscate_cover(img)
            obfuscated_img.save(dst, format="PNG")
            new_files.append(dst)
    return new_files


def downloadALLAndToPdf(comic_id, save_path: str) -> str:
    """
    全本下载并导出为 PDF。
    返回值：PDF 文件路径（不含 .pdf 后缀，兼容调用方的 f"{r}.pdf" 拼接写法）。
    """
    download_album(
        str(comic_id),
        extra=Feature.export_pdf(
            pdf_dir=save_path,
            filename_rule='Aid',
            delete_original_file=True,
        ),
    )
    return os.path.join(save_path, str(comic_id))