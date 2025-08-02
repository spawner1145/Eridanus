import json
import os
import platform
import subprocess
import time
import zipfile
from typing import Optional, Any, Dict, List
import redis
from developTools.utils.logger import get_logger

logger = get_logger()


class RedisCacheManager:
    """Redis缓存管理器 - 统一管理不同数据库的Redis缓存"""

    # 类级别的连接池，按数据库编号存储
    _connection_pools: Dict[int, redis.StrictRedis] = {}
    _initialized_dbs: set = set()

    # Redis服务配置
    REDIS_EXECUTABLE = "redis-server.exe"
    REDIS_ZIP_PATH = os.path.join("data", "Redis-x64-5.0.14.1.zip")
    REDIS_FOLDER = os.path.join("data", "redis_extracted")

    def __init__(self, db_number: int = 0, cache_ttl: int = 300):
        """
        初始化Redis缓存管理器

        Args:
            db_number: Redis数据库编号 (0-15)
            cache_ttl: 缓存过期时间（秒）
        """
        self.db_number = db_number
        self.cache_ttl = cache_ttl
        self.redis_client = None

        # 根据环境确定Redis URL
        if self._is_running_in_docker():
            self.redis_url = f"redis://redis:6379/{db_number}"
        else:
            self.redis_url = f"redis://localhost/{db_number}"

        # 初始化连接
        self._init_connection()

    @staticmethod
    def _is_running_in_docker() -> bool:
        """检查是否在Docker环境中运行"""
        return os.path.exists("/.dockerenv") or os.environ.get("IN_DOCKER") == "1"

    @classmethod
    def _extract_redis_from_local_zip(cls):
        """从本地 zip 解压 Redis 到指定目录"""
        if not os.path.exists(cls.REDIS_FOLDER):
            os.makedirs(cls.REDIS_FOLDER)
            logger.info("📦 正在从本地压缩包解压 Redis...")
            try:
                with zipfile.ZipFile(cls.REDIS_ZIP_PATH, 'r') as zip_ref:
                    zip_ref.extractall(cls.REDIS_FOLDER)
                logger.info("✅ Redis 解压完成")
            except Exception as e:
                logger.error(f"❌ Redis 解压失败: {e}")

    @classmethod
    def _start_redis_background(cls):
        """在后台启动 Redis（支持 Windows 和 Linux）"""
        system = platform.system()
        cls._extract_redis_from_local_zip()

        if system == "Windows":
            redis_path = os.path.join(cls.REDIS_FOLDER, cls.REDIS_EXECUTABLE)
            if not os.path.exists(redis_path):
                logger.error(f"❌ 找不到 redis-server.exe 于 {redis_path}")
                return
            logger.info("🚀 启动 Redis 服务中 (Windows)...")
            subprocess.Popen([redis_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif system == "Linux":
            try:
                logger.info("🚀 尝试在后台启动 Redis 服务 (Linux)...")
                subprocess.Popen(["redis-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                logger.error("❌ 'redis-server' 命令未找到。请确保 Redis 已安装并在系统的 PATH 中。")
            except Exception as e:
                logger.error(f"❌ 在 Linux 上启动 Redis 失败: {e}")
        else:
            logger.warning(f"⚠️ 不支持在 {system} 系统上自动启动 Redis。")

    def _init_connection(self):
        """初始化Redis连接"""
        # 检查是否已有该数据库的连接
        if self.db_number in self._connection_pools:
            self.redis_client = self._connection_pools[self.db_number]
            return

        try:
            # 创建新的Redis连接
            client = redis.StrictRedis.from_url(
                self.redis_url,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            client.ping()

            # 存储到连接池
            self._connection_pools[self.db_number] = client
            self.redis_client = client
            self._initialized_dbs.add(self.db_number)

            logger.info(f"✅ Redis 连接成功（数据库 db{self.db_number}）")

        except redis.exceptions.ConnectionError:
            logger.warning(f"⚠️ Redis 数据库 {self.db_number} 未运行，尝试自动启动 Redis...")

            # 尝试启动Redis（只在第一次失败时启动）
            if not any(self._initialized_dbs):
                self._start_redis_background()
                time.sleep(2)

            try:
                client = redis.StrictRedis.from_url(
                    self.redis_url,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30
                )
                client.ping()

                self._connection_pools[self.db_number] = client
                self.redis_client = client
                self._initialized_dbs.add(self.db_number)

                logger.info(f"✅ Redis 已自动启动并连接成功（数据库 db{self.db_number}）")

            except Exception as e:
                logger.error(f"❌ Redis 数据库 {self.db_number} 连接失败：{e}")
                self.redis_client = None

    def is_connected(self) -> bool:
        """检查Redis连接状态"""
        return self.redis_client is not None

    def get(self, key: str) -> Optional[Any]:
        """获取缓存数据"""
        if not self.redis_client:
            return None

        try:
            cached = self.redis_client.get(key)
            return json.loads(cached) if cached else None
        except Exception as e:
            logger.debug(f"Redis读取失败 (db{self.db_number}): {e}")
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存数据"""
        if not self.redis_client:
            return False

        try:
            ttl = ttl or self.cache_ttl
            self.redis_client.setex(key, ttl, json.dumps(value))
            return True
        except Exception as e:
            logger.debug(f"Redis写入失败 (db{self.db_number}): {e}")
            return False

    def delete(self, key: str) -> bool:
        """删除指定缓存"""
        if not self.redis_client:
            return False

        try:
            self.redis_client.delete(key)
            return True
        except Exception as e:
            logger.debug(f"Redis删除失败 (db{self.db_number}): {e}")
            return False

    def delete_pattern(self, pattern: str) -> bool:
        """删除匹配模式的缓存"""
        if not self.redis_client:
            return False

        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
            return True
        except Exception as e:
            logger.debug(f"Redis模式删除失败 (db{self.db_number}): {e}")
            return False

    def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        if not self.redis_client:
            return False

        try:
            return bool(self.redis_client.exists(key))
        except Exception as e:
            logger.debug(f"Redis存在性检查失败 (db{self.db_number}): {e}")
            return False

    def expire(self, key: str, ttl: int) -> bool:
        """设置缓存过期时间"""
        if not self.redis_client:
            return False

        try:
            return bool(self.redis_client.expire(key, ttl))
        except Exception as e:
            logger.debug(f"Redis过期时间设置失败 (db{self.db_number}): {e}")
            return False

    def get_keys(self, pattern: str = "*") -> List[str]:
        """获取匹配模式的所有键"""
        if not self.redis_client:
            return []

        try:
            keys = self.redis_client.keys(pattern)
            return [key.decode('utf-8') if isinstance(key, bytes) else key for key in keys]
        except Exception as e:
            logger.debug(f"Redis键获取失败 (db{self.db_number}): {e}")
            return []

    def flush_db(self) -> bool:
        """清空当前数据库"""
        if not self.redis_client:
            return False

        try:
            self.redis_client.flushdb()
            logger.info(f"✅ Redis 数据库 {self.db_number} 已清空")
            return True
        except Exception as e:
            logger.error(f"❌ Redis 数据库 {self.db_number} 清空失败: {e}")
            return False

    def get_info(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        if not self.redis_client:
            return {
                "connected": False,
                "db_number": self.db_number,
                "cache_ttl": self.cache_ttl,
                "redis_url": self.redis_url
            }

        try:
            info = self.redis_client.info()
            return {
                "connected": True,
                "db_number": self.db_number,
                "cache_ttl": self.cache_ttl,
                "redis_url": self.redis_url,
                "redis_info": {
                    "used_memory": info.get("used_memory_human"),
                    "connected_clients": info.get("connected_clients"),
                    "total_commands_processed": info.get("total_commands_processed"),
                    "keyspace_hits": info.get("keyspace_hits"),
                    "keyspace_misses": info.get("keyspace_misses")
                }
            }
        except Exception as e:
            logger.debug(f"Redis信息获取失败 (db{self.db_number}): {e}")
            return {
                "connected": True,
                "db_number": self.db_number,
                "cache_ttl": self.cache_ttl,
                "redis_url": self.redis_url,
                "error": str(e)
            }

    @classmethod
    def get_all_connections_info(cls) -> Dict[int, Dict[str, Any]]:
        """获取所有连接的信息"""
        info = {}
        for db_num, client in cls._connection_pools.items():
            try:
                client.ping()
                info[db_num] = {
                    "status": "connected",
                    "initialized": db_num in cls._initialized_dbs
                }
            except Exception as e:
                info[db_num] = {
                    "status": "disconnected",
                    "error": str(e),
                    "initialized": db_num in cls._initialized_dbs
                }
        return info

    @classmethod
    def close_all_connections(cls):
        """关闭所有Redis连接"""
        for db_num, client in cls._connection_pools.items():
            try:
                client.close()
                logger.info(f"✅ Redis 数据库 {db_num} 连接已关闭")
            except Exception as e:
                logger.error(f"❌ 关闭 Redis 数据库 {db_num} 连接失败: {e}")

        cls._connection_pools.clear()
        cls._initialized_dbs.clear()

    def __del__(self):
        """析构函数 - 清理资源"""
        # 注意：不在这里关闭连接，因为连接是共享的
        pass

    def __repr__(self):
        return f"RedisCacheManager(db_number={self.db_number}, connected={self.is_connected()})"


# 便捷函数：创建不同数据库的缓存管理器
def create_user_cache_manager(cache_ttl: int = 60) -> RedisCacheManager:
    """创建用户数据库缓存管理器 (db1)"""
    return RedisCacheManager(db_number=1, cache_ttl=cache_ttl)


def create_group_cache_manager(cache_ttl: int = 300) -> RedisCacheManager:
    """创建群组消息缓存管理器 (db0)"""
    return RedisCacheManager(db_number=0, cache_ttl=cache_ttl)


def create_custom_cache_manager(db_number: int, cache_ttl: int = 300) -> RedisCacheManager:
    """创建自定义数据库缓存管理器"""
    return RedisCacheManager(db_number=db_number, cache_ttl=cache_ttl)