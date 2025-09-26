from PIL import Image, ImageDraw, ImageFilter, ImageOps,ImageFont
from datetime import datetime
import calendar
import weakref
import time
import os
from .data_deal import date_get
import random
import string

async def img_rounded(img):
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, img.width, img.height), radius=23, fill=255, outline=255,width=2)
    rounded_image = Image.new("RGBA", img.size)
    rounded_image.paste(img, (0, 0), mask=mask)
    return rounded_image

async def img_text_draw(canvas,font,size,text,box):
    draw = ImageDraw.Draw(canvas)
    if '🦌' not in text:
        draw.text(box, text, font=font, fill=(0, 0, 0))
    elif '🦌' in text:
        index = text.find('🦌')
        before_flag = text[:index]   # 标志前的字符
        after_flag = text[index + len('🦌'):]  # 标志后的字符
        x, y =box
        draw.text((x, y), before_flag, font=font, fill=(0, 0, 0))
        char_width = font.getbbox(before_flag)[2] - font.getbbox(before_flag)[0]
        lu_path = 'run/group_fun/service/lu/core/data/🦌.png'
        lu_img = Image.open(lu_path).resize((size, size))
        if lu_img.mode != 'RGBA':
            lu_img = lu_img.convert('RGBA')
        canvas.paste(lu_img, (x+char_width+1, y+2),mask=lu_img.split()[-1])
        draw.text((x+char_width+size+2, y), after_flag, font=font, fill=(0, 0, 0))

async def lu_img_maker(user_info,content='枫与岚',day_info=None):
    if day_info is None: day_info = await date_get()
    canvas = Image.new("RGBA", (960, 960), (235, 239, 253, 255))
    font_path = 'run/group_fun/service/lu/core/data/LXGWWenKai-Regular.ttf'
    font = ImageFont.truetype(font_path, 24)
    font_title = ImageFont.truetype(font_path, 34)

    draw = ImageDraw.Draw(canvas)

    x, y, title_flag = 20, 20, True
    for item in content:
        if title_flag:
            await img_text_draw(canvas,font_title,34,item,(x,y))
            y += 34
            title_flag = False
        else:
            await img_text_draw(canvas, font, 24, item, (x, y))
            y += 24
        y += 15

    first_day_of_week = datetime(datetime.now().year, datetime.now().month, 1).weekday() + 1
    if first_day_of_week == 7: first_day_of_week = 0

    img_lu_path = 'run/group_fun/service/lu/core/data/background_LU.jpg'
    background_make = Image.open(img_lu_path)
    img_width = (canvas.width - 2*20 + 15) // 7 - 15
    img_height = int(img_width * background_make.height / background_make.height *0.92)
    background_make = background_make.resize((img_width, img_height))
    background_make_L = Image.new("RGBA", background_make.size, (255, 255, 255, 255))
    background_make_L.putalpha(background_make.convert('L'))
    #为其添加圆角
    background_make = await img_rounded(background_make)
    background_make_L = await img_rounded(background_make_L)
    img_list = []

    weeky = ['周日', '周一', '周二', '周三', '周四', '周五', '周六', '周日']
    for i in range(7):
        week_img_canves = Image.new("RGBA", background_make.size, (255, 255, 255, 255))
        draw_week = ImageDraw.Draw(week_img_canves)
        draw_week.text((25, 30), weeky[i], font=font_title, fill=(0, 0, 0))
        week_img_canves = await img_rounded(week_img_canves)
        img_list.append(week_img_canves)

    _, days_total = calendar.monthrange(datetime.now().year, datetime.now().month)
    no_color_img = Image.new("RGBA", background_make.size, (0, 0, 0, 0))
    for i in range(first_day_of_week):img_list.append(no_color_img)

    check_num = 0
    y += 20
    #print(len(img_list),days_total)
    for i in range(len(img_list) + days_total):
        if i < len(img_list):
            canvas.paste(img_list[i], (int(x), int(y)), mask=img_list[i])
        else:
            check_i = i - len(img_list) + 1
            if f"{day_info['month']}_{check_i}" in user_info['lu_done']['data']:
                canvas.paste(background_make, (int(x), int(y)), mask=background_make)
                if user_info['lu_done']['data'][f"{day_info['month']}_{check_i}"] not in [0,1]:
                    time_str = user_info['lu_done']['data'][f"{day_info['month']}_{check_i}"]
                    draw.text((int(x + 15), int(y + 63)), f'×{time_str}', font=font, fill=(255,0,0))
            else:
                canvas.paste(background_make_L, (int(x), int(y)), mask=background_make_L)
                draw.text((int(x+35), int(y+33)), str(check_i), font=font_title, fill=(0, 0, 0))

        check_num += 1
        x += img_width + 15
        if check_num == 7:
            x = 20
            y += img_height + 15
            check_num = 0
    random_string = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
    img_path = f"data/pictures/cache/{random_string}.png"
    #img_path = f"run/group_fun/service/lu/cache/{random_string}.png"
    canvas = await img_rounded(canvas)
    canvas_back = Image.new("RGBA", (canvas.width+40, canvas.height+40), (194, 228, 255, 255))
    canvas_back.paste(canvas, (20,20), mask=canvas)
    basic_img = canvas_back.convert("RGB")
    basic_img.save(img_path, "PNG")
    return img_path






