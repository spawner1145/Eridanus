import redis
import json
from typing import Dict, Any
import os
import time
from datetime import datetime

#递归合并字典中的同名字段
def merge_dicts(dict1, dict2):
    merged = dict1.copy()  # 复制 dict1 的数据
    for key, value in dict2.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            # 如果键存在且对应的值是嵌套字典，则递归合并
            merged[key] = merge_dicts(merged[key], value)
        else:
            # 否则直接覆盖
            merged[key] = value
    return merged

class RedisDatabase:
    def __init__(self, host="localhost", port=6379, db=0):
        """
        初始化 Redis 数据库连接，并设置数据存储路径和文件名。
        :param host: Redis 服务器地址
        :param port: Redis 服务器端口
        :param db: Redis 数据库编号
        """
        # 创建 Redis 连接
        self.pool = redis.ConnectionPool(host=host, port=port, db=db, decode_responses=True)
        self.redis = redis.StrictRedis(connection_pool=self.pool)

    def write_user(self, user_id: str, user_data: Dict[str, Any]):
        """
        将用户数据以嵌套字典的形式存储到 Redis 中（通过 JSON 序列化）。
        """

        key = f"user:{user_id}"

        # 读取旧数据
        existing_data = self.read_user(user_id)

        # 合并新数据与旧数据（旧数据保留，新数据覆盖同名字段）
        merged_data = merge_dicts(existing_data, user_data)

        # 序列化为 JSON 字符串并写入 Redis
        json_data = json.dumps(merged_data)
        self.redis.set(key, json_data)

    def read_user(self, user_id: str) -> Dict[str, Any]:
        """
        读取用户数据，并将 JSON 字符串反序列化为嵌套字典。
        """
        key = f"user:{user_id}"
        json_data = self.redis.get(key)
        if json_data:
            return json.loads(json_data)
        return {}

    def update_user_field(self, user_id: str, field_path: str, value: Any):
        """
        更新嵌套字典中的某个字段。
        :param user_id: 用户 ID
        :param field_path: 嵌套字段的路径，例如 "address.city"
        :param value: 要更新的值
        """
        user_data = self.read_user(user_id)
        if not user_data:
            return False

        # 解析字段路径并更新对应的嵌套值
        keys = field_path.split(".")
        target = user_data
        for key in keys[:-1]:
            target = target.setdefault(key, {})
        target[keys[-1]] = value

        # 写回 Redis
        self.write_user(user_id, user_data)
        return True

    def delete_user_field(self, user_id: str, field_path: str):
        """
        删除嵌套字典中的某个字段。
        """
        user_data = self.read_user(user_id)
        if not user_data:
            return False

        # 解析字段路径并删除对应的嵌套值
        keys = field_path.split(".")
        target = user_data
        for key in keys[:-1]:
            target = target.get(key, {})
            if not isinstance(target, dict):
                return False
        target.pop(keys[-1], None)

        # 写回 Redis
        self.write_user(user_id, user_data)
        return True

    def delete_user(self, user_id: str):
        """
        删除整个用户数据。
        """
        key = f"user:{user_id}"
        self.redis.delete(key)

    def write_multiple_users(self, users: Dict[str, Dict[str, Any]]):
        """
        一次写入多个用户的数据（嵌套字典形式）。
        """
        pipe = self.redis.pipeline()
        for user_id, user_data in users.items():
            key = f"user:{user_id}"
            json_data = json.dumps(user_data)
            pipe.set(key, json_data)
        pipe.execute()

    def read_all_users(self, user_prefix: str = "user:") -> Dict[str, Dict[str, Any]]:
        """
        读取所有用户数据，返回一个嵌套字典，key 为用户 ID，value 是嵌套字典数据。
        """
        keys = self.redis.keys(f"{user_prefix}*")
        users_data = {}
        for key in keys:
            user_id = key.split(":")[1]
            json_data = self.redis.get(key)
            if json_data:
                users_data[user_id] = json.loads(json_data)
        return users_data

    def save_to_disk(self):
        """
        手动保存 Redis 数据到磁盘（RDB 文件）。
        """
        try:
            self.redis.save()  # 同步保存数据到磁盘
            print("Data saved to disk successfully.")
        except redis.exceptions.ResponseError as e:
            print(f"Error saving data to disk: {e}")

    def load_from_disk(self):
        """
        加载 Redis 数据从磁盘文件恢复。
        """
        # Redis 自动会在启动时加载 RDB 文件，此处仅提及流程
        print("Redis 数据会在启动时自动加载。确保 RDB 文件存在于指定目录。")

# 示例使用
if __name__ == "__main__":
    # 指定存储目录和数据库文件名
    storage_dir = "E:\Others\github/bot\Eridanus\data\dataBase"
    storage_file = "test.rdb"

    # 初始化 Redis 数据库实例
    db = RedisDatabase(data_dir=storage_dir, db_file=storage_file)

    # 写入单个用户数据（嵌套字典形式存储）
    user_data = {
        "name": "Alice",
        "age": 25,
        "address": {
            "city": "New York",
            "zip": "10001"
        },
        "preferences": {
            "food": "Pizza",
            "color": "Blue"
        }
    }
    db.write_user("user1", user_data)

    # 读取单个用户数据
    user1_data = db.read_user("user1")
    print("User1 Data:", user1_data)

    # 更新用户数据中的某个嵌套字段
    db.update_user_field("user1", "address.city", "Los Angeles")
    updated_user1 = db.read_user("user1")
    print("Updated User1 Data:", updated_user1)

    # 删除用户数据中的某个嵌套字段
    db.delete_user_field("user1", "preferences.food")
    user1_after_deletion = db.read_user("user1")
    print("User1 Data After Field Deletion:", user1_after_deletion)

    # 写入多个用户数据
    users = {
        "user2": {
            "name": "Bob",
            "age": 30,
            "address": {
                "city": "Chicago",
                "zip": "60601"
            },
            "preferences": {
                "food": "Burger",
                "color": "Red"
            }
        },
        "user3": {
            "name": "Charlie",
            "age": 22,
            "address": {
                "city": "San Francisco",
                "zip": "94101"
            },
            "preferences": {
                "food": "Sushi",
                "color": "Green"
            }
        }
    }
    db.write_multiple_users(users)

    # 读取所有用户数据
    all_users = db.read_all_users()
    print("All Users Data:", all_users)

    # 删除整个用户数据
    db.delete_user("user1")
    print("User1 After Deletion:", db.read_user("user1"))

    # 手动保存数据到磁盘
    db.save_to_disk()

    print(f"Redis 数据已存储到指定目录：{storage_dir}, 文件名：{storage_file}")