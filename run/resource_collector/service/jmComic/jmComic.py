# -*- coding: utf-8 -*-
"""
jmComic 业务逻辑封装
重构要点：
  - 统一使用新版 jmcomic API（Feature、JmDownloader.use()）
  - 彻底废弃全局可变类变量控制 Downloader 的旧写法
  - 预览下载器通过工厂函数按需构造，互不影响
  - downloadALLAndToPdf 的 filename_rule 改为合法的 'Aid'（本子ID）
  - 消除 YAML 文件被反复读写修改 base_dir 的副作用
"""

import asyncio
import os
import shutil
from datetime import date

import jmcomic
import yaml
from jmcomic import (
    JmOption, JmAlbumDetail, JmPhotoDetail,
    JmSearchPage, JmCategoryPage,
    JmModuleConfig, JmMagicConstants,
    download_album, Feature,
)
from PIL import Image

from framework_common.utils.random_str import random_str
from run.ai_generated_art.service.antiSFW import process_folder, compress_gifs

# ──────────────────────────────────────────────
# 全局缓存（周/月排行等不需要每次都请求）
# ──────────────────────────────────────────────
_jm_cache: dict = {}

_OPTION_FILE = 'run/resource_collector/jmcomic.yml'


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
        # 直接修改 option 对象，不碰 YAML 文件
        option.dir_rule.base_dir = base_dir
    return option


def _make_preview_downloader(start: int, end: int, album_index: int):
    """
    工厂函数：每次调用都返回一个 **全新的** 预览用 Downloader 类。
    使用局部 class 避免全局状态污染，彻底解决并发/复用时参数串用问题。
    """
    # 用闭包把参数绑定进去，每次调用互相独立
    _start = start
    _end = end
    _album_index = album_index

    class _PreviewDownloader(jmcomic.JmDownloader):
        def do_filter(self, detail):
            # 整本：只取第 album_index 章（1-based）
            if detail.is_album():
                album: JmAlbumDetail = detail
                idx = max(0, min(_album_index - 1, len(album) - 1))
                return [album[idx]]

            # 章节：按 [start:end] 切片
            if detail.is_photo():
                photo: JmPhotoDetail = detail
                s = max(0, _start)
                e = _end if _end > 0 else len(photo)
                e = min(e, len(photo))
                # 防止无效区间
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
    """本周排行，有日级缓存。"""
    today = date.today()
    cache_key = f'{today}_week'
    if cache_key in _jm_cache:
        return _jm_cache[cache_key]

    cl = JmOption.default().new_jm_client()
    lines = []
    for page in cl.categories_filter_gen(
        page=1,
        time=JmMagicConstants.TIME_WEEK,
        category=JmMagicConstants.CATEGORY_ALL,
        order_by=JmMagicConstants.ORDER_BY_VIEW,
    ):
        for aid, atitle in page:
            lines.append(f'[{aid}]: {atitle}')
            if len(lines) >= 20:
                break
        break  # 只取第一页

    result = '\n'.join(lines)
    _jm_cache[cache_key] = result
    return result


def JM_search_month() -> list:
    """本月热门榜，返回 album_id 列表，有日级缓存。"""
    today = date.today()
    cache_key = f'{today}_month'
    if cache_key in _jm_cache:
        return _jm_cache[cache_key]

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

    _jm_cache[cache_key] = result
    return result


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
        comic_id   : 禁漫车牌号
        start      : 图片起始下标（1-based，含）
        end        : 图片结束下标（1-based，不含）；0 表示全部
        anti_nsfw  : 反 NSFW 处理方式（"black_and_white" / "gif" / "no_censor"）
        gif_compress: 是否压缩 gif
    """
    temp_dir = f'data/pictures/benzi/temp{comic_id}'
    os.makedirs(temp_dir, exist_ok=True)

    # ── 1. 构造独立的 Downloader 并注册 ──────────────────────
    # start/end 在 do_filter 中是 0-based 切片，外部传入 1-based，这里转换
    slice_start = max(0, start - 1)  # 1→0, 0→0（防呆）
    slice_end = end                  # end 本身就是切片右边界（不含）

    PreviewDownloader = _make_preview_downloader(
        start=slice_start,
        end=slice_end,
        album_index=1,  # 始终只下载第一章
    )
    PreviewDownloader.use()  # 注册为当前 Downloader

    # ── 2. 构造 option（不修改 YAML 文件）─────────────────────
    option = _load_option(base_dir=temp_dir)

    # ── 3. 下载 ───────────────────────────────────────────────
    jmcomic.download_album(comic_id, option)

    # ── 4. 恢复默认 Downloader，避免污染后续调用 ─────────────
    jmcomic.JmDownloader.use()

    # ── 5. 后处理：反 NSFW ────────────────────────────────────
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
            src = os.path.join(temp_dir, fname)
            img = Image.open(src).convert('1')
            dst = f'data/pictures/cache/{random_str()}.png'
            img.save(dst)
            new_files.append(dst)

    elif anti_nsfw == "no_censor":
        for fname in file_names:
            src = os.path.join(temp_dir, fname)
            dst = os.path.join('data/pictures/cache', fname)
            shutil.move(src, dst)
            new_files.append(dst)

    return new_files


def downloadALLAndToPdf(comic_id, save_path: str) -> str:
    """
    全本下载并导出为 PDF。
    文件名格式：{save_path}/[JM{comic_id}]本子标题.pdf（由 jmcomic 自动生成）

    返回值：PDF 文件完整路径（不含 .pdf 后缀，以兼容原有调用方）。
    注意：调用方拼接路径时记得加 .pdf。
    """
    download_album(
        str(comic_id),
        extra=Feature.export_pdf(
            pdf_dir=save_path,
            filename_rule='Aid',          # 'Aid' = 本子 ID，合法的内置规则字段
            delete_original_file=True,    # 导出后删除原图，节省磁盘
        ),
    )
    # 返回无后缀路径以兼容调用方的 f"{r}.pdf" 拼接写法
    return os.path.join(save_path, str(comic_id))