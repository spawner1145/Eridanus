from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
from .download_img import process_img_download
from .text_deal import basic_img_draw_text
from .common import crop_to_square
from .img_deal import _cleanup_temp_images
import math
import gc
import weakref
from collections.abc import Iterable
import pprint

#处理图片大小并缩放
async def per_img_deal_gather(params, img, type='img'):  # 处理每个模块之间图像的限高关系
    #每个图片的比例关系，默认为1
    if 'magnification_img' in params:
        if params['magnification_img'] == 'default':
            if img.height / img.width < 9 / 16:params['magnification_img'] = 2
            else:params['magnification_img'] = 2.5
    else:
        params['magnification_img'] = 1
    img_height = int((params['new_width'] / params['magnification_img']) * img.height / img.width)
    img_width = int(params['new_width'] / params['magnification_img'])
    img = img.resize((img_width, img_height))#这里的不用回收，最后会统一处理
    return img

#处理图片的限高关系
async def per_img_limit_deal_gather(params, img, type='img'):  # 处理每个模块之间图像的限高关系
    img_width, img_height = img.width, img.height
    #对图片大小划定完后进行限高判断以及裁剪
    #此处处理超长图片裁切问题，此处为裁切至上一列绘制完的位置
    if params['number_count'] + 1 <= params['number_per_row'] and 'draw_limited_height' in params:
        cropped_img = img.crop((0, params['draw_limited_height'], img_width, img_height))
        img.close()
        img = cropped_img
    #处理其是否到底
    if img.height > params['img_height_limit_module']:
        final_cropped = img.crop((0, 0, img_width, params['img_height_limit_module']))
        img.close()
        img = final_cropped
        if type not in ['avatar','math']:params['draw_limited_height_check'] = params['img_height_limit_module']
        params['json_img_left_module_flag'] = True
    #单独处理math模块内chart个数问题
    if params['type'] == 'math' and isinstance(params['content'][params['number_count']], (set, list)):#单独处理math模块中chart的长宽
        number_per_row_list=len(params['content'][params['number_count']])
        if params['chart_width'] == 'default':
            params['chart_width'] = (((params['new_width'] - params['padding'] * 2) - (number_per_row_list - 1) * params['padding_with']) // number_per_row_list)
    return img

async def img_rounded_gather(params, img, type='img'):
    # 圆角处理
    if params['is_rounded_corners_front'] and params[f'is_rounded_corners_{type}']:
        mask = Image.new("L", img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((0, 0, img.width, img.height), radius=params[f'rounded_{type}_radius'], fill=255,
                               outline=255,
                               width=2)
        rounded_image = Image.new("RGBA", img.size)
        rounded_image.paste(img, (0, 0), mask=mask)
        # 清理mask，不再需要
        mask.close()
        img = rounded_image
    return img


#图像处理
async def img_process_gather(img_info, type='img'):
    temp_images = []  # 用于跟踪需要清理的临时图像
    params = img_info['params']
    original_img, img, x_offset, current_y, upshift = img_info['img'], img_info['img'], img_info['info']['x_offset'], img_info['info']['current_y'], img_info['info']['upshift']
    pure_backdrop = Image.new("RGBA", (params['img_width'], int(params['img_height_limit'] + params['upshift'] + params['padding_up_common'] * 2)),(0, 0, 0, 0))
    try:
        # 圆角处理
        if params['is_rounded_corners_front'] and params[f'is_rounded_corners_{type}']:
            mask = Image.new("L", img.size, 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle((0, 0, img.width, img.height), radius=params[f'rounded_{type}_radius'], fill=255,
                                   outline=255,
                                   width=2)
            rounded_image = Image.new("RGBA", img.size)
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

async def img_combine_alpha(layers):
    if len(layers) == 1:
        return layers[0]
    # 两两合成
    paired_layers = []
    for i in range(0, len(layers), 2):
        if i+1 < len(layers):
            # 并发调用alpha_composite合成layers[i]和layers[i+1]
            paired_layers.append(Image.alpha_composite(layers[i], layers[i+1]))
        else:
            paired_layers.append(layers[i])
    # 递归合成
    return await img_combine_alpha(paired_layers)


