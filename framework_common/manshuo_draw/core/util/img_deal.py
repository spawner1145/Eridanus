from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
from .download_img import process_img_download
from .text_deal import basic_img_draw_text
from .common import crop_to_square
import math
import gc
import weakref


def _cleanup_temp_images(temp_images):
    """清理临时图像对象"""
    for img_ref in temp_images:
        img = img_ref() if hasattr(img_ref, '__call__') else img_ref
        if img is not None and hasattr(img, 'close'):
            try:
                img.close()
                del img  # 显式删除引用
            except:
                pass
    temp_images.clear()  # 清空列表
    gc.collect()  # 强制垃圾回收


async def img_process(params, pure_backdrop, img, x_offset, current_y, upshift=0, type='img'):
    temp_images = []  # 用于跟踪需要清理的临时图像
    original_img = img

    try:
        # 圆角处理
        if params['is_rounded_corners_front'] and params[f'is_rounded_corners_{type}']:
            mask = Image.new("L", img.size, 0)
            temp_images.append(weakref.ref(mask))
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle((0, 0, img.width, img.height), radius=params[f'rounded_{type}_radius'], fill=255,
                                   outline=255,
                                   width=2)
            rounded_image = Image.new("RGBA", img.size)
            temp_images.append(weakref.ref(rounded_image))
            rounded_image.paste(img, (0, 0), mask=mask)
            # 清理mask，不再需要
            mask.close()
            img = rounded_image

        # 阴影处理
        if params['is_shadow_front'] and params[f'is_shadow_{type}']:
            shadow_image = Image.new("RGBA", pure_backdrop.size, (0, 0, 0, 0))
            temp_images.append(weakref.ref(shadow_image))
            shadow_draw = ImageDraw.Draw(shadow_image)
            # 计算阴影矩形的位置
            shadow_rect = [
                x_offset - params[f'shadow_offset_{type}'],
                current_y - params[f'shadow_offset_{type}'] + upshift,
                x_offset + img.width + params[f'shadow_offset_{type}'],
                current_y + img.height + params[f'shadow_offset_{type}'] + upshift
            ]
            # 绘制阴影（半透明黑色）
            shadow_draw.rounded_rectangle(shadow_rect, radius=params[f'rounded_{type}_radius'],
                                          fill=(0, 0, 0, params[f'shadow_opacity_{type}']))
            # 对阴影层应用模糊效果
            blurred_shadow = shadow_image.filter(ImageFilter.GaussianBlur(params[f'blur_radius_{type}']))
            temp_images.append(weakref.ref(blurred_shadow))
            # 清理原始阴影图像
            shadow_image.close()
            # 将阴影层与底层图像合并
            new_backdrop = Image.alpha_composite(pure_backdrop, blurred_shadow)
            # 清理旧的pure_backdrop（这里需要更严格的判断）
            if pure_backdrop is not original_img and hasattr(pure_backdrop, 'close'):
                try:
                    pure_backdrop.close()
                except:
                    pass
            pure_backdrop = new_backdrop
            # 清理模糊阴影
            blurred_shadow.close()

        # 描边处理
        if params['is_stroke_front'] and params[f'is_stroke_{type}']:
            stroke_img = Image.new('RGBA', (
            img.width + params[f'stroke_{type}_width'], img.height + params[f'stroke_{type}_width']),
                                   eval(str(params[f'stroke_{type}_color'])))
            temp_images.append(weakref.ref(stroke_img))
            shadow_blurred = stroke_img.filter(ImageFilter.GaussianBlur(params[f'stroke_{type}_width'] / 2))
            temp_images.append(weakref.ref(shadow_blurred))
            # 清理原始描边图像
            stroke_img.close()

            mask = Image.new('L', shadow_blurred.size, 255)
            temp_images.append(weakref.ref(mask))
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle([0, 0, shadow_blurred.size[0], shadow_blurred.size[1]],
                                   radius=params[f'stroke_{type}_radius'], fill=0, outline=255, width=2)
            shadow_blurred = ImageOps.fit(shadow_blurred, mask.size, method=0, bleed=0.0, centering=(0.5, 0.5))
            inverted_mask = ImageOps.invert(mask)
            temp_images.append(weakref.ref(inverted_mask))
            # 清理原始mask
            mask.close()

            shadow_blurred.putalpha(inverted_mask)
            pure_backdrop.paste(shadow_blurred,
                                (int(x_offset - params[f'stroke_{type}_width'] / 2),
                                 int(current_y - params[f'stroke_{type}_width'] / 2 + upshift)),
                                shadow_blurred.split()[3])
            # 清理临时图像
            shadow_blurred.close()
            inverted_mask.close()

        # 检查透明通道并粘贴
        if img.mode == "RGBA":
            alpha_channel = img.split()[3]
            pure_backdrop.paste(img, (int(x_offset), int(current_y + upshift)), alpha_channel)
        else:
            pure_backdrop.paste(img, (int(x_offset), int(current_y + upshift)))

        return pure_backdrop

    finally:
        # 清理所有临时图像
        _cleanup_temp_images(temp_images)
        # 如果img不是原始输入且已被修改，清理它
        if img is not original_img and img is not None:
            try:
                img.close()
            except:
                pass


async def backdrop_process(params, canves, limit=(0, 0)):
    limit_x, limit_y = limit
    if params['background'] is None or params['background'] == []:
        return canves

    if not isinstance(params['background'], list):
        background_list = [params['background']]
    else:
        background_list = params['background']

    if 'number_count' not in params:
        number_count = 0
    else:
        number_count = int(params['number_count'])

    if number_count >= len(background_list):
        number_count = len(background_list) - 1

    background_img = (await process_img_download(background_list[number_count], params['is_abs_path_convert']))[0]
    temp_images = [background_img]  # 跟踪需要清理的图像

    try:
        # 调整背景图像尺寸
        # 调整背景图像尺寸
        if background_img.width > limit_x and background_img.height > limit_y:
            new_img = background_img.resize(
                (int(limit_x), int(limit_x * background_img.height / background_img.width)))
            background_img.close()  # 直接关闭，因为已经创建了新的
            background_img = new_img

        if background_img.height < limit_y:
            new_img = background_img.resize(
                (int((limit_y) * background_img.width / background_img.height), int(limit_y)))
            background_img.close()  # 直接关闭
            background_img = new_img

        if background_img.width < limit_x:
            new_img = background_img.resize(
                (int(limit_x), int(limit_x * background_img.height / background_img.width)))
            background_img.close()  # 直接关闭
            background_img = new_img

        # 裁剪图像
        offest_x = (background_img.width - limit_x) // 2
        offest_y = (background_img.height - limit_y) // 2
        cropped_img = background_img.crop((offest_x, offest_y, limit_x + offest_x, limit_y + offest_y))
        background_img.close()  # 直接关闭
        background_img = cropped_img

        if background_img.mode != "RGBA":
            rgba_img = background_img.convert("RGBA")
            background_img.close()  # 直接关闭
            background_img = rgba_img


        # 模糊处理
        if params['is_blurred']:
            blurred_img = background_img.filter(ImageFilter.GaussianBlur(radius=5))
            background_img.close()
            background_img = blurred_img

        # 阴影处理
        if params['is_shadow']:
            width, height = background_img.size
            center_x, center_y = width // 2, height // 2
            shadow_color = (0, 0, 0)

            # 创建遮罩 - 使用更高效的方法
            mask = Image.new("L", (width, height), 0)
            max_alpha, intensity = 100, 0.8
            max_distance = math.sqrt(center_x ** 2 + center_y ** 2)

            # 批量处理像素而不是逐个处理
            pixels = []
            for y in range(height):
                row = []
                for x in range(width):
                    dx = x - center_x
                    dy = y - center_y
                    distance = math.sqrt(dx ** 2 + dy ** 2)
                    normalized_distance = distance / max_distance
                    alpha = min(int(max_alpha * (normalized_distance ** intensity)), max_alpha)
                    row.append(alpha)
                pixels.append(row)

            # 一次性设置所有像素
            mask.putdata([pixel for row in pixels for pixel in row])

            # 创建阴影图层
            shadow = Image.new("RGBA", background_img.size, shadow_color + (0,))
            shadow.putalpha(mask)
            mask.close()  # 立即清理mask

            # 合并原图和阴影
            final_img = Image.alpha_composite(background_img.convert("RGBA"), shadow)
            background_img.close()
            shadow.close()
            background_img = final_img

        # 粘贴canvas
        background_img.paste(canves, (0, 0), mask=canves)
        return background_img

    except Exception as e:
        # 出错时清理所有临时图像
        for img in temp_images:
            if img and hasattr(img, 'close'):
                try:
                    img.close()
                except:
                    pass
        raise e


async def icon_process(params, canves, box_right=(0, 0)):
    x, y = box_right
    if params['right_icon'] is None or params['right_icon'] == []:
        return canves

    if not isinstance(params['right_icon'], list):
        icon_list = [params['right_icon']]
    else:
        icon_list = params['right_icon']

    if 'number_count' not in params:
        number_count = 0
    else:
        number_count = int(params['number_count'])

    if number_count >= len(icon_list):
        number_count = len(icon_list) - 1

    icon_img = (await process_img_download(icon_list[number_count], params['is_abs_path_convert']))[0].convert("RGBA")
    temp_images = [icon_img]

    try:
        # 调整图标大小
        resized_icon = icon_img.resize(
            (int(params['avatar_size'] * icon_img.width / icon_img.height), int(params['avatar_size'])))
        if resized_icon is not icon_img:
            icon_img.close()
        icon_img = resized_icon

        if params['is_shadow_font']:
            color_image = Image.new("RGBA", icon_img.size, (255, 255, 255, 255))
            temp_images.append(color_image)
            gray_alpha = icon_img.convert('L')
            color_image.putalpha(gray_alpha)
            gray_alpha.close()  # 立即清理
            canves.paste(color_image, (int(x - icon_img.width + 1), int(y - icon_img.height + 1)))
            color_image.close()  # 立即清理

        canves.paste(icon_img, (int(x - icon_img.width), int(y - icon_img.height)), mask=icon_img)
        return canves

    finally:
        # 清理图标图像
        if icon_img and hasattr(icon_img, 'close'):
            try:
                icon_img.close()
            except:
                pass


# 头像右侧标签以及背景处理
async def icon_backdrop_check(params):
    if not (params['type_software'] is None and params['background'] is None and params['right_icon'] is None):
        for content_check in params['software_list']:
            if content_check['right_icon'] and params['type_software'] == content_check['type']:
                if params['right_icon'] is None:
                    params['right_icon'] = content_check['right_icon']
                if content_check['background'] and params['background'] is None:
                    params['background'] = content_check['background']
        if params['background']:
            params['font_name_color'], params['font_time_color'] = '(255,255,255)', '(255,255,255)'
            params['is_shadow_font'] = True
    if params['judge_flag'] == 'default':
        if (params['background'] or params['right_icon']) and (
                len(params['img']) != 1 or params['number_per_row'] != 1):
            params['is_shadow_img'], params['is_rounded_corners_img'], params['is_stroke_img'] = True, True, True
            params['judge_flag'] = 'list'
        elif (params['background'] or params['right_icon']) and len(params['img']) == 1 and params[
            'number_per_row'] == 1:
            params['is_shadow_img'], params['is_rounded_corners_img'], params['is_stroke_img'] = False, False, False
            params['judge_flag'] = 'common'
        else:
            params['is_shadow_img'], params['is_rounded_corners_img'], params['is_stroke_img'] = False, False, False
    elif params['judge_flag'] == 'list':
        params['is_shadow_img'], params['is_rounded_corners_img'], params['is_stroke_img'] = True, True, True
    elif params['judge_flag'] == 'common':
        params['is_shadow_img'], params['is_rounded_corners_img'], params['is_stroke_img'] = False, False, False


# 标签绘制
async def label_process(params, img, number_count, new_width):
    if number_count >= len(params['label']) or params['label'][number_count] == '':
        return img

    font_label = ImageFont.truetype(params['font_label'], params['font_label_size'])
    label_width, label_height, upshift = params['padding'] * 4, params['padding'] + params['font_label_size'], 0
    label_content = params['label'][number_count]

    # 计算标签的实际长度
    for per_label_font in label_content:
        bbox = font_label.getbbox(per_label_font)
        label_width += bbox[2] - bbox[0]

    if label_width > new_width:
        label_width = new_width

    label_canvas = Image.new("RGBA", (int(label_width), int(label_height)), eval(params['label_color']))

    try:
        # 调用方法绘制文字并判断是否需要描边和圆角
        text_result = await basic_img_draw_text(label_canvas, f'[label] {label_content} [/label]', params,
                                                box=(params['padding'] * 1.3, params['padding'] * 0.8),
                                                limit_box=(label_width, label_height), ellipsis=False)
        label_canvas = text_result['canvas']

        result_img = await img_process(params, img, label_canvas, int(new_width - label_width), 0, upshift, 'label')
        return result_img

    finally:
        # 清理标签画布
        if label_canvas and hasattr(label_canvas, 'close'):
            try:
                label_canvas.close()
            except:
                pass


# 以下函数为模块内关系处理函数
async def init(params):  # 对模块的参数进行初始化
    # 接下来是对图片进行处理，将其全部转化为pillow的img对象，方便后续处理
    if 'img' in params:
        params['processed_img'] = await process_img_download(params['img'], params['is_abs_path_convert'],
                                                             proxy=params['proxy'])
        # 判断图片的排版方式
        if params['number_per_row'] == 'default':
            if len(params['processed_img']) == 1:
                params['number_per_row'] = 1
                params['is_crop'] = False
            elif len(params['processed_img']) in [2, 4]:
                params['number_per_row'] = 2
            else:
                params['number_per_row'] = 3
        # 接下来处理是否裁剪部分
        if params['type'] == 'avatar':
            params['is_crop'] = True
        if params['type'] == 'games' and 'is_crop' not in params:
            params['is_crop'] = False
        if 'is_crop' in params and params['is_crop'] == 'default':
            if params['number_per_row'] == 1:
                params['is_crop'] = False
            else:
                params['is_crop'] = True
        if params['is_crop'] is True:
            params['processed_img'] = await crop_to_square(params['processed_img'])

    if 'number_per_row' in params:
        params['new_width'] = (((params['img_width'] - params['padding'] * 2) - (params['number_per_row'] - 1) * params[
            'padding_with']) // params['number_per_row'])
    if 'draw_limited_height' in params:
        params['draw_limited_height_remain'] = params['draw_limited_height']
    else:
        params['draw_limited_height_remain'] = 0

    params['per_number_count'], params['number_count'], params['upshift'], params['downshift'], params['current_y'], \
    params['x_offset'], params['max_height'], params['avatar_upshift'] = 0, 0, 0, 0, 0, params['padding'], 0, 0
    params['img_height_limit_module'], params['json_img_left_module'], params['without_draw_and_jump'], params[
        'draw_limited_height_check'], params['json_img_left_module_flag'] = params[
        'img_height_limit'], [], False, None, False
    # 若有描边，则将初始粘贴位置增加一个描边宽度
    if params['is_stroke_front'] and params['is_stroke_img']:
        params['upshift'] += params['stroke_img_width'] / 2
    if params['is_shadow_front'] and params['is_shadow_img']:
        params['upshift'] += params['shadow_offset_img'] * 3
    if 'is_shadow_avatar' in params and 'shadow_offset_avatar' in params:
        if params['is_shadow_front'] and params['is_shadow_avatar']:
            params['avatar_upshift'] += params['shadow_offset_avatar'] * 2
    params['pure_backdrop'] = Image.new("RGBA", (
    params['img_width'], int(params['img_height_limit'] + params['upshift'] + params['padding_up_common'] * 2)),
                                        (0, 0, 0, 0))


async def per_img_limit_deal(params, img, type='img'):  # 处理每个模块之间图像的限高关系
    original_img = img
    try:
        if 'magnification_img' in params:
            if params['magnification_img'] == 'default':
                if img.height / img.width < 9 / 16:
                    params['magnification_img'] = 2
                else:
                    params['magnification_img'] = 2.5
        else:
            params['magnification_img'] = 1

        img_height = int((params['new_width'] / params['magnification_img']) * img.height / img.width)
        img_width = int(params['new_width'] / params['magnification_img'])

        resized_img = img.resize((img_width, img_height))
        if resized_img is not img and img is not original_img:
            img.close()
        img = resized_img

        if params['number_count'] + 1 <= params['number_per_row'] and 'draw_limited_height' in params:
            cropped_img = img.crop((0, params['draw_limited_height'], img_width, img_height))
            if cropped_img is not img:
                img.close()
            img = cropped_img

        if img.height > params['img_height_limit_module']:
            final_cropped = img.crop((0, 0, img_width, params['img_height_limit_module']))
            if final_cropped is not img:
                img.close()
            img = final_cropped
            if type != 'avatar':
                params['draw_limited_height_check'] = params['img_height_limit_module']
            params['json_img_left_module_flag'] = True

        return img

    except Exception as e:
        # 出错时清理可能创建的图像
        if img is not original_img and img and hasattr(img, 'close'):
            try:
                img.close()
            except:
                pass
        raise e


async def per_img_deal(params, img, type='img'):  # 绘制完该模块后处理下一个模块的关系
    if img.height > params['max_height']:
        params['max_height'] = img.height
    params['x_offset'] += params['new_width'] + params['padding_with']
    params['per_number_count'] += 1
    params['number_count'] += 1
    if params['per_number_count'] == params['number_per_row']:
        params['current_y'] += params['max_height'] + params['padding_with']
        params['img_height_limit_module'] -= (params['padding_with'] + params['max_height'])
        if params['img_height_limit_module'] <= 0:
            params['img_height_limit_module'] = 0
        params['per_number_count'], params['x_offset'], params['max_height'] = 0, params['padding'], 0
    # 然后对剩余文字进行处理
    if 'content' in params and params['number_count'] - 1 < len(params['content']):  # 仅在索引小于文字内容长度的时候生效
        if isinstance(params['content'][params['number_count'] - 1], list) and params['content'][
            params['number_count'] - 1] != []:
            params['params']['content'][params['number_count'] - 1] = params['content'][params['number_count'] - 1]
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
            else:number_check=int(params["number_count"])
            if number_check < 0: number_check = 0
            params['params'][item] = params['params'][item][number_check:]
    if params['draw_limited_height_check']:
        params['params']['draw_limited_height'] = params['draw_limited_height_check'] + params['draw_limited_height_remain']
    if params['json_img_left_module_flag']:
        params['json_img_left_module'] = params['params']


    #print(params['img_height_limit'],params['current_y'])