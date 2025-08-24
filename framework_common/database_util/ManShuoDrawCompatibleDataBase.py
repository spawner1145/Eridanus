import aiosqlite
import json
import asyncio
from typing import Dict, Any, Optional
import os
from datetime import datetime
from pathlib import Path

from developTools.utils.logger import get_logger

logger=get_logger(__name__.split('.')[-1])

# 递归合并字典中的同名字段
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


class AsyncSQLiteDatabase:
    _instance = None
    _lock = asyncio.Lock()
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(AsyncSQLiteDatabase, cls).__new__(cls)
        return cls._instance

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def initialize(self, db_path: str = "manshuo.db", storage_dir: str = "data/database"):
        """
        初始化 SQLite 数据库连接，并创建必要的表结构。
        :param db_path: SQLite 数据库文件路径
        :param storage_dir: 数据库存储目录
        """
        logger.info(f"Initializing SQLite database at {db_path}")
        async with self._lock:
            if self._initialized:
                return

            if storage_dir:
                # 确保目录存在
                Path(storage_dir).mkdir(parents=True, exist_ok=True)
                self.db_path = os.path.join(storage_dir, db_path)
            else:
                self.db_path = db_path

            # 创建连接池的概念 - 使用信号量控制并发连接数
            self._semaphore = asyncio.Semaphore(50)  # 最大50个并发连接

            # 初始化数据库表结构
            await self._init_database()
            self._initialized = True

    async def _get_connection(self):
        """获取数据库连接的上下文管理器"""
        await self._semaphore.acquire()
        try:
            conn = await aiosqlite.connect(self.db_path)
            conn.row_factory = aiosqlite.Row
            return conn
        except Exception as e:
            self._semaphore.release()
            raise e

    async def _release_connection(self, conn):
        """释放数据库连接"""
        if conn:
            await conn.close()
        self._semaphore.release()

    async def _init_database(self):
        """初始化数据库表结构"""
        conn = await self._get_connection()
        try:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    user_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 创建索引提高查询性能
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_users_updated_at ON users(updated_at)
            ''')

            await conn.commit()
        finally:
            await self._release_connection(conn)

    async def write_user(self, user_id: str, user_data: Dict[str, Any]):
        """
        将用户数据以嵌套字典的形式存储到 SQLite 中（通过 JSON 序列化）。
        """
        logger.info(f"Writing user {user_id} to {self.db_path}")
        # 读取旧数据
        existing_data = await self.read_user(user_id)

        # 合并新数据与旧数据（旧数据保留，新数据覆盖同名字段）
        merged_data = merge_dicts(existing_data, user_data)

        # 序列化为 JSON 字符串
        json_data = json.dumps(merged_data, ensure_ascii=False)

        conn = await self._get_connection()
        try:
            await conn.execute('''
                INSERT OR REPLACE INTO users (user_id, user_data, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, json_data))
            await conn.commit()
        finally:
            await self._release_connection(conn)

    async def read_user(self, user_id: str) -> Dict[str, Any]:
        """
        读取用户数据，并将 JSON 字符串反序列化为嵌套字典。
        """
        logger.info(f"Reading user {user_id} from {self.db_path}")
        conn = await self._get_connection()
        try:
            cursor = await conn.execute(
                'SELECT user_data FROM users WHERE user_id = ?',
                (user_id,)
            )
            row = await cursor.fetchone()

            if row:
                return json.loads(row['user_data'])
            return {}
        finally:
            await self._release_connection(conn)

    async def update_user_field(self, user_id: str, field_path: str, value: Any) -> bool:
        """
        更新嵌套字典中的某个字段。
        :param user_id: 用户 ID
        :param field_path: 嵌套字段的路径，例如 "address.city"
        :param value: 要更新的值
        """
        logger.info(f"Updating user {user_id} field {field_path} to {value}")
        user_data = await self.read_user(user_id)
        if not user_data:
            return False

        # 解析字段路径并更新对应的嵌套值
        keys = field_path.split(".")
        target = user_data
        for key in keys[:-1]:
            target = target.setdefault(key, {})
        target[keys[-1]] = value

        # 写回数据库
        await self.write_user(user_id, user_data)
        return True

    async def delete_user_field(self, user_id: str, field_path: str) -> bool:
        """
        删除嵌套字典中的某个字段。
        """
        logger.info(f"Deleting user {user_id} field {field_path}")
        user_data = await self.read_user(user_id)
        if not user_data:
            return False

        # 解析字段路径并删除对应的嵌套值
        keys = field_path.split(".")
        target = user_data
        for key in keys[:-1]:
            target = target.get(key, {})
            if not isinstance(target, dict):
                return False

        if keys[-1] in target:
            target.pop(keys[-1], None)
            # 写回数据库
            await self.write_user(user_id, user_data)
            return True
        return False

    async def delete_user(self, user_id: str) -> bool:
        """
        删除整个用户数据。
        """
        logger.info(f"Deleting user {user_id} from {self.db_path}")
        conn = await self._get_connection()
        try:
            cursor = await conn.execute(
                'DELETE FROM users WHERE user_id = ?',
                (user_id,)
            )
            await conn.commit()
            return cursor.rowcount > 0
        finally:
            await self._release_connection(conn)

    async def write_multiple_users(self, users: Dict[str, Dict[str, Any]]):
        """
        一次写入多个用户的数据（嵌套字典形式）。
        """
        logger.info(f"Writing multiple users to {self.db_path}")
        conn = await self._get_connection()
        try:
            # 使用事务提高性能
            await conn.execute('BEGIN TRANSACTION')

            for user_id, user_data in users.items():
                json_data = json.dumps(user_data, ensure_ascii=False)
                await conn.execute('''
                    INSERT OR REPLACE INTO users (user_id, user_data, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                ''', (user_id, json_data))

            await conn.commit()
        except Exception as e:
            await conn.rollback()
            raise e
        finally:
            await self._release_connection(conn)

    async def read_all_users(self, user_prefix: str = None) -> Dict[str, Dict[str, Any]]:
        """
        读取所有用户数据，返回一个嵌套字典，key 为用户 ID，value 是嵌套字典数据。
        :param user_prefix: 用户ID前缀过滤器，如果提供则只返回匹配前缀的用户
        """
        logger.info(f"Reading all users from {self.db_path}")
        conn = await self._get_connection()
        try:
            if user_prefix:
                cursor = await conn.execute(
                    'SELECT user_id, user_data FROM users WHERE user_id LIKE ?',
                    (f'{user_prefix}%',)
                )
            else:
                cursor = await conn.execute('SELECT user_id, user_data FROM users')

            users_data = {}
            async for row in cursor:
                user_id = row['user_id']
                user_data = json.loads(row['user_data'])
                users_data[user_id] = user_data

            return users_data
        finally:
            await self._release_connection(conn)

    async def save_to_disk(self):
        """
        手动执行数据库同步（SQLite 自动持久化，此方法执行 WAL checkpoint）。
        """
        conn = await self._get_connection()
        try:
            await conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            await conn.commit()
            print("Database checkpoint completed successfully.")
        except Exception as e:
            print(f"Error during database checkpoint: {e}")
        finally:
            await self._release_connection(conn)

    async def load_from_disk(self):
        """
        SQLite 数据会自动从文件加载，此方法仅用于兼容性。
        """
        print("SQLite 数据会在连接时自动加载。数据库文件路径:", self.db_path)

    async def get_user_count(self) -> int:
        """获取用户总数"""
        logger.info(f"Getting user count from {self.db_path}")
        conn = await self._get_connection()
        try:
            cursor = await conn.execute('SELECT COUNT(*) as count FROM users')
            row = await cursor.fetchone()
            return row['count']
        finally:
            await self._release_connection(conn)

    async def get_users_by_pattern(self, pattern: str) -> Dict[str, Dict[str, Any]]:
        """
        通过模式匹配获取用户数据
        :param pattern: SQL LIKE 模式，例如 '%test%'
        """
        conn = await self._get_connection()
        try:
            cursor = await conn.execute(
                'SELECT user_id, user_data FROM users WHERE user_id LIKE ?',
                (pattern,)
            )

            users_data = {}
            async for row in cursor:
                user_id = row['user_id']
                user_data = json.loads(row['user_data'])
                users_data[user_id] = user_data

            return users_data
        finally:
            await self._release_connection(conn)

    async def close(self):
        """关闭数据库连接（清理资源）"""
        # SQLite 连接在每次使用后都会自动关闭
        # 这里主要用于清理单例状态
        pass

    @classmethod
    async def get_instance(cls, db_path: str = "ManshuoCompatibledData.db", storage_dir: str = "data/database")-> "AsyncSQLiteDatabase":
        """
        获取数据库实例的异步方法
        """
        logger.info(f"Getting database instance for {db_path}")
        instance = cls()
        if not instance._initialized:
            await instance.initialize(db_path, storage_dir)
        return instance


# 示例使用
async def main():
    """
    异步示例使用方法
    """
    # 指定存储目录和数据库文件名
    storage_dir = "E:\\Others\\github\\bot\\Eridanus\\data\\dataBase"
    storage_file = "test.db"

    # 获取数据库实例（单例模式）
    db = await AsyncSQLiteDatabase.get_instance(storage_file, storage_dir)

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
    await db.write_user("user1", user_data)

    # 读取单个用户数据
    user1_data = await db.read_user("user1")
    print("User1 Data:", user1_data)

    # 更新用户数据中的某个嵌套字段
    await db.update_user_field("user1", "address.city", "Los Angeles")
    updated_user1 = await db.read_user("user1")
    print("Updated User1 Data:", updated_user1)

    # 删除用户数据中的某个嵌套字段
    await db.delete_user_field("user1", "preferences.food")
    user1_after_deletion = await db.read_user("user1")
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
    await db.write_multiple_users(users)

    # 读取所有用户数据
    all_users = await db.read_all_users()
    print("All Users Data:", all_users)

    # 获取用户总数
    user_count = await db.get_user_count()
    print(f"Total users: {user_count}")

    # 删除整个用户数据
    await db.delete_user("user1")
    print("User1 After Deletion:", await db.read_user("user1"))

    # 手动保存数据到磁盘
    await db.save_to_disk()

    print(f"SQLite 数据已存储到指定目录：{storage_dir}, 文件名：{storage_file}")

    # 演示高并发查询
    print("\n演示高并发查询...")
    tasks = []
    for i in range(100):
        task = db.read_user(f"user{i % 3 + 1}")  # 循环查询已存在的用户
        tasks.append(task)

    # 并发执行所有查询
    start_time = datetime.now()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    end_time = datetime.now()

    print(f"完成100个并发查询，耗时: {(end_time - start_time).total_seconds():.3f}秒")
    print(f"成功查询数: {sum(1 for r in results if isinstance(r, dict))}")


if __name__ == "__main__":
    asyncio.run(main())