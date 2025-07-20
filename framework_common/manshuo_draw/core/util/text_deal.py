import re
from PIL import Image, ImageDraw, ImageFilter, ImageOps,ImageFont
import platform
from .download_img import process_img_download
from .common import add_append_img
import copy

async def deal_text_with_tag(input_string):
    pattern = r'\[(\w+)\](.*?)\[/\1\]'
    input_string=input_string.replace("\\n", "\n")
    matches = list(re.finditer(pattern, str(input_string), flags=re.DOTALL))
    result = []
    last_end = 0  # 记录上一个匹配结束的位置
    for match in matches:
        start, end = match.span()
        # 处理非标签内容（在上一个匹配结束到当前匹配开始之间的部分）
        if last_end < start:
            non_tag_content = input_string[last_end:start]
            if non_tag_content:
                result.append({'content': non_tag_content,'tag': 'common'})

        # 处理标签内容,若标签内还有标签，则继续递归处理
        tag = match.group(1)  # 标签名
        content = match.group(2)
        content_tag=list(re.finditer(pattern, content, flags=re.DOTALL))
        if content_tag:
            result=add_append_img(result,deal_text_with_tag(content),'last_tag',tag,'common')
        else:
            result.append({'content': content, 'tag': tag})

        last_end = end

    # 处理最后的非标签内容（在最后一个标签结束到字符串末尾之间的部分）
    if last_end < len(input_string):
        non_tag_content = input_string[last_end:]
        if non_tag_content:
            result.append({'content': non_tag_content,'tag': 'common'})


    return result


async def can_render_character(font, character,params):
    """
    检测文字是否可以正常绘制
    此处受限于pillow自身的绘制缺陷
    在无法绘制后让另一个模块进行处理
    """
    if not (params['is_rounded_corners_front'] or params['is_stroke_front'] or params['is_shadow_front']):
        return True
    if character==' ' or character=='':return True
    try:
        # 获取字符的掩码
        mask = font.getmask(character)
        # 如果掩码的宽度或高度为 0，说明字符无法绘制
        if mask.size[0] == 0 or mask.size[1] == 0:
            return False

        # 创建一个测试图像
        dummy_image = Image.new("RGB", (100, 100), "white")
        draw = ImageDraw.Draw(dummy_image)

        # 绘制目标字符
        draw.text((10, 10), character, font=font, fill="black")

        # 创建一个替代字符测试图像
        replacement_image = Image.new("RGB", (100, 100), "white")
        replacement_draw = ImageDraw.Draw(replacement_image)
        replacement_draw.text((10, 10), '\uFFFD', font=font, fill="black")

        # 比较两幅图像的像素数据
        return not (list(dummy_image.getdata()) == list(replacement_image.getdata()))

    except Exception as e:
        # 如果抛出异常，说明字体不支持该字符
        return False

async def color_emoji_maker(text,color,size=40):
    try:
        #此绘图方式win暂不可用，仅限于mac与linux使用
        import gi
        gi.require_version("Pango", "1.0")
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import Pango, PangoCairo
        import cairo
        width, height = 50, 50
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        context = cairo.Context(surface)
        context.set_source_rgba(0, 0, 0, 0)
        context.paint()
        layout = PangoCairo.create_layout(context)
        font_description = Pango.FontDescription("Sans 30")  # 使用系统默认 Sans 字体
        layout.set_font_description(font_description)
        layout.set_text(text, -1)
        context.set_source_rgb(0, 0, 0)  # 黑色文本
        context.move_to(0, 0)
        PangoCairo.show_layout(context, layout)
        buf = surface.get_data()
        # 创建 Pillow 图像对象
        image = Image.frombuffer(
            "RGBA",  # Pillow 使用 "RGBA" 模式
            (surface.get_width(), surface.get_height()),
            buf,  # 数据缓冲区
            "raw",  # 原始数据格式
            "BGRA",  # cairo 使用的是 BGRA 排列，需要转换
            0, 1  # 像素顺序和步长
        )
        return image
    except Exception as e:
        system = platform.system()
        image_size, x_offest = 40, 0
        if system == "Darwin":  # macOS 系统标识
            font_path = "/System/Library/Fonts/Apple Color Emoji.ttc"
        elif system == "Windows":
            font_path = r"C:\Windows\Fonts\seguiemj.ttf"
            x_offest=8
        elif system == "Linux":
            font_path = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
        else:
            raise OSError("暂不支持")
        # 图像大小（宽高相等）
        image = Image.new('RGBA', (image_size, image_size), (255, 255, 255, 0))  # 背景透明
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(font_path, size)
        draw.text((0-x_offest, 0), text, font=font, fill=color)
    #image.show()
    return image



async def basic_img_draw_text(canvas,content,params,box=None,limit_box=None,is_shadow=False,ellipsis=True):
    """
    #此方法不同于其余绘制方法
    #其余绘制方法仅返回自身绘制画面
    #此方法返回在原画布上绘制好的画面，同时返回的底部长度携带一个标准间距，此举意在简化模组中的叠加操作，请注意甄别
    """

    if box is None: box = (params['padding'], 0)  # 初始位置
    x, y = box
    if limit_box is None:
        x_limit, y_limit = (params['img_width'] - params['padding'] * 2, params['img_height'])  # 初始位置
    else:
        x_limit, y_limit = limit_box
    if content == '' or content is None:
        return {'canvas': canvas, 'canvas_bottom': y}
    if isinstance(content, list):content_list=content
    else:content_list = await deal_text_with_tag(content)

    #将所有的emoji转换成pillow对象
    content_list_convert,emoji_list=[],[]
    for item in content_list:
        if item['tag'] == 'emoji':
            if not isinstance(item['content'], dict):emoji_list=[item['content']]
            else:emoji_list=item['content']
            for pillow_emoji in process_img_download(emoji_list, params['is_abs_path_convert']):
                if 'last_tag' not in item: item['last_tag']='common'
                content_list_convert.append({'content': [pillow_emoji.convert("RGBA")], 'tag': 'emoji','last_tag': item['last_tag']})
        else:content_list_convert.append(item)
    content_list=content_list_convert

    # 这一部分检测每行的最大高度
    last_tag,line_height_list,per_max_height = 'common',[],0
    font = ImageFont.truetype(params[f'font_{last_tag}'], params[f'font_{last_tag}_size'])
    for content in content_list:
        emoji_list=[]
        if content['tag'] == 'emoji':
            for item in content['content']:
                emoji_x,emoji_y=int(params[f'font_{content["last_tag"]}_size']*item.width/item.height),int(params[f'font_{content["last_tag"]}_size'])
                emoji_list.append(item.resize((emoji_x,emoji_y)))
            content['content']=emoji_list

        elif last_tag != content['tag']:
            last_tag = content['tag']
            font = ImageFont.truetype(params[f'font_{last_tag}'], params[f'font_{last_tag}_size'])

        i = 0
        # 对文字进行逐个绘制
        text = content['content']
        while i < len(text):  # 遍历每一个字符
            if text[i] == '': continue
            if content['tag'] == 'emoji':
                char_width=emoji_x
                if emoji_y > per_max_height: per_max_height = emoji_y
            else:
                char_width = font.getbbox(text[i])[2] - font.getbbox(text[i])[0]
                if params[f'font_{last_tag}_size'] > per_max_height: per_max_height = params[f'font_{last_tag}_size']

            x += char_width + 1
            i += 1
            if (x + char_width > x_limit and i < len(text)) or text[i - 1] == '\n':
                if x != box[0] + char_width + 1 :
                    x = box[0]
                    line_height_list.append(per_max_height)
                    per_max_height=0
                if x == box[0] + char_width + 1 and text[i - 1] == '\n' :#检测是否在一行最开始换行，若是则修正
                    x -= char_width + 1

    line_height_list.append(params[f'font_{last_tag}_size'])
    line_height_list.append(params[f'font_common_size'])


    #这一部分开始进行实际绘制
    left_content_list = copy.deepcopy(content_list)
    if box is None: box = (params['padding'], 0)  # 初始位置
    x, y = box
    should_break, last_tag, line_count,text,content_left = False, 'common',0 , None, []
    font = ImageFont.truetype(params[f'font_{last_tag}'], params[f'font_{last_tag}_size'])
    #对初始位置进行修正
    if ellipsis: y += line_height_list[0] - params[f'font_common_size']
    for content in content_list:
        left_content_list.pop(left_content_list.index(content))
        # 依据字符串处理的字典加载对应的字体
        if content['tag'] == 'emoji':
            pass
        elif last_tag != content['tag']:
            last_tag = content['tag']
            font = ImageFont.truetype(params[f'font_{last_tag}'], params[f'font_{last_tag}_size'])
        # 在循环之前进行判断返回，避免过多处理字段
        if y > y_limit - (font.getbbox('的')[3] - font.getbbox('的')[1]) and ellipsis:
            return {'canvas': canvas, 'canvas_bottom': y}
        if should_break:  # 检查标志并跳出外层循环
            break

        draw = ImageDraw.Draw(canvas)
        i = 0
        # 对文字进行逐个绘制
        text, content_left = content['content'], content
        while i < len(text):  # 遍历每一个字符
            if text[i] == '': continue
            if content['tag'] == 'emoji':
                emoji_x, emoji_y = int(params[f'font_{content["last_tag"]}_size'] * text[i] .width / text[i] .height), int(params[f'font_{content["last_tag"]}_size'])
                upshift_font,char_width = emoji_y - params[f'font_common_size'],emoji_x
            else:
                char_width = font.getbbox(text[i])[2] - font.getbbox(text[i])[0]
                upshift_font = params[f'font_{last_tag}_size'] - params[f'font_common_size']


            #绘制文字与图片
            if content['tag'] == 'emoji':
                canvas.paste(text[i], (int(x), int(y - upshift_font + 3)), mask=text[i])
            elif await can_render_character(font, text[i],params):
                if is_shadow: draw.text((x + 2, y - upshift_font + 2), text[i], font=font, fill=(148, 148,148))
                draw.text((x, y - upshift_font), text[i], font=font, fill=eval(params[f'font_{last_tag}_color']))
            else:
                try:
                    emoji_img = await color_emoji_maker(text[i], eval(params[f'font_{last_tag}_color']))
                    emoji_img = emoji_img.resize((char_width, int(char_width * emoji_img.height / emoji_img.width)))
                    canvas.paste(emoji_img, (int(x), int(y + 3 - upshift_font)), mask=emoji_img)
                except Exception as e:
                    i += 1
                    continue

            x += char_width + 1
            i += 1
            if (x + char_width * 2 > x_limit and i < len(text) and ellipsis) or text[i - 1] == '\n':
                if y > y_limit - (params[f'font_common_size'])  - params['padding_up'] - line_height_list[line_count + 1]:
                    draw.text((x, y), '...', font=font, fill=eval(params[f'font_{last_tag}_color']))
                    should_break = True
                    break
            if (x + char_width > x_limit and i - 1 < len(text)) or text[i - 1] == '\n':
                if x != box[0] + char_width + 1 :
                    line_count += 1
                    y += params[f'font_common_size'] + params['padding_up'] + line_height_list[line_count] - params[f'font_common_size']
                    x = box[0]
                if x == box[0] + char_width + 1 and text[i - 1] == '\n' :#检测是否在一行最开始换行，若是则修正
                    x -= char_width + 1
    canvas_bottom = y + params[f'font_common_size'] + 2
    if text and params["number_count"] < len(params['content']):
        content_left['content']=text[i:]
        if content_left['content'] == '':
            params['content'][params["number_count"]]=left_content_list
        else:
            params['content'][params["number_count"]]=add_append_img([content_left],left_content_list)
    return {'canvas': canvas, 'canvas_bottom': canvas_bottom,}


if __name__ == '__main__':
    # 输入字符串
    input_string = "这里是manshuo[title]！这部分是测manshuo！[/title]这manshuo！[des]这里是介绍[/des]这里是manshuo[title]！这部分是测manshuo！[/title]"

    # 调用函数
    output = deal_text_with_tag(input_string)
    for item in output:
        print(item)
    # 输出结果
    print(output)