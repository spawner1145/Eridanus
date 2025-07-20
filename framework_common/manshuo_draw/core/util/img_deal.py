from PIL import Image, ImageDraw, ImageFont, ImageOps,ImageFilter
from .download_img import process_img_download
from .text_deal import basic_img_draw_text
from .common import crop_to_square
import math

async def img_process(params,pure_backdrop ,img ,x_offset ,current_y ,upshift=0,type='img'):
    # 圆角处理
    if params['is_rounded_corners_front'] and params[f'is_rounded_corners_{type}']:
        mask = Image.new("L", img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((0, 0, img.width, img.height), radius=params[f'rounded_{type}_radius'], fill=255, outline=255,
                               width=2)
        rounded_image = Image.new("RGBA", img.size)
        rounded_image.paste(img, (0, 0), mask=mask)
        img = rounded_image

    # 阴影处理
    if params['is_shadow_front'] and params[f'is_shadow_{type}']:
        shadow_image = Image.new("RGBA", pure_backdrop.size, (0, 0, 0, 0))  # 初始化透明图层
        shadow_draw = ImageDraw.Draw(shadow_image)
        # 计算阴影矩形的位置
        shadow_rect = [
            x_offset - params[f'shadow_offset_{type}'],  # 左
            current_y - params[f'shadow_offset_{type}'] + upshift,  # 上
            x_offset + img.width + params[f'shadow_offset_{type}'],  # 右
            current_y + img.height + params[f'shadow_offset_{type}'] + upshift  # 下
        ]
        # 绘制阴影（半透明黑色）
        shadow_draw.rounded_rectangle(shadow_rect, radius=params[f'rounded_{type}_radius'],
                                      fill=(0, 0, 0, params[f'shadow_opacity_{type}']))
        # 对阴影层应用模糊效果
        shadow_image = shadow_image.filter(ImageFilter.GaussianBlur(params[f'blur_radius_{type}']))
        # 将阴影层与底层图像 layer2 合并
        pure_backdrop = Image.alpha_composite(pure_backdrop, shadow_image)

    # 描边处理
    if params['is_stroke_front'] and params[f'is_stroke_{type}']:
        shadow_image = Image.new('RGBA', (img.width + params[f'stroke_{type}_width'], img.height + params[f'stroke_{type}_width']),
                                 (255, 255, 255, 80))
        shadow_blurred = shadow_image.filter(ImageFilter.GaussianBlur(params[f'stroke_{type}_width'] / 2))
        mask = Image.new('L', shadow_blurred.size, 255)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([0, 0, shadow_blurred.size[0], shadow_blurred.size[1]],
                               radius=params[f'stroke_{type}_radius'], fill=0, outline=255, width=2)
        shadow_blurred = ImageOps.fit(shadow_blurred, mask.size, method=0, bleed=0.0, centering=(0.5, 0.5))
        mask = ImageOps.invert(mask)
        shadow_blurred.putalpha(mask)
        pure_backdrop.paste(shadow_blurred,
        (int(x_offset - params[f'stroke_{type}_width'] / 2), int(current_y - params[f'stroke_{type}_width'] / 2 + upshift)),
                            shadow_blurred.split()[3])

    # 检查透明通道
    if img.mode == "RGBA":
        pure_backdrop.paste(img, (int(x_offset), int(current_y + upshift)), img.split()[3])
    else:
        pure_backdrop.paste(img, (int(x_offset), int(current_y + upshift)))

    return pure_backdrop


async def backdrop_process(params,canves,limit=(0, 0)):
    limit_x, limit_y = limit
    if params['background'] is None or params['background'] == []:return canves
    if not isinstance(params['background'], list):background_list=[params['background']]
    else:background_list=params['background']
    if 'number_count' not in params:number_count=0
    else:number_count=int(params['number_count'])
    if number_count >= len(background_list):number_count=len(background_list)-1
    background_img = (await process_img_download(background_list[number_count], params['is_abs_path_convert']))[0]
    if background_img.width > limit_x and background_img.height > limit_y:
        background_img = background_img.resize(
            (int(limit_x), int(limit_x * background_img.height / background_img.width)))
    if background_img.height < limit_y:
        background_img = background_img.resize(
            (int((limit_y) * background_img.width / background_img.height), int(limit_y)))
    if background_img.width < limit_x:
        background_img = background_img.resize(
            (int(limit_x), int(limit_x * background_img.height / background_img.width)))
    offest_x = (background_img.width - limit_x) // 2
    offest_y = (background_img.height - limit_y) // 2
    # print(offest_x,offest_y)
    background_img = background_img.crop((offest_x, offest_y, limit_x + offest_x, limit_y + offest_y))

    #对图像进行模糊化处理
    if background_img.mode not in ("RGB", "RGBA"):background_img = background_img.convert("RGBA")
    background_img = background_img.filter(ImageFilter.GaussianBlur(radius=5))

    #对图像进行边缘阴影化处理
    width, height = background_img.size
    center_x, center_y = width // 2, height // 2
    shadow_color = (0, 0, 0)
    # 创建空白遮罩图像
    mask = Image.new("L", (width, height), 0)  # 单通道（L模式）
    draw = ImageDraw.Draw(mask)
    max_alpha, intensity = 100, 0.8
    # 创建径向渐变（非线性）
    max_distance = math.sqrt(center_x ** 2 + center_y ** 2)  # 从中心到角落的最大距离
    for y in range(height):
        for x in range(width):
            # 计算像素点到中心的距离
            dx = x - center_x
            dy = y - center_y
            distance = math.sqrt(dx ** 2 + dy ** 2)

            # 根据距离计算透明度，使用非线性公式
            normalized_distance = distance / max_distance  # 距离归一化到 [0, 1]
            alpha = int(max_alpha * (normalized_distance ** intensity))  # 非线性加深
            if alpha > max_alpha:
                alpha = max_alpha
            mask.putpixel((x, y), alpha)

    # 创建阴影图层
    shadow = Image.new("RGBA", background_img.size, shadow_color + (0,))
    shadow.putalpha(mask)

    # 合并原图和阴影
    background_img = Image.alpha_composite(background_img.convert("RGBA"), shadow)

    background_img.paste(canves, (0, 0), mask=canves)
    canves = background_img
    return canves

async def icon_process(params,canves,box_right=(0, 0)):
    x, y = box_right
    if params['right_icon'] is None or params['right_icon'] == []: return canves
    if not isinstance(params['right_icon'], list):icon_list=[params['right_icon']]
    else:icon_list=params['right_icon']
    if 'number_count' not in params:number_count=0
    else:number_count=int(params['number_count'])
    if number_count >= len(icon_list):number_count=len(icon_list)-1
    icon_img = (await process_img_download(icon_list[number_count], params['is_abs_path_convert']))[0].convert("RGBA")
    icon_img = icon_img.resize((int(params['avatar_size'] * icon_img.width / icon_img.height), int(params['avatar_size'] )))
    if params['is_shadow_font']:
        color_image = Image.new("RGBA", icon_img.size, (255,255,255,255))
        color_image.putalpha(icon_img.convert('L'))
        canves.paste(color_image, (int(x - icon_img.width + 1), int(y - icon_img.height + 1)))
    canves.paste(icon_img, (int(x - icon_img.width), int(y - icon_img.height)), mask=icon_img)
    return canves


#头像右侧标签以及背景处理
async def icon_backdrop_check(params):
    if not (params['type_software'] is None and params['background'] is None and params['right_icon'] is None):
        for content_check in params['software_list']:
            if content_check['right_icon'] and params['type_software'] == content_check['type']:
                if params['right_icon'] is None:params['right_icon'] = content_check['right_icon']
                if content_check['background'] and params['background'] is None:params['background'] = content_check['background']
        if params['background']:
            params['font_name_color'], params['font_time_color'] = '(255,255,255)', '(255,255,255)'
            params['is_shadow_font'] = True
    if params['judge_flag'] == 'default':
        if (params['background'] or params['right_icon']) and (len(params['img']) != 1 or params['number_per_row'] != 1):
            params['is_shadow_img'], params['is_rounded_corners_img'], params['is_stroke_img'] = True, True, True
            params['judge_flag'] = 'list'
        elif (params['background'] or params['right_icon']) and len(params['img']) == 1 and params['number_per_row'] == 1:
            params['is_shadow_img'], params['is_rounded_corners_img'], params['is_stroke_img'] = False, False, False
            params['judge_flag'] = 'common'
        else:
            params['is_shadow_img'], params['is_rounded_corners_img'], params['is_stroke_img'] = False, False, False
    elif params['judge_flag'] == 'list':
        params['is_shadow_img'], params['is_rounded_corners_img'], params['is_stroke_img'] = True, True, True
    elif params['judge_flag'] == 'common':
        params['is_shadow_img'], params['is_rounded_corners_img'], params['is_stroke_img'] = False, False, False


#标签绘制
async def label_process(params,img,number_count,new_width):
    font_label = ImageFont.truetype(params['font_label'], params['font_label_size'])
    label_width, label_height, upshift = params['padding'] * 4, params['padding'] + params['font_label_size'], 0
    if number_count >= len(params['label']) or params['label'][number_count] == '':
        return img
    label_content = params['label'][number_count]
    # 计算标签的实际长度
    for per_label_font in label_content:
        label_width += font_label.getbbox(per_label_font)[2] - font_label.getbbox(per_label_font)[0]
    if label_width > new_width: label_width = new_width
    label_canvas = Image.new("RGBA", (int(label_width), int(label_height)), eval(params['label_color']))
    # 调用方法绘制文字并判断是否需要描边和圆角
    # print(label_width,label_height)
    label_canvas = (await basic_img_draw_text(label_canvas, f'[label] {label_content} [/label]', params,
                                       box=(params['padding'] * 1.3, params['padding'] * 0.8),
                                       limit_box=(label_width, label_height), ellipsis=False))['canvas']
    img = await img_process(params, img, label_canvas, int(new_width - label_width), 0, upshift, 'label')
    return img

#以下函数为模块内关系处理函数
async def init(params):#对模块的参数进行初始化
    # 接下来是对图片进行处理，将其全部转化为pillow的img对象，方便后续处理
    if 'img' in params and params['img'] !=[]:
        params['processed_img'] = await process_img_download(params['img'], params['is_abs_path_convert'])
        # 判断图片的排版方式
        if params['number_per_row'] == 'default':
            if len(params['processed_img']) == 1:
                params['number_per_row'] = 1
                params['is_crop'] = False
            elif len(params['processed_img']) in [2, 4]:params['number_per_row'] = 2
            else:params['number_per_row'] = 3
        # 接下来处理是否裁剪部分
        if params['type'] == 'avatar': params['is_crop'] = True
        if 'is_crop' in params and params['is_crop'] == 'default':
            if params['number_per_row'] == 1:params['is_crop'] = False
            else:params['is_crop'] = True
        if params['is_crop'] is True: params['processed_img'] = await crop_to_square(params['processed_img'])

    if 'number_per_row' in params:
        params['new_width'] = (((params['img_width'] - params['padding'] * 2) - (params['number_per_row'] - 1) * params['padding_with']) // params['number_per_row'])
    if 'draw_limited_height' in params:params['draw_limited_height_remain']=params['draw_limited_height']
    else:params['draw_limited_height_remain']=0

    params['per_number_count'], params['number_count'], params['upshift'], params['downshift'], params['current_y'], params['x_offset'], params['max_height'] ,params['avatar_upshift'] = 0, 0, 0, 0, 0, params['padding'], 0 ,0
    params['img_height_limit_module'],params['json_img_left_module'],params['without_draw_and_jump'],params['draw_limited_height_check'],params['json_img_left_module_flag'] = params['img_height_limit'],[], False, None, False
    # 若有描边，则将初始粘贴位置增加一个描边宽度
    if params['is_stroke_front'] and params['is_stroke_img']:
        params['upshift'] += params['stroke_img_width'] / 2
    if params['is_shadow_front'] and params['is_shadow_img']: params['upshift'] += params['shadow_offset_img'] * 3
    if 'is_shadow_avatar' in params and 'shadow_offset_avatar' in params:
        if params['is_shadow_front'] and params['is_shadow_avatar']: params['avatar_upshift'] += params['shadow_offset_avatar'] * 2
    params['pure_backdrop'] = Image.new("RGBA", (params['img_width'], int(params['img_height_limit'] + params['upshift'] + params['padding_up_common']*2)), (0, 0, 0, 0))
    #params['pure_backdrop'] = Image.new("RGBA",(params['img_width'], int(params['img_height_limit'] + params['upshift'] + params['padding_up_common']*2)),(255, 0, 0, 255))


async def per_img_limit_deal(params,img,magnification_img=1,type='img'):  #处理每个模块之间图像的限高关系
    img_height, img_width = int((params['new_width'] / magnification_img) * img.height / img.width),int(params['new_width'] / magnification_img)
    img = img.resize((img_width, img_height))
    if params['number_count'] + 1 <= params['number_per_row'] and 'draw_limited_height' in params:

        img = img.crop((0, params['draw_limited_height'], img_width, img_height))
    if img.height > params['img_height_limit_module']:
        img = img.crop((0, 0, img_width, params['img_height_limit_module']))
        if type != 'avatar': params['draw_limited_height_check']=params['img_height_limit_module']
        params['json_img_left_module_flag'] = True
    return img



async def per_img_deal(params,img, type='img'):#绘制完该模块后处理下一个模块的关系
    if img.height > params['max_height']: params['max_height'] = img.height
    params['x_offset'] += params['new_width'] + params['padding_with']
    params['per_number_count'] += 1
    params['number_count'] += 1
    if params['per_number_count'] == params['number_per_row']:
        params['current_y'] += params['max_height'] + params['padding_with']
        params['img_height_limit_module'] -= (params['padding_with'] + params['max_height'])
        if params['img_height_limit_module'] <= 0 : params['img_height_limit_module'] = 0
        params['per_number_count'], params['x_offset'], params['max_height'] = 0, params['padding'], 0
    #然后对剩余文字进行处理
    if 'content' in params and params['number_count'] - 1 < len(params['content']): #仅在索引小于文字内容长度的时候生效
        if isinstance(params['content'][params['number_count'] - 1], list) and params['content'][params['number_count'] - 1] != []:
            params['params']['content'][params['number_count'] - 1]=params['content'][params['number_count'] - 1]
        elif not params['content'][params['number_count'] - 1]:
            params['params']['content'][params['number_count'] - 1] = []
        else:
            params['params']['content'][params['number_count'] - 1] = [params['content'][params['number_count'] - 1]]


async def final_img_deal(params, type='img'):#判断是否需要增减
    if type == 'text':
        if params['content'][0] != []:
            params['params']['content'] = [params['content'][0]]
            params['json_img_left_module'] = params['params']
            params['json_img_left_module_flag']=True
        return
    if params['per_number_count'] != 0:
        params['current_y'] += params['max_height']
    else:
        params['current_y'] -= params['padding_with']
    #处理限制高度
    if params['current_y'] >= params['img_height_limit']:
        if params['img_height_limit_flag'] :
            params['current_y'] = params['img_height_limit'] - params['padding_up_common']
        elif params['img_height_limit_flag'] is False:
            params['current_y'] = params['img_height_limit']
    #处理能够返回的剩余待处理图片
    for item in ['img','content','label','right_icon','background']:
        if item in params['params']:
            if type == 'avatar':number_check=params["number_count"]
            else:number_check=int(params["number_count"] - params["number_per_row"])
            if number_check < 0: number_check = 0
            params['params'][item] = params['params'][item][number_check:]
    if params['draw_limited_height_check']:
        params['params']['draw_limited_height'] = params['draw_limited_height_check'] + params['draw_limited_height_remain']
    if params['json_img_left_module_flag']: params['json_img_left_module'] = params['params']


    #print(params['img_height_limit'],params['current_y'])