import os
from ruamel.yaml import YAML
from typing import Any
from concurrent.futures import ThreadPoolExecutor
import threading

from framework_common.utils.install_and_import import install_and_import

watchdog=install_and_import("watchdog")
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from framework_common.utils.system_logger import get_logger

logger=get_logger("YAMLManager")
class YAMLFileHandler(FileSystemEventHandler):
    def __init__(self, yaml_manager):
        self.yaml_manager = yaml_manager
        super().__init__()

    def on_modified(self, event):
        if event.is_directory:
            return

        file_path = event.src_path
        if file_path.endswith(('.yaml', '.yml')):
            self.yaml_manager.reload_file(file_path)


class PluginConfig:
    def __init__(self, name, data, file_paths, save_func):
        self._data = data
        self._file_paths = file_paths
        self._name = name
        self._save_func = save_func

    def __getattr__(self, config_name):
        if config_name in ["_data", "_file_paths", "_save_func", "_name"]:
            return self.__getattribute__(config_name)
        if config_name in self._data:
            return self._data[config_name]
        raise AttributeError(f"Plugin {self._name} has no config '{config_name}'.")

    def __setattr__(self, config_name, value):
        if config_name in ["_data", "_file_paths", "_save_func", "_name"]:
            super().__setattr__(config_name, value)
        elif config_name in self._data:
            self._data[config_name] = value
            self._save_func(config_name, self._name)
        else:
            raise AttributeError(f"Plugin {self._name} has no config '{config_name}'.")


class YAMLManager:
    _instance = None
    _lock = threading.Lock()

    def __init__(self, plugins_dir=None):
        """
        初始化 YAML 管理器，自动并行加载 run 目录下及各插件文件夹中的 YAML 文件。
        """
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.allow_duplicate_keys = True

        self.data = {}
        self.file_paths = {}
        self.path_to_key = {}  # 文件路径到配置键的映射

        # 设置监控目录
        self.run_dir = os.path.join(os.getcwd(), plugins_dir or "run")
        if not os.path.exists(self.run_dir):
            raise FileNotFoundError(f"Run directory {self.run_dir} not found.")

        # 初始加载所有文件
        self._load_all_files()

        # 启动文件监控
        self._start_file_watcher()

        YAMLManager._instance = self

    def _load_all_files(self):
        """加载所有YAML文件"""
        yaml_files = []

        # 收集所有YAML文件
        for item in os.listdir(self.run_dir):
            item_path = os.path.join(self.run_dir, item)

            if os.path.isdir(item_path):
                # 插件文件夹
                for file_name in os.listdir(item_path):
                    if file_name.endswith((".yaml", ".yml")):
                        file_path = os.path.join(item_path, file_name)
                        config_name = os.path.splitext(file_name)[0]
                        yaml_files.append((item, config_name, file_path))
            elif item.endswith((".yaml", ".yml")):
                # 根目录下的YAML文件
                file_path = item_path
                config_name = os.path.splitext(item)[0]
                yaml_files.append((None, config_name, file_path))

        # 并行加载
        def load_yaml_file(args):
            plugin_name, config_name, file_path = args
            yaml_instance = YAML()
            yaml_instance.preserve_quotes = True
            yaml_instance.allow_duplicate_keys = True

            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    return plugin_name, config_name, file_path, yaml_instance.load(file)
            except Exception as e:
                logger.info(f"Error loading {file_path}: {e}")
                return plugin_name, config_name, file_path, {}

        with ThreadPoolExecutor() as executor:
            for plugin_name, config_name, file_path, data in executor.map(load_yaml_file, yaml_files):
                self._store_config(plugin_name, config_name, file_path, data)

    def _store_config(self, plugin_name, config_name, file_path, data):
        """存储配置数据"""
        if plugin_name is None:
            # 根目录文件
            self.data[config_name] = data
            self.file_paths[config_name] = file_path
            self.path_to_key[file_path] = (None, config_name)
        else:
            # 插件文件夹中的文件
            if plugin_name not in self.data:
                self.data[plugin_name] = {}
                self.file_paths[plugin_name] = {}

            self.data[plugin_name][config_name] = data
            self.file_paths[plugin_name][config_name] = file_path
            self.path_to_key[file_path] = (plugin_name, config_name)

    def _start_file_watcher(self):
        """启动文件监控"""
        self.event_handler = YAMLFileHandler(self)
        self.observer = Observer()
        self.observer.schedule(self.event_handler, self.run_dir, recursive=True)
        self.observer.start()



    def _update_with_merge(self, old_data, new_data):
        """
        使用你的合并逻辑更新现有对象，保持引用和注释

        :param old_data: 原始数据对象（要保持引用）
        :param new_data: 新加载的数据
        """
        from ruamel.yaml.comments import CommentedMap, CommentedSeq

        if not isinstance(old_data, (dict, CommentedMap)) or not isinstance(new_data, (dict, CommentedMap)):
            return new_data

        # 使用你的合并逻辑


        # 现在new_data包含了合并后的结果，我们需要将其同步到old_data
        # 清空old_data但保持对象引用
        old_data.clear()

        # 将合并结果复制回old_data
        for key, value in new_data.items():
            old_data[key] = value

        # 保留注释信息
        if isinstance(new_data, CommentedMap) and hasattr(new_data, 'ca'):
            if not hasattr(old_data, 'ca'):
                # 创建与new_data相同类型的ca对象
                old_data.ca = type(new_data.ca)()

            for attr_name in dir(new_data.ca):
                if not attr_name.startswith('_'):
                    try:
                        attr_value = getattr(new_data.ca, attr_name)
                        if not callable(attr_value):
                            setattr(old_data.ca, attr_name, attr_value)
                    except:
                        pass

    def reload_file(self, file_path):
        """重新加载单个文件，使用你的合并逻辑保留配置和注释"""
        if file_path not in self.path_to_key:
            return

        plugin_name, config_name = self.path_to_key[file_path]

        try:
            # 创建新的YAML实例以保持注释
            yaml_loader = YAML()
            yaml_loader.preserve_quotes = True
            yaml_loader.indent(mapping=2, sequence=4, offset=2)  # 使用你的缩进设置
            yaml_loader.allow_duplicate_keys = True
            yaml_loader.width = 4096

            with open(file_path, 'r', encoding='utf-8') as file:
                new_data = yaml_loader.load(file)

            if plugin_name is None:
                # 根目录文件
                old_data = self.data[config_name]
                if isinstance(old_data, dict) and isinstance(new_data, dict):
                    self._update_with_merge(old_data, new_data)
                else:
                    self.data[config_name] = new_data
            else:
                # 插件配置
                old_data = self.data[plugin_name][config_name]
                if isinstance(old_data, dict) and isinstance(new_data, dict):
                    self._update_with_merge(old_data, new_data)
                else:
                    self.data[plugin_name][config_name] = new_data

            logger.info(f"文件重新加载完成: {file_path}")

        except Exception as e:
            logger.error(f"重新加载文件时出错 {file_path}: {e}")
            import traceback
            traceback.print_exc()

    def conflict_file_dealter(self, file_old, file_new):
        """
        你的原始冲突文件处理方法，作为独立工具保留
        """
        # 加载旧的YAML文件
        with open(file_old, 'r', encoding="utf-8") as file:
            old_data = self.yaml.load(file)

        # 加载新的YAML文件
        with open(file_new, 'r', encoding="utf-8") as file:
            new_data = self.yaml.load(file)

        # 遍历旧的YAML数据并更新新的YAML数据中的相应值
        self.merge_dicts(old_data, new_data)

        # 把新的YAML数据保存到新的文件中，保留注释
        with open(file_new, 'w', encoding="utf-8") as file:
            self.yaml.dump(new_data, file)

    def stop_watching(self):
        """停止文件监控"""
        if hasattr(self, 'observer'):
            self.observer.stop()
            self.observer.join()

    @staticmethod
    def get_instance() -> 'YAMLManager':
        """获取已创建的 YAMLManager 实例（线程安全）"""
        with YAMLManager._lock:
            if YAMLManager._instance is None:
                YAMLManager._instance = YAMLManager()
            return YAMLManager._instance

    def save_yaml(self, config_name: str, plugin_name: str = None):
        """保存某个 YAML 数据到文件"""
        if plugin_name is None:
            if config_name not in self.file_paths:
                raise ValueError(f"YAML file {config_name} not managed by YAMLManager.")
            file_path = self.file_paths[config_name]
            data = self.data[config_name]
        else:
            if plugin_name not in self.file_paths or config_name not in self.file_paths[plugin_name]:
                raise ValueError(f"YAML file {config_name} in plugin {plugin_name} not managed by YAMLManager.")
            file_path = self.file_paths[plugin_name][config_name]
            data = self.data[plugin_name][config_name]

        with open(file_path, 'w', encoding='utf-8') as file:
            self.yaml.dump(data, file)

    def __getattr__(self, name: str):
        """允许通过属性访问插件或直接 YAML 数据"""
        if name in self.data:
            if isinstance(self.data[name], dict) and name in self.file_paths and isinstance(self.file_paths[name],
                                                                                            dict):
                # 插件文件夹
                return PluginConfig(name, self.data[name], self.file_paths[name], self.save_yaml)
            else:
                # 直接在 run 目录下的 YAML 文件
                return self.data[name]
        raise AttributeError(f"YAMLManager has no plugin or config '{name}'.")

    def __setattr__(self, name: str, value: Any):
        """允许通过属性修改 YAML 数据"""
        if name in ["yaml", "data", "file_paths", "path_to_key", "run_dir", "event_handler", "observer", "_instance",
                    "_lock"]:
            super().__setattr__(name, value)
        elif hasattr(self, 'data') and name in self.data and not isinstance(self.data[name], dict):
            self.data[name] = value
            self.save_yaml(name)
        else:
            if hasattr(self, 'data'):
                raise AttributeError(f"YAMLManager cannot set attribute '{name}' directly.")
            super().__setattr__(name, value)

    def __del__(self):
        """析构函数，停止文件监控"""
        self.stop_watching()


# 测试你的合并逻辑的使用示例
if __name__ == "__main__":
    import tempfile
    config = YAMLManager()
    print(config.ai_llm.config,type(config.ai_llm.config))


