# -*- coding: utf-8 -*-
"""
封面反 NSFW 处理升级补丁
将此函数替换 jmComic.py 中原有的 download_cover_bw()。

设计目标：
  - 保持图片"大致可辨"（封面构图、文字、颜色区块肉眼仍可分辨）
  - 多层变换堆叠，使感知哈希/颜色直方图特征远离原图
  - 每次处理引入随机参数，避免固定变换被特征库记录
  - 纯 Pillow + numpy，不引入新依赖

处理流水线（可配置，默认全开）：
  1. 色相旋转       hue_shift ∈ [90, 150] 度，随机方向
  2. 通道重排       随机选一种非原始排列（BRG / GBR 等）
  3. 饱和度压缩     S *= 0.25~0.45，亮度 V 保持，图像偏灰但结构清晰
  4. 小角度随机旋转  ±[2, 6]°，补白色边，破坏像素对齐特征
  5. 轻微噪声叠加   每像素 ±[8, 18] 随机整数，人眼几乎察觉不到
"""

import os
import random
from typing import Literal

import numpy as np
from PIL import Image

from framework_common.utils.random_str import random_str

# ─── 可调参数 ──────────────────────────────────────────────────────
_HUE_SHIFT_RANGE   = (90, 150)   # 色相旋转角度范围（度）
_SAT_FACTOR_RANGE  = (0.25, 0.45) # 饱和度乘数范围（越小越灰，但结构保留）
_ROT_ANGLE_RANGE   = (2.0, 6.0)   # 旋转角度绝对值范围（度）
_NOISE_RANGE       = (8, 18)      # 每像素噪声幅度范围（0-255）
# ──────────────────────────────────────────────────────────────────


# ─── 各处理步骤 ────────────────────────────────────────────────────

def _hue_rotate(img: Image.Image, shift: int) -> Image.Image:
    """
    色相旋转：将 RGB 转到 HSV，偏移 H 通道后转回。
    shift 范围 0-360，推荐 90-150 以保证颜色明显变化但图像仍可辨。
    人体皮肤色调（约 15-35°）旋转后落在绿/青/蓝区，
    使肤色不再触发肤色检测器，同时轮廓、对比度完整保留。
    """
    arr = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
    # RGB → HSV（纯 numpy，避免 colorsys 的逐像素 Python 循环）
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    maxc = arr.max(axis=2)
    minc = arr.min(axis=2)
    v    = maxc
    s    = np.where(maxc != 0, (maxc - minc) / maxc, 0.0)

    delta = maxc - minc + 1e-9
    h = np.zeros_like(maxc)
    mask_r = (maxc == r) & (maxc != minc)
    mask_g = (maxc == g) & (maxc != minc)
    mask_b = (maxc == b) & (maxc != minc)
    h[mask_r] = (60 * ((g - b) / delta))[mask_r] % 360
    h[mask_g] = (60 * ((b - r) / delta) + 120)[mask_g]
    h[mask_b] = (60 * ((r - g) / delta) + 240)[mask_b]

    h = (h + shift) % 360  # ← 旋转色相

    # HSV → RGB
    h6 = h / 60.0
    i  = h6.astype(int) % 6
    f  = h6 - np.floor(h6)
    p  = v * (1 - s)
    q  = v * (1 - s * f)
    t_ = v * (1 - s * (1 - f))

    out = np.zeros_like(arr)
    for idx, (c0, c1, c2) in enumerate([(v,t_,p),(q,v,p),(p,v,t_),(p,q,v),(t_,p,v),(v,p,q)]):
        m = i == idx
        out[m, 0], out[m, 1], out[m, 2] = c0[m], c1[m], c2[m]

    out = (np.clip(out, 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(out, "RGB")


def _channel_shuffle(img: Image.Image) -> Image.Image:
    """
    随机通道重排（排除原始 RGB 顺序）。
    颜色分布直方图被彻底打乱，但亮度对比、边缘、构图完整。
    可选排列：GBR, BRG, RBG, BGR, GRB（不含 RGB）
    """
    orders = [(0,2,1),(1,0,2),(1,2,0),(2,0,1),(2,1,0)]  # 排除 (0,1,2)
    order  = random.choice(orders)
    arr    = np.array(img.convert("RGB"))
    out    = arr[:, :, list(order)]
    return Image.fromarray(out, "RGB")


def _compress_saturation(img: Image.Image, factor: float) -> Image.Image:
    """
    饱和度压缩：图像整体偏灰，但轮廓、层次、文字仍清晰可读。
    factor=0 → 纯灰度；factor=1 → 原色；推荐 0.25~0.45。
    实现：RGB 与灰度图线性混合，比 HSV 转换更快且无色阶断层。
    """
    arr  = np.array(img.convert("RGB"), dtype=np.float32)
    gray = 0.299 * arr[...,0] + 0.587 * arr[...,1] + 0.114 * arr[...,2]
    gray = gray[..., np.newaxis]
    out  = gray + (arr - gray) * factor
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def _random_rotate(img: Image.Image, angle: float) -> Image.Image:
    """
    小角度旋转（±angle 度），白色背景填充。
    破坏像素网格对齐，使感知哈希（pHash/dHash）产生明显偏移。
    """
    direction = random.choice([-1, 1])
    return img.rotate(
        angle * direction,
        resample=Image.BICUBIC,
        expand=False,
        fillcolor=(255, 255, 255),
    )


def _add_noise(img: Image.Image, amplitude: int) -> Image.Image:
    """
    均匀随机噪声叠加（每像素 [-amplitude, +amplitude]）。
    人眼几乎察觉不到（amplitude≤20），但会使逐像素哈希完全改变。
    """
    arr   = np.array(img.convert("RGB"), dtype=np.int16)
    noise = np.random.randint(-amplitude, amplitude + 1, arr.shape, dtype=np.int16)
    out   = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGB")


# ─── 公开入口 ──────────────────────────────────────────────────────

def obfuscate_cover(
    img: Image.Image,
    *,
    hue_rotate:  bool = True,
    chan_shuffle: bool = True,
    sat_compress: bool = True,
    small_rotate: bool = True,
    add_noise:    bool = True,
) -> Image.Image:
    """
    对封面图执行多层混淆处理，返回处理后的 PIL Image（RGB 模式）。

    参数（均可单独关闭）：
        hue_rotate   – 色相旋转，最有效的肤色规避手段
        chan_shuffle  – 通道重排，打乱颜色直方图
        sat_compress  – 饱和度压缩，整体偏灰
        small_rotate  – 小角度旋转，破坏像素对齐
        add_noise     – 轻微噪声，改变逐像素哈希

    处理顺序固定（旋转→重排→饱和→小转→噪声），参数在各自范围内随机取值。
    """
    img = img.convert("RGB")

    if hue_rotate:
        shift = random.randint(*_HUE_SHIFT_RANGE)
        if random.random() < 0.5:
            shift = 360 - shift          # 随机决定旋转方向
        img = _hue_rotate(img, shift)

    if chan_shuffle:
        img = _channel_shuffle(img)

    if sat_compress:
        factor = random.uniform(*_SAT_FACTOR_RANGE)
        img = _compress_saturation(img, factor)

    if small_rotate:
        angle = random.uniform(*_ROT_ANGLE_RANGE)
        img = _random_rotate(img, angle)

    if add_noise:
        amplitude = random.randint(*_NOISE_RANGE)
        img = _add_noise(img, amplitude)

    return img


def download_cover_bw(
    comic_id,
    anti_nsfw: Literal["obfuscate", "black_and_white", "no_censor"] = "obfuscate",
) -> str | None:
    """
    下载封面并做反 NSFW 处理，返回本地文件路径。
    失败时返回 None（不抛出，让调用方降级为纯文字）。

    anti_nsfw 模式：
        "obfuscate"      – 多层混淆（新默认，推荐）
        "black_and_white"– 旧方案，二值化黑白（保留兼容）
        "no_censor"      – 不处理，直接输出原图
    """
    from jmcomic import JmOption
    try:
        client  = JmOption.default().new_jm_client()
        raw_path = f'data/pictures/cache/cover_raw_{comic_id}_{random_str()}.jpg'
        client.download_album_cover(str(comic_id), raw_path)

        dst = f'data/pictures/cache/cover_{comic_id}_{random_str()}.png'

        if anti_nsfw == "obfuscate":
            img = Image.open(raw_path)
            obfuscate_cover(img).save(dst, format="PNG")
            os.remove(raw_path)

        elif anti_nsfw == "black_and_white":
            Image.open(raw_path).convert("1").save(dst)
            os.remove(raw_path)

        else:  # no_censor
            os.rename(raw_path, dst)

        return dst

    except Exception:
        return None