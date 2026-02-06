import asyncio
import math
from pathlib import Path
from textwrap import shorten
from typing import List, Dict

from PIL import Image, ImageDraw, ImageFont


# =====================
# 布局参数
# =====================
POPULAR_COLUMNS = 3
MIN_LATEST_COLUMNS = 3
MAX_LATEST_COLUMNS = 8

THUMB_SIZE = (220, 300)
CARD_PADDING = 16
TITLE_HEIGHT = 48

BG_COLOR = (18, 18, 18)
TEXT_COLOR = (240, 240, 240)

FONT = ImageFont.load_default()


# =====================
# 工具函数
# =====================
def calc_balanced_columns(
    count: int,
    min_cols: int = MIN_LATEST_COLUMNS,
    max_cols: int = MAX_LATEST_COLUMNS,
) -> int:
    if count <= 0:
        return min_cols
    cols = math.ceil(math.sqrt(count))
    return max(min_cols, min(cols, max_cols))


def calc_canvas_size(count: int, columns: int) -> tuple[int, int]:
    rows = max(1, math.ceil(count / columns))
    width = columns * THUMB_SIZE[0] + (columns + 1) * CARD_PADDING
    height = (
        rows * (THUMB_SIZE[1] + TITLE_HEIGHT)
        + (rows + 1) * CARD_PADDING
    )
    return width, height


def _load_thumb(path: str) -> Image.Image:
    img = Image.open(path)
    img.thumbnail(THUMB_SIZE)
    return img


# =====================
# 绘制 + 位置映射
# =====================
async def _render_section(
    items: List[Dict],
    columns: int,
    out_path: Path,
) -> Dict:
    width, height = calc_canvas_size(len(items), columns)

    canvas = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    layout_items = []

    for idx, item in enumerate(items):
        col = idx % columns
        row = idx // columns

        x = CARD_PADDING + col * (THUMB_SIZE[0] + CARD_PADDING)
        y = CARD_PADDING + row * (THUMB_SIZE[1] + TITLE_HEIGHT + CARD_PADDING)

        # 图片
        img = await asyncio.to_thread(_load_thumb, item["preview"])
        canvas.paste(img, (x, y))
        img.close()

        # 标题
        title = shorten(item["title"], width=40, placeholder="…")
        draw.text(
            (x, y + THUMB_SIZE[1] + 6),
            title,
            fill=TEXT_COLOR,
            font=FONT,
        )

        # 记录布局（row / col 从 1 开始）
        layout_items.append({
            "row": row + 1,
            "col": col + 1,
            "title": item["title"],
            "preview": item["preview"],
            "url": item["url"],
        })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(canvas.save, out_path, "PNG", optimize=True)
    canvas.close()

    return {
        "image": str(out_path),
        "columns": columns,
        "items": layout_items,
    }


# =====================
# 对外 API
# =====================
async def render_hitomi_sections(
    popular: List[Dict],
    latest: List[Dict],
    out_dir: str = "data/pictures",
) -> Dict:
    out_dir = Path(out_dir)

    popular_path = out_dir / "popular.png"
    latest_path = out_dir / "latest.png"

    latest_columns = calc_balanced_columns(len(latest))

    popular_result, latest_result = await asyncio.gather(
        _render_section(
            popular,
            columns=POPULAR_COLUMNS,
            out_path=popular_path,
        ),
        _render_section(
            latest,
            columns=latest_columns,
            out_path=latest_path,
        ),
    )

    return {
        "popular": popular_result,
        "latest": latest_result,
    }
