# -*- coding: utf-8 -*-
"""
封面反 NSFW 处理升级补丁 (深度学习对抗增强版)
将此完整代码替换 jmComic.py 中原有的 download_cover_bw() 及其相关依赖。

设计目标：
  - 保持图片"大致可辨"（依靠人脑的完形心理学脑补能力）
  - 彻底破坏 AI 的特征提取：通过网格、错位切断连续曲线（对抗 CNN）
  - 通过色阶、色相变换对抗颜色直方图特征
  - 每次处理引入随机参数，避免固定变换被特征库记录
  - 纯 Pillow + numpy 实现
"""

import os
import random
from typing import Literal

import numpy as np
from PIL import Image, ImageOps

from framework_common.utils.random_str import random_str

# ─── 可调参数（若觉得图片太难看清，可以微调这些参数） ───────────────────────
_HUE_SHIFT_RANGE = (90, 150)  # 色相旋转角度范围（度）
_SAT_FACTOR_RANGE = (0.25, 0.45)  # 饱和度乘数范围（越小越灰，结构保留）
_ROT_ANGLE_RANGE = (2.0, 6.0)  # 旋转角度绝对值范围（度）
_NOISE_RANGE = (8, 18)  # 每像素噪声幅度范围（0-255）
_PIXELATE_SCALE = (0.25, 0.4)  # 像素化缩小比例（越小马赛克越大，1.0为无变化）
_GLITCH_SHIFT_MAX = 8  # 切片错位的最大像素数（破坏线条连续性）
_SCANLINE_INTERVAL = (4, 7)  # 扫描线间隔像素（越小网格越密）


# ──────────────────────────────────────────────────────────────────


# ─── 传统感知哈希/颜色对抗处理 ───────────────────────────────────────

def _hue_rotate(img: Image.Image, shift: int) -> Image.Image:
    """将 RGB 转到 HSV，偏移 H 通道后转回，规避肤色检测"""
    arr = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    maxc = arr.max(axis=2)
    minc = arr.min(axis=2)
    v = maxc
    s = np.where(maxc != 0, (maxc - minc) / maxc, 0.0)

    delta = maxc - minc + 1e-9
    h = np.zeros_like(maxc)
    mask_r = (maxc == r) & (maxc != minc)
    mask_g = (maxc == g) & (maxc != minc)
    mask_b = (maxc == b) & (maxc != minc)
    h[mask_r] = (60 * ((g - b) / delta))[mask_r] % 360
    h[mask_g] = (60 * ((b - r) / delta) + 120)[mask_g]
    h[mask_b] = (60 * ((r - g) / delta) + 240)[mask_b]

    h = (h + shift) % 360

    h6 = h / 60.0
    i = h6.astype(int) % 6
    f = h6 - np.floor(h6)
    p = v * (1 - s)
    q = v * (1 - s * f)
    t_ = v * (1 - s * (1 - f))

    out = np.zeros_like(arr)
    for idx, (c0, c1, c2) in enumerate([(v, t_, p), (q, v, p), (p, v, t_), (p, q, v), (t_, p, v), (v, p, q)]):
        m = i == idx
        out[m, 0], out[m, 1], out[m, 2] = c0[m], c1[m], c2[m]

    out = (np.clip(out, 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(out, "RGB")


def _channel_shuffle(img: Image.Image) -> Image.Image:
    """随机通道重排（排除原始 RGB 顺序），打乱颜色直方图"""
    orders = [(0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)]
    order = random.choice(orders)
    arr = np.array(img.convert("RGB"))
    out = arr[:, :, list(order)]
    return Image.fromarray(out, "RGB")


def _compress_saturation(img: Image.Image, factor: float) -> Image.Image:
    """饱和度压缩：图像整体偏灰，但轮廓层次清晰"""
    arr = np.array(img.convert("RGB"), dtype=np.float32)
    gray = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
    gray = gray[..., np.newaxis]
    out = gray + (arr - gray) * factor
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def _random_rotate(img: Image.Image, angle: float) -> Image.Image:
    """小角度旋转，白色背景填充，破坏逐像素对齐"""
    direction = random.choice([-1, 1])
    return img.rotate(
        angle * direction,
        resample=Image.BICUBIC,
        expand=False,
        fillcolor=(255, 255, 255),
    )


def _add_noise(img: Image.Image, amplitude: int) -> Image.Image:
    """均匀随机噪声叠加，改变局部哈希值"""
    arr = np.array(img.convert("RGB"), dtype=np.int16)
    noise = np.random.randint(-amplitude, amplitude + 1, arr.shape, dtype=np.int16)
    out = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGB")


# ─── 现代 AI (深度学习/CNN) 特征破坏处理 ──────────────────────────────

def _pixelate(img: Image.Image, scale_factor: float) -> Image.Image:
    """像素化：通过缩小再用最近邻放大，移除高频敏感细节纹理"""
    w, h = img.size
    small = img.resize((max(1, int(w * scale_factor)), max(1, int(h * scale_factor))), Image.BILINEAR)
    return small.resize((w, h), Image.NEAREST)


def _apply_scanlines(img: Image.Image, interval: int) -> Image.Image:
    """扫描线/网格干扰：引入密集人造直线边缘，使 CNN 卷积核提取混乱"""
    arr = np.array(img)
    color = random.choice([0, 255])  # 随机选择纯黑或纯白线条
    # 水平线
    arr[::interval, :, :] = color
    # 50%概率加上垂直线形成网格，大幅增加 AI 识别难度
    if random.random() > 0.5:
        arr[:, ::interval, :] = color
    return Image.fromarray(arr)


def _glitch_shift(img: Image.Image, max_shift: int) -> Image.Image:
    """水平切片错位：将图像横向切分并错位，打断连续的身体曲线和轮廓线"""
    arr = np.array(img)
    h, w, _ = arr.shape
    chunk_size = random.randint(10, 30)
    for y in range(0, h, chunk_size):
        shift = random.randint(-max_shift, max_shift)
        arr[y:y + chunk_size] = np.roll(arr[y:y + chunk_size], shift, axis=1)
    return Image.fromarray(arr)


def _posterize(img: Image.Image, bits: int) -> Image.Image:
    """色阶分离：减少颜色层级，产生伪等高线，干扰 AI 对3D圆柱/球体阴影的识别"""
    return ImageOps.posterize(img, bits)


# ─── 公开入口与主流水线 ──────────────────────────────────────────────

def obfuscate_cover(
        img: Image.Image,
        *,
        pixelate: bool = True,
        glitch_shift: bool = True,
        scanlines: bool = True,
        posterize: bool = True,
        hue_rotate: bool = True,
        chan_shuffle: bool = True,
        sat_compress: bool = True,
        small_rotate: bool = True,
        add_noise: bool = True,
) -> Image.Image:
    """
    对封面图执行多层混淆处理流水线，返回处理后的 PIL Image (RGB)。
    """
    img = img.convert("RGB")

    # 1. 结构与纹理破坏 (针对 CNN 和 ViT 模型)
    if pixelate:
        scale = random.uniform(*_PIXELATE_SCALE)
        img = _pixelate(img, scale)

    if glitch_shift:
        img = _glitch_shift(img, _GLITCH_SHIFT_MAX)

    # 2. 色彩与阴影拓扑破坏
    if posterize:
        bits = random.randint(3, 5)  # 3-5 bit 能产生伪轮廓且不至于过黑
        img = _posterize(img, bits)

    if hue_rotate:
        shift = random.randint(*_HUE_SHIFT_RANGE)
        shift = 360 - shift if random.random() < 0.5 else shift
        img = _hue_rotate(img, shift)

    # 通道重排对人类视觉有一定冲击，设为 70% 概率触发
    if chan_shuffle and random.random() < 0.7:
        img = _channel_shuffle(img)

    if sat_compress:
        factor = random.uniform(*_SAT_FACTOR_RANGE)
        img = _compress_saturation(img, factor)

    # 3. 强力人造边缘引入 (致命打断 AI 的边缘与轮廓识别)
    if scanlines:
        interval = random.randint(*_SCANLINE_INTERVAL)
        img = _apply_scanlines(img, interval)

    # 4. 传统微调破坏 (针对 pHash/dHash 特征计算)
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
    下载封面并执行反 NSFW 混淆处理，返回本地图片路径。
    失败时返回 None，便于调用方优雅降级。
    """
    from jmcomic import JmOption
    try:
        client = JmOption.default().new_jm_client()
        raw_path = f'data/pictures/cache/cover_raw_{comic_id}_{random_str()}.jpg'

        # 确保缓存目录存在
        os.makedirs(os.path.dirname(raw_path), exist_ok=True)

        # 下载原图
        client.download_album_cover(str(comic_id), raw_path)

        dst = f'data/pictures/cache/cover_{comic_id}_{random_str()}.png'

        if anti_nsfw == "obfuscate":
            # 开启高强度 AI 混淆
            img = Image.open(raw_path)
            obfuscated_img = obfuscate_cover(img)
            obfuscated_img.save(dst, format="PNG")
            os.remove(raw_path)

        elif anti_nsfw == "black_and_white":
            # 兼容旧版本：纯粹的二值化黑白处理
            Image.open(raw_path).convert("1").save(dst)
            os.remove(raw_path)

        else:
            # no_censor：不作审查处理，保留原图
            os.rename(raw_path, dst)

        return dst

    except Exception as e:
        # 捕获异常返回 None。如需调试可取消下一行的注释：
        # print(f"Download cover failed: {e}")
        return None