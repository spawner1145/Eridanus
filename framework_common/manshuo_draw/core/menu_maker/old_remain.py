import os
import shutil
from ruamel.yaml import YAML
import pprint

# 使用 ruamel.yaml 来读取和写入文件
yaml = YAML()
yaml.preserve_quotes = True  # 保留引号和格式
yaml.indent(sequence=4, offset=2)  # 设置缩进
yaml.width = 4096  # 设置行宽防止换行

#一个简易的版本号比对工具
def compare_versions(v1: str, v2: str) -> int:
    parts1 = list(map(int, v1.split('.')))
    parts2 = list(map(int, v2.split('.')))
    # 补齐较短版本号长度，补0
    max_len = max(len(parts1), len(parts2))
    parts1.extend([0] * (max_len - len(parts1)))
    parts2.extend([0] * (max_len - len(parts2)))
    for num1, num2 in zip(parts1, parts2):
        if num1 > num2: return 1     # v1 > v2
        elif num1 < num2: return -1    # v1 < v2
    return 0  # v1 == v2


#转换旧版本菜单至新版本
async def copy_yaml():
    return_json = {'status':False,'menu':{}}
    current_version = '1.0.0'
    old_path = r'run/common_config/menu.yaml'#源文件
    new_path = r'framework_common/manshuo_draw/data/cache/menu.yaml'#目标地址
    if not os.path.exists(old_path): return return_json
    return_json['status'] = True
    with open(old_path, 'r', encoding='utf-8') as old_menu_ob:
        old_menu = yaml.load(old_menu_ob)
    #pprint.pprint(old_menu['help_menu']['content'])
    if 'help_menu' in old_menu and '菜单版本号' in old_menu['help_menu'] and compare_versions(old_menu['help_menu']['菜单版本号'],current_version) in [0,1]:
        return_json['menu'] = old_menu['help_menu']['content']
        return return_json
    if 'is_convert' not in old_menu['help_menu']:
        old_menu['help_menu']['is_convert'] = True
    if old_menu['help_menu']['is_convert'] is False:
        return_json['menu'] = old_menu['help_menu']['content']
        return return_json
    #执行新菜单生成合并
    #先将旧菜单移动至新位置保存
    shutil.copy2(old_path, new_path)
    os.remove(old_path)
    menu_context = old_menu['help_menu']['content']
    new_menu_context = {}
    #pprint.pprint(menu_context)
    for page in menu_context:
        new_menu_context[page], num = {}, 1
        for item in menu_context[page]:
            if 'type' not in item:
                new_menu_context[page][f'序号{num}'] = {'类型': '文字','内容文本': item}
            elif item['type'] == 'basic_set':
                continue
            elif item['type'] in 'avatar':
                new_menu_context[page][f'序号{num}'] = {'类型':'头像','图片链接':item['img'],'内容文本':item['content']}
            elif item['type'] == 'text':
                new_menu_context[page][f'序号{num}'] = {'类型':'文字','内容文本':item['content']}
            elif item['type'] == 'img':
                if 'subtype' not in item or item['subtype'] == 'common':
                    new_menu_context[page][f'序号{num}'] = {'类型':'图片','图片链接':item['img']}
                elif item['subtype'] == 'common_with_des_right':
                    new_menu_context[page][f'序号{num}'] = {'类型': '图片右侧带文字','图片链接': item['img'],'内容文本': item['content']}
                elif item['subtype'] == 'common_with_des':
                    new_menu_context[page][f'序号{num}'] = {'类型': '图片带文字','图片链接': item['img'],'内容文本': item['content']}
            num += 1
    old_menu['help_menu']['content'] = new_menu_context
    #做一点键值对检查
    #检查内部版本号
    old_menu['help_menu']['菜单版本号'] = current_version
    old_menu['help_menu']['is_convert'] = False
    return_json['menu'] = new_menu_context
    #pprint.pprint(new_menu_context)
    #将转换好的菜单保存
    with open(old_path, 'w', encoding='utf-8') as file:
        yaml.dump(old_menu, file)
    return return_json