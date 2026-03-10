import json
import os
from PIL import Image, ImageDraw, ImageFont
from typing import Optional


def generate_meme_key_image(json_file_path: str) -> Optional[str]:
    """
    根据指定的JSON文件路径，生成meme表情包关键字列表图片，并返回图片保存路径
    """
    # 读取并解析JSON文件 
    if not os.path.exists(json_file_path):
        print(f"错误：JSON文件不存在 -> {json_file_path}")
        return None
    
    try:
        with open(json_file_path, "r", encoding="utf-8") as f:
            meme_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"错误：JSON文件解析失败 -> {e}")
        return None
    except Exception as e:
        print(f"错误：读取JSON文件异常 -> {e}")
        return None
    
    # 提取关键字
    meme_keys = list(meme_data.keys())
    
    # 创建带有图标的文本列表
    texts = []
    for key in meme_keys:
        config = meme_data[key]
        pic_num = config.get("min_img_num", 0)
        str_num = config.get("string_num", 0)
        if pic_num > 0 and str_num == 0:
            icon = "[图]"  # 仅图片标识
        elif str_num > 0 and pic_num == 0:
            icon = "[文]"  # 需要字符串标识
        elif pic_num > 0 and str_num > 0:
            icon = "[图文]"  # 同时需要图片和字符串标识
        else:
            icon = ""
        text = f"{icon} {key}" if icon else key
        texts.append(text)
    
    # 图片样式配置
    # 基础配置
    font_size = 24  # 字体大小
    col_num = 5     # 列数
    padding = 40    # 图片内边距
    line_spacing = 15  # 行间距
    col_spacing = 60   # 列间距
    bg_color = (255, 255, 255)  # 背景色
    text_color = (0, 0, 0)      # 文字色
    
    # 字体配置
    # 适配不同系统的字体路径
    font_paths = [
        "C:/Windows/Fonts/SimHei.ttf",          # Windows 黑体
        "/System/Library/Fonts/PingFang.ttc",   # Mac 苹方
        "/usr/share/fonts/truetype/noto/NotoSansCJK-SC.ttf"  # Linux 思源黑体
    ]
    font = None
    for font_path in font_paths:
        if os.path.exists(font_path):
            if "PingFang.ttc" in font_path:
                font = ImageFont.truetype(font_path, font_size, index=0)
            else:
                font = ImageFont.truetype(font_path, font_size)
            break
    if not font:
        # 若未找到系统字体，尝试使用默认字体
        font = ImageFont.load_default(size=font_size)
        print("警告：未找到指定的字体")

    # 计算图片尺寸
    # 计算单行列数和总行数
    row_num = (len(meme_keys) + col_num - 1) // col_num
    # 计算单字最大宽度/高度
    max_text_width = max([font.getbbox(text)[2] - font.getbbox(text)[0] for text in texts])
    max_text_height = max([font.getbbox(text)[3] - font.getbbox(text)[1] for text in texts])
    # 计算图片宽度和高度
    img_width = padding * 2 + col_num * max_text_width + (col_num - 1) * col_spacing
    img_height = padding * 2 + row_num * (max_text_height + line_spacing) - line_spacing

    # 绘制图片
    # 创建画布
    img = Image.new("RGB", (img_width, img_height), bg_color)
    draw = ImageDraw.Draw(img)
    
    # 逐行逐列绘制文字
    for idx, text in enumerate(texts):
        # 计算当前文字的行列索引
        row_idx = idx // col_num
        col_idx = idx % col_num
        # 计算文字绘制坐标
        x = padding + col_idx * (max_text_width + col_spacing)
        y = padding + row_idx * (max_text_height + line_spacing)
        # 绘制文字
        draw.text((x, y), text, fill=text_color, font=font)

    # 保存图片
    # 生成图片保存路径（与JSON文件同目录）
    img_dir = os.path.dirname(json_file_path)
    img_path = os.path.join(img_dir, "meme_keys.jpg")
    try:
        img.save(img_path, quality=95)
        print(f"图片生成成功 -> {img_path}")
        return img_path
    except Exception as e:
        print(f"错误：保存图片失败 -> {e}")
        return None


# 测试调用 
if __name__ == "__main__":
    json_path = "./run/meme_generate/config/mapping.json"
    image_path = generate_meme_key_image(json_path)