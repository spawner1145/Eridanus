from pathlib import Path
from developTools.message.message_components import Text, Image, At
import pprint

current_file = Path(__file__)
# 获取当前脚本文件所在的目录
plugin_dir = current_file.parent.parent
cache_dir = plugin_dir / 'cache'
data_dir = plugin_dir / 'data'


if __name__ == '__main__':
    pass
    print(plugin_dir)