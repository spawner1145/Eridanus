"""
明日方舟 · 卫戍协议风格头像生成器
完美还原 Vue 源码：修正 farthest-corner 径向渐变，取消自作聪明的扫描线放大
"""

import sys
import asyncio
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

ASSETS_DIR = Path(__file__).parent  # av-icon.png / av-text-1.png 所在目录


def make_radial_gradient_mask(size: int) -> Image.Image:
    """严格还原 .av-cover 的 CSS radial-gradient（最远角匹配）"""
    bg = np.array([50, 50, 50], dtype=np.float32)
    arr = np.zeros((size, size, 4), dtype=np.float32)

    cx = (size - 1) / 2.0
    cy = (size - 1) / 2.0
    max_dist = np.sqrt(cx**2 + cy**2)

    Y, X = np.mgrid[0:size, 0:size]
    dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2) / max_dist

    # 使用原汁原味的 Vue 源码透明度停点
    alpha = np.where(
        dist <= 0.33, 0.0,
        np.where(
            dist <= 0.40, (dist - 0.33) / (0.40 - 0.33) * 0.1,
            np.where(
                dist <= 0.50, 0.1 + (dist - 0.40) / (0.50 - 0.40) * 0.3,
                np.where(
                    dist <= 0.65, 0.4 + (dist - 0.50) / (0.65 - 0.50) * 0.6,
                    1.0,
                ),
            ),
        ),
    )

    arr[:, :, 0] = bg[0]
    arr[:, :, 1] = bg[1]
    arr[:, :, 2] = bg[2]
    arr[:, :, 3] = alpha * 255

    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def make_scanline_grid(size: int, filter_strength: float) -> Image.Image:
    """
    还原 .preview-grid 扫描线。
    【核心修复】：移除等比例放大！直接使用 CSS 里的绝对像素 3px 和 5px。
    在 1000px 的画幅下，150 根 3px 的细线会形成非常细腻的科技感纹理，而不会喧宾夺主。
    """
    green_alpha = int(filter_strength / 200 * 255)
    grid = Image.new("RGBA", (size, size), (0, 255, 189, green_alpha))
    d = ImageDraw.Draw(grid)

    line_h = 3
    margin_top = 5

    line_color = (255, 255, 255, int(0.1 * 255))
    y = margin_top
    for _ in range(150):
        d.rectangle([0, y, size - 1, y + line_h - 1], fill=line_color)
        y += line_h + margin_top
        if y > size:  # 超出画布范围则停止绘制
            break

    return grid


def _load_and_crop_square(path: str, size: int, zoom: float = 1.0) -> Image.Image:
    """读取图片，居中正方形裁剪后缩放到 size×size。"""
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    short = min(w, h)

    crop_size = int(short / max(0.1, zoom))
    crop_size = min(crop_size, short)

    left = (w - crop_size) // 2
    top  = (h - crop_size) // 2
    img = img.crop((left, top, left + crop_size, top + crop_size))
    return img.resize((size, size), Image.LANCZOS)


def composite_sync(
    user_photo_path: str,
    output_path: str = "output.png",
    filter_strength: float = 50,
    offset_x: float = 0,
    offset_y: float = 0,
    show_badge: bool = True,
    zoom: float = 1.0,
    canvas_size: int = 1000,
    assets_dir: str | None = None,
) -> Image.Image:

    adir = Path(assets_dir) if assets_dir else ASSETS_DIR
    S = canvas_size

    # 1. Vue stage 背景色：rgba(50, 50, 50, 1)
    canvas = Image.new("RGBA", (S, S), (50, 50, 50, 255))

    # 2. .preview-avatar 容器 (95%)
    avatar_size   = int(S * 0.95)
    avatar_offset = (S - avatar_size) // 2

    # 2a. 用户照片
    photo = _load_and_crop_square(user_photo_path, avatar_size, zoom=zoom)
    canvas.alpha_composite(photo, (avatar_offset, avatar_offset))

    # 2b. 扫描线及暗化滤镜层
    grid = make_scanline_grid(avatar_size, filter_strength)
    canvas.alpha_composite(grid, (avatar_offset, avatar_offset))

    # 3. .av-cover 径向渐变遮罩 (102% 大小，-1% 偏移进行完美居中)
    cover_size = int(avatar_size * 1.02)
    cover_off  = avatar_offset - int(avatar_size * 0.01)
    cover = make_radial_gradient_mask(cover_size)
    canvas.alpha_composite(cover, (cover_off, cover_off))

    # 4. 文字贴图
    av_text = Image.open(adir / "av-text-1.png").convert("RGBA")
    av_text = av_text.resize((S, S), Image.LANCZOS)
    canvas.alpha_composite(av_text)

    # 5. 角标
    if show_badge:
        icon_size  = int(S * 0.40)
        icon_top   = int((-6 + offset_y) / 100 * S)
        icon_right = int((-6 + offset_x) / 100 * S)
        icon_left  = S - icon_size - icon_right

        av_icon = Image.open(adir / "av-icon.png").convert("RGBA")
        av_icon = av_icon.resize((icon_size, icon_size), Image.LANCZOS)
        canvas.alpha_composite(av_icon, (icon_left, icon_top))

    # 6. 保存
    result = canvas.convert("RGB")
    if output_path:
        result.save(output_path, quality=95)
        print(f"✅ 已保存: {output_path}")
    return result


async def composite_async(
    user_photo_path: str,
    output_path: str = "output.png",
    filter_strength: float = 50,
    offset_x: float = 0,
    offset_y: float = 0,
    show_badge: bool = True,
    zoom: float = 1.0,
    canvas_size: int = 1000,
    assets_dir: str | None = None,
) -> Image.Image:

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: composite_sync(
            user_photo_path,
            output_path,
            filter_strength,
            offset_x,
            offset_y,
            show_badge,
            zoom,
            canvas_size,
            assets_dir,
        ),
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python generator.py <头像图片>[输出] [filter] [offset_x] [offset_y] [show_badge] [zoom]")
        sys.exit(1)

    _photo  = sys.argv[1]
    _output = sys.argv[2] if len(sys.argv) > 2 else "output.png"
    _filter = float(sys.argv[3]) if len(sys.argv) > 3 else 50
    _off_x  = float(sys.argv[4]) if len(sys.argv) > 4 else 0
    _off_y  = float(sys.argv[5]) if len(sys.argv) > 5 else 0
    _badge  = (sys.argv[6] != "0") if len(sys.argv) > 6 else True
    _zoom   = float(sys.argv[7]) if len(sys.argv) > 7 else 1.0

    asyncio.run(composite_async(_photo, _output, _filter, _off_x, _off_y, _badge, _zoom))