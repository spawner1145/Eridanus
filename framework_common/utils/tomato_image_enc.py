import base64
import os
from io import BytesIO
from PIL import Image
import numpy as np
import math

def gilbert2d(width, height):
    coordinates = []
    if width >= height:
        generate2d(0, 0, width, 0, 0, height, coordinates)
    else:
        generate2d(0, 0, 0, height, width, 0, coordinates)
    return coordinates

def generate2d(x, y, ax, ay, bx, by, coordinates):
    w = abs(ax + ay)
    h = abs(bx + by)
    dax = 1 if ax > 0 else -1 if ax < 0 else 0
    day = 1 if ay > 0 else -1 if ay < 0 else 0
    dbx = 1 if bx > 0 else -1 if bx < 0 else 0
    dby = 1 if by > 0 else -1 if by < 0 else 0
    if h == 1:
        for i in range(w):
            coordinates.append([x, y])
            x += dax
            y += day
        return
    if w == 1:
        for i in range(h):
            coordinates.append([x, y])
            x += dbx
            y += dby
        return
    ax2 = ax // 2
    ay2 = ay // 2
    bx2 = bx // 2
    by2 = by // 2
    w2 = abs(ax2 + ay2)
    h2 = abs(bx2 + by2)
    
    if 2 * w > 3 * h:
        if (w2 % 2) and (w > 2):
            ax2 += dax
            ay2 += day
        generate2d(x, y, ax2, ay2, bx, by, coordinates)
        generate2d(x + ax2, y + ay2, ax - ax2, ay - ay2, bx, by, coordinates)
    else:
        if (h2 % 2) and (h > 2):
            bx2 += dbx
            by2 += dby
        generate2d(x, y, bx2, by2, ax2, ay2, coordinates)
        generate2d(x + bx2, y + by2, ax, ay, bx - bx2, by - by2, coordinates)
        generate2d(x + (ax - dax) + (bx2 - dbx), y + (ay - day) + (by2 - dby),
                   -bx2, -by2, -(ax - ax2), -(ay - ay2), coordinates)

def tomato_encrypt(input_data, save_path=None):
    """
    混淆
    input_data: 图片路径或Base64字符串
    save_path: 
        "self": 覆盖原图
        None: 不保存
        其他路径: 保存到指定路径
    返回：(保存路径, 混淆后图片的Base64编码)
    """
    if os.path.isfile(input_data):
        with open(input_data, 'rb') as f:
            image_data = f.read()
    else:
        image_data = base64.b64decode(input_data)
    img = Image.open(BytesIO(image_data))
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGB')
    width, height = img.size
    pixels = np.array(img)
    curve = gilbert2d(width, height)
    total_pixels = width * height
    offset = round((math.sqrt(5) - 1) / 2 * total_pixels)
    new_pixels = np.zeros_like(pixels)
    for i in range(total_pixels):
        old_pos = curve[i]
        new_pos = curve[(i + offset) % total_pixels]
        new_pixels[new_pos[1], new_pos[0]] = pixels[old_pos[1], old_pos[0]]
    output_img = Image.fromarray(new_pixels)
    output_buffer = BytesIO()
    output_img.save(output_buffer, format='PNG')
    base64_result = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
    path = None
    if save_path == "self":
        save_path_png = input_data.replace(os.path.splitext(input_data)[1], '.png')
        output_img.save(save_path_png, format='PNG')
        path = save_path_png
    elif save_path:
        save_path_png = save_path if save_path.endswith('.png') else f"{save_path}.png"
        output_img.save(save_path_png, format='PNG')
        path = save_path_png
    return path, base64_result

def tomato_decrypt(input_data, save_path=None):
    """
    解混淆
    input_data: 图片路径或Base64字符串
    save_path: 
        "self": 覆盖原图
        None: 不保存
        其他路径: 保存到指定路径
    返回：(保存路径, 解混淆后图片的Base64编码)
    """
    # 读取输入图片（混淆图）
    if os.path.isfile(input_data):
        with open(input_data, 'rb') as f:
            image_data = f.read()
    else:
        image_data = base64.b64decode(input_data)
    img = Image.open(BytesIO(image_data))
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGB')
    width, height = img.size
    pixels = np.array(img)
    curve = gilbert2d(width, height)
    total_pixels = width * height
    offset = round((math.sqrt(5) - 1) / 2 * total_pixels)
    new_pixels = np.zeros_like(pixels)
    for i in range(total_pixels):
        old_pos = curve[i]
        new_pos = curve[(i + offset) % total_pixels]
        new_pixels[old_pos[1], old_pos[0]] = pixels[new_pos[1], new_pos[0]]
    output_img = Image.fromarray(new_pixels)
    output_buffer = BytesIO()
    output_img.save(output_buffer, format='PNG')
    base64_result = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
    path = None
    if save_path == "self":
        save_path_png = input_data.replace(os.path.splitext(input_data)[1], '.png')
        output_img.save(save_path_png, format='PNG')
        path = save_path_png
    elif save_path:
        save_path_png = save_path if save_path.endswith('.png') else f"{save_path}.png"
        output_img.save(save_path_png, format='PNG')
        path = save_path_png
    return path, base64_result
