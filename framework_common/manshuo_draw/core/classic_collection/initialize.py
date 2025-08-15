import os
from .util import *
global initialize_yaml_set
version_check=True
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

def version_check_core():
    global version_check
    version_check=False
    default_config = get_abs_path('framework_common/manshuo_draw/data/config/save_config.yml')


if version_check:
    try:version_check_core()
    except Exception as e:print(e)

def initialize_yaml_must_require(params):#对里面的数据进行处理
    initialize_yaml_load, must_required_keys=initialize_yaml_must_require_core(params)
    for key in initialize_yaml_load:
        if initialize_yaml_load[key] == 'None': initialize_yaml_load[key]=None
    return initialize_yaml_load, must_required_keys

#检测默认配置文件与用户文件的差异，实现自动更新配置文件
def check_merge_config(default_config_path, user_config_path):
    # 使用 ruamel.yaml 来读取和写入文件
    yaml = YAML()
    yaml.preserve_quotes = True  # 保留引号和格式
    yaml.indent(sequence=4, offset=2)  # 设置缩进
    yaml.width = 4096  # 设置行宽防止换行

    # 读取默认配置文件
    with open(default_config_path, 'r', encoding='utf-8') as default_file:
        default_config = yaml.load(default_file)

    # 读取用户配置文件（保留注释和格式）
    with open(user_config_path, 'r', encoding='utf-8') as user_file:
        user_config = yaml.load(user_file)

    # 定义递归合并函数
    def merge_dicts(default_dict, user_dict):
        for key, value in default_dict.items():
            if key not in user_dict and not isinstance(value, dict):  # 用户配置中缺少键
                user_dict[key] = value
                if isinstance(default_dict, CommentedMap):
                    comment = default_dict.ca.items.get(key)
                    if comment:
                        user_dict.ca.items[key] = comment
            elif key not in user_dict and isinstance(value, dict):
                user_dict[key] = {}
                merge_dicts(value, user_dict[key])
            elif isinstance(value, dict) and isinstance(user_dict[key], dict):  # 如果键对应的值是嵌套字典，递归合并
                merge_dicts(value, user_dict[key])
        return user_dict

    # 合并配置文件
    merge_dicts(default_config, user_config)

    # 将更新后的配置写回用户文件，同时保留注释和排版
    with open(user_config_path, 'w', encoding='utf-8') as user_file:
        yaml.dump(user_config, user_file)

def initialize_yaml_must_require_core(params):
    global initialize_yaml_set,version_check
    yaml = YAML()
    yaml.preserve_quotes = True  # 保留 YAML 中的引号
    yaml.indent(sequence=4, offset=2)  # 设置缩进
    yaml.width = 4096  # 设置行宽防止换行
    default_config = get_abs_path('framework_common/manshuo_draw/data/config/save_config.yml')
    if 'basic_set' == params['type'] :
        if 'config_path' not in params:
            params['config_path']=get_abs_path(default_config)
        config_abs_path = get_abs_path(params['config_path'])
        if not os.path.exists(config_abs_path):
            with open(default_config, 'r', encoding='utf-8') as file:
                origin_config_set_yaml = yaml.load(file)
            with open(config_abs_path, 'w', encoding='utf-8') as file:
                yaml.dump(origin_config_set_yaml, file)
            initialize_yaml_set=origin_config_set_yaml
        else:
            try:
                #判断配置文件与默认配置文件的不同，若键值不同则直接增添后复写
                check_merge_config(default_config, params['config_path'])
                with open(config_abs_path, 'r', encoding='utf-8') as file:
                    initialize_yaml_set = yaml.load(file)
            except Exception as e:
                with open(default_config, 'r', encoding='utf-8') as file:
                    origin_config_set_yaml = yaml.load(file)
                with open(config_abs_path, 'w', encoding='utf-8') as file:
                    yaml.dump(origin_config_set_yaml, file)
                initialize_yaml_set = origin_config_set_yaml



    if params['type'] not in initialize_yaml_set:
        return [], {}
    if params['type'] in initialize_yaml_set :
        if 'subtype' in params and params['subtype'] not in initialize_yaml_set[params['type']]:
            return initialize_yaml_set[f"{params['type']}"], {}

    must_required_keys = []
    if 'subtype' not in params:
        initialize_yaml_load=initialize_yaml_set[f"{params['type']}"]
    else:
        initialize_yaml_load_check=initialize_yaml_set[f"{params['type']}"]
        initialize_yaml_load_check_reload,initialize_yaml_load_reload={},{}
        for per_yaml in initialize_yaml_load_check:
            if 'must_required_keys' == per_yaml:must_required_keys = initialize_yaml_load_check['must_required_keys']
            if isinstance(initialize_yaml_load_check[per_yaml], dict): continue
            initialize_yaml_load_check_reload[per_yaml]=initialize_yaml_load_check[per_yaml]


        initialize_yaml_load=initialize_yaml_set[f"{params['type']}"][f"{params['subtype']}"]
        for per_yaml in initialize_yaml_load_check_reload:
            initialize_yaml_load_reload[per_yaml]=initialize_yaml_load_check_reload[per_yaml]
        for per_yaml in initialize_yaml_load:
            initialize_yaml_load_reload[per_yaml]=initialize_yaml_load[per_yaml]
        initialize_yaml_load=initialize_yaml_load_reload



    if initialize_yaml_load is None:
        return [], must_required_keys

    if 'must_required_keys' in initialize_yaml_load:#寻找本模块必要的按键，若没有，则为空
        must_required_keys=initialize_yaml_load['must_required_keys']
        initialize_yaml_load.pop('must_required_keys')

    return initialize_yaml_load,must_required_keys

if __name__ == '__main__':
    initialize_yaml_must_require({'type': 'img', 'subtype': 'common'})