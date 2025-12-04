import os
import shutil
from ruamel.yaml import YAML
import pprint

# 使用 ruamel.yaml 来读取和写入文件
yaml = YAML()
yaml.preserve_quotes = True  # 保留引号和格式
yaml.indent(sequence=4, offset=2)  # 设置缩进
yaml.width = 4096  # 设置行宽防止换行

async def menu_convert_draw(menu_content):
    #pprint.pprint(menu_content)
    draw_json = {}
    for page in menu_content:
        draw_json[page] = [
        { 'type': 'basic_set', 'img_width': 1000,'img_name_save': f'help_menu_{page}.png','img_height': 1500,'max_num_of_columns': 5 ,
          'font_common_size': 34,'font_des_size': 25, 'font_tag_size': 34, 'font_title_size': 46,'spacing': 3,'padding_up': 30 }
        ]
        for item in menu_content[page]:
            check_item = menu_content[page][item]
            is_jump_next = check_item.get('是否跳转至下一页', False)
            layer = check_item.get('层级', 2)
            number_per_row = check_item.get('每行个数', 'default')
            if check_item['类型'] == '头像':
                draw_json[page].append({'type': 'avatar', 'img': check_item['图片链接'],'content': check_item['内容文本'], 'padding_up_font': 5,'upshift_extra': 5, 'jump_next_page':is_jump_next, 'layer': layer})
            elif check_item['类型'] == '文字':
                if isinstance(check_item['内容文本'], str):
                    if check_item['内容文本'].strip() == '': layer = 1
                    draw_json[page].append({'type': 'text', 'content': [check_item['内容文本']], 'layer': layer, 'jump_next_page':is_jump_next})
                else:
                    draw_json[page].append({'type': 'text', 'content': check_item['内容文本'], 'layer': layer, 'jump_next_page':is_jump_next})
            elif check_item['类型'] == '图片':
                draw_json[page].append({ 'type': 'img','layer': layer, 'img': check_item['图片链接'], 'jump_next_page':is_jump_next, 'number_per_row':number_per_row})
            elif check_item['类型'] == '图片带文字':
                draw_json[page].append({ 'type': 'img', 'subtype': 'common_with_des','layer': layer, 'img':check_item['图片链接'] ,'content': check_item['内容文本'],
                                         'jump_next_page':is_jump_next, 'number_per_row':number_per_row})
            elif check_item['类型'] == '图片右侧带文字':
                draw_json[page].append({ 'type': 'img', 'subtype': 'common_with_des_right','layer': layer, 'img':check_item['图片链接'] ,'content': check_item['内容文本'],
                                         'jump_next_page':is_jump_next, 'number_per_row':number_per_row})
    #pprint.pprint(draw_json)
    return draw_json