import json
import os
import pickle
import platform
import subprocess
import zipfile
import sqlite3

import aiosqlite
import datetime
import asyncio
import traceback

import redis

from developTools.utils.logger import get_logger
from functools import wraps
import time
from typing import Optional

dbpath = "data/dataBase/user_management.db"


def is_running_in_docker():
    return os.path.exists("/.dockerenv") or os.environ.get("IN_DOCKER") == "1"


if is_running_in_docker():
    REDIS_URL = "redis://redis:6379/1"
else:
    REDIS_URL = "redis://localhost/1"

REDIS_CACHE_TTL = 60  # 秒
REDIS_EXECUTABLE = "redis-server.exe"
REDIS_ZIP_PATH = os.path.join("data", "Redis-x64-5.0.14.1.zip")
REDIS_FOLDER = os.path.join("data", "redis_extracted")

logger = get_logger()
redis_client = None

# 全局变量存储初始化状态
_db_initialized: bool = False

# 数据库连接重试配置
DB_RETRY_ATTEMPTS = 3
DB_RETRY_DELAY = 1.0  # 秒
DB_CONNECTION_TIMEOUT = 30.0  # 秒


def database_retry(max_attempts=DB_RETRY_ATTEMPTS, delay=DB_RETRY_DELAY):
    """数据库操作重试装饰器"""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    last_exception = e
                    error_msg = str(e).lower()

                    if "unable to open database" in error_msg or "database is locked" in error_msg:
                        logger.warning(f"数据库连接失败 (尝试 {attempt + 1}/{max_attempts}): {e}")

                        if attempt < max_attempts - 1:
                            # 尝试修复数据库连接
                            await _handle_database_connection_error()
                            await asyncio.sleep(delay * (attempt + 1))  # 递增延迟
                            continue
                    raise e
                except Exception as e:
                    # 对于其他异常，不重试
                    raise e

            # 所有重试都失败了
            logger.error(f"数据库操作在 {max_attempts} 次尝试后仍然失败")
            raise last_exception

        return wrapper

    return decorator


async def _handle_database_connection_error():
    """处理数据库连接错误的恢复逻辑"""
    global _db_initialized

    try:
        logger.info("🔧 尝试修复数据库连接...")

        # 1. 检查数据库文件和目录权限
        db_dir = os.path.dirname(dbpath)
        if not os.path.exists(db_dir):
            logger.info(f"📁 创建数据库目录: {db_dir}")
            os.makedirs(db_dir, exist_ok=True)

        # 2. 检查数据库文件是否存在和可访问
        if os.path.exists(dbpath):
            # 检查文件权限
            if not os.access(dbpath, os.R_OK | os.W_OK):
                logger.warning("⚠️ 数据库文件权限不足，尝试修复...")
                try:
                    os.chmod(dbpath, 0o664)
                except Exception as chmod_error:
                    logger.warning(f"修改文件权限失败: {chmod_error}")

        # 3. 尝试打开数据库进行简单测试
        try:
            async with aiosqlite.connect(dbpath, timeout=DB_CONNECTION_TIMEOUT) as test_db:
                await test_db.execute("SELECT 1")
                logger.info("✅ 数据库连接测试成功")
        except Exception as test_error:
            logger.warning(f"数据库连接测试失败: {test_error}")

            # 4. 如果连接测试失败，尝试备份并重新初始化
            if os.path.exists(dbpath):
                backup_path = f"{dbpath}.backup_{int(time.time())}"
                try:
                    os.rename(dbpath, backup_path)
                    logger.info(f"📦 已备份损坏的数据库文件到: {backup_path}")
                except Exception as backup_error:
                    logger.warning(f"备份数据库失败: {backup_error}")

        # 5. 重置初始化标志，强制重新初始化
        _db_initialized = False

        # 6. 清除相关缓存
        if redis_client:
            try:
                # 清除所有用户缓存
                for key in redis_client.scan_iter(match="user:*"):
                    redis_client.delete(key)
                logger.info("🧹 已清除Redis缓存")
            except Exception as cache_error:
                logger.debug(f"清除缓存失败: {cache_error}")

        logger.info("🔧 数据库连接修复处理完成")

    except Exception as recovery_error:
        logger.error(f"❌ 数据库连接恢复失败: {recovery_error}")


async def _safe_db_connect(timeout=DB_CONNECTION_TIMEOUT):
    """安全的数据库连接函数"""
    try:
        # 确保目录存在
        db_dir = os.path.dirname(dbpath)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        return aiosqlite.connect(dbpath, timeout=timeout)
    except Exception as e:
        logger.error(f"创建数据库连接失败: {e}")
        raise


def extract_redis_from_local_zip():
    """从本地 zip 解压 Redis 到指定目录"""
    if not os.path.exists(REDIS_FOLDER):
        os.makedirs(REDIS_FOLDER)
        logger.info("📦 正在从本地压缩包解压 Redis...")
        with zipfile.ZipFile(REDIS_ZIP_PATH, 'r') as zip_ref:
            zip_ref.extractall(REDIS_FOLDER)
        logger.info("✅ Redis 解压完成")


def start_redis_background():
    """在后台启动 Redis（支持 Windows 和 Linux）"""
    system = platform.system()
    extract_redis_from_local_zip()
    if system == "Windows":
        redis_path = os.path.join(REDIS_FOLDER, REDIS_EXECUTABLE)
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


def init_redis():
    global redis_client
    if redis_client is not None:
        return
    try:
        redis_client = redis.StrictRedis.from_url(
            REDIS_URL,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30
        )
        redis_client.ping()
        logger.info("✅ Redis 连接成功（数据库 db user）")
    except redis.exceptions.ConnectionError:
        logger.warning("⚠️ Redis 未运行，尝试自动启动 Redis...")
        system = platform.system()
        if system == "Windows" or system == "Linux":
            start_redis_background()
            time.sleep(2)
            try:
                redis_client = redis.StrictRedis.from_url(
                    REDIS_URL,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30
                )
                redis_client.ping()
                logger.info(f"✅ Redis 已在 {system} 上自动启动并连接成功（数据库 db1）")
            except Exception as e:
                logger.error(f"❌ Redis 自动启动后连接失败：{e}")
                redis_client = None
        else:
            logger.error(f"❌ 非 Windows/Linux 系统，请手动安装并启动 Redis")
            redis_client = None


async def ensure_db_initialized():
    """确保数据库已初始化"""
    global _db_initialized
    if not _db_initialized:
        await initialize_db()
        _db_initialized = True


# 初始化数据库，新增注册时间字段
@database_retry()
async def initialize_db():
    """初始化数据库表结构"""
    try:
        # 确保数据库目录存在
        db_dir = os.path.dirname(dbpath)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

        async with await _safe_db_connect() as db:
            # 优化数据库设置
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            await db.execute("PRAGMA cache_size=10000;")
            await db.execute("PRAGMA temp_store=MEMORY;")
            await db.execute("PRAGMA busy_timeout=5000;")

            await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                nickname TEXT,
                card TEXT,
                sex TEXT DEFAULT '0',
                age INTEGER DEFAULT 0,
                city TEXT DEFAULT '通辽',
                permission INTEGER DEFAULT 0,
                signed_days TEXT,
                registration_date TEXT,
                ai_token_record INTEGER DEFAULT 0,
                user_portrait TEXT DEFAULT '',
                portrait_update_time TEXT DEFAULT ''
            )
            """)

            # 检查并添加缺失的列
            async with db.execute("PRAGMA table_info(users);") as cursor:
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]

                if 'user_portrait' not in column_names:
                    await db.execute("ALTER TABLE users ADD COLUMN user_portrait TEXT DEFAULT '';")
                    logger.info("✅ 添加了 user_portrait 列")

                if 'portrait_update_time' not in column_names:
                    await db.execute("ALTER TABLE users ADD COLUMN portrait_update_time TEXT DEFAULT '';")
                    logger.info("✅ 添加了 portrait_update_time 列")

            # 创建索引优化查询
            await db.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON users(user_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_permission ON users(permission);")

            await db.commit()
            logger.info("✅ 用户数据库初始化完成")

    except Exception as e:
        logger.error(f"❌ 数据库初始化失败: {e}")
        raise


# User 类
class User:
    def __init__(self, user_id, nickname, card, sex, age, city, permission, signed_days, registration_date,
                 ai_token_record, user_portrait="", portrait_update_time=""):
        self.user_id = user_id
        self.nickname = nickname
        self.card = card
        self.sex = sex
        self.age = age
        self.city = city
        self.permission = permission
        self.signed_days = signed_days
        self.registration_date = registration_date
        self.ai_token_record = ai_token_record
        self.user_portrait = user_portrait
        self.portrait_update_time = portrait_update_time

    def __repr__(self):
        return (f"User(user_id={self.user_id}, nickname={self.nickname}, card={self.card}, "
                f"sex={self.sex}, age={self.age}, city={self.city}, permission={self.permission}, "
                f"signed_days={self.signed_days}, registration_date={self.registration_date}, "
                f"ai_token_record={self.ai_token_record}, user_portrait={self.user_portrait}, "
                f"portrait_update_time={self.portrait_update_time})")


@database_retry()
async def add_user(user_id, nickname, card, sex="0", age=0, city="通辽", permission=0, ai_token_record=0):
    """添加新用户"""
    # 确保数据库已初始化
    await ensure_db_initialized()

    async with await _safe_db_connect() as db:
        async with db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)) as cursor:
            if await cursor.fetchone():
                return f"✅ 用户 {user_id} 已存在，无法重复注册。"

        registration_date = datetime.date.today().isoformat()
        await db.execute("""
        INSERT INTO users (user_id, nickname, card, sex, age, city, permission, signed_days, registration_date, ai_token_record)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, nickname, card, sex, age, city, permission, "[]", registration_date, ai_token_record))
        await db.commit()

        # 清除缓存
        if redis_client:
            try:
                redis_client.delete(f"user:{user_id}")
            except Exception as e:
                logger.debug(f"清除缓存失败: {e}")

        return f"✅ 用户 {user_id} 注册成功。"


@database_retry()
async def update_user(user_id, **kwargs):
    """更新用户信息"""
    # 确保数据库已初始化
    await ensure_db_initialized()

    valid_fields = ["nickname", "card", "sex", "age", "city", "permission",
                    'ai_token_record', 'user_portrait', 'portrait_update_time']

    async with await _safe_db_connect() as db:
        for key, value in kwargs.items():
            if key in valid_fields:
                await db.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (value, user_id))
            else:
                logger.warning(f"❌ 未知的用户字段 {key}，请检查输入是否正确。")
        await db.commit()

    # 清除缓存
    if redis_client:
        try:
            redis_client.delete(f"user:{user_id}")
        except Exception as e:
            logger.debug(f"清除缓存失败: {e}")

    logger.info(f"✅ 用户 {user_id} 的信息已更新：{kwargs}")
    return f"✅ 用户 {user_id} 的信息已更新：{kwargs}"


# 递归深度限制
MAX_RECURSION_DEPTH = 3


@database_retry()
async def get_user(user_id, nickname="", _recursion_depth=0) -> User:
    """获取用户信息，如果不存在则创建默认用户"""
    global _db_initialized

    # 检查递归深度，防止无限递归
    if _recursion_depth >= MAX_RECURSION_DEPTH:
        logger.error(f"get_user 递归深度超限 ({_recursion_depth})，返回默认用户对象")
        # 返回一个基本的用户对象，避免程序崩溃
        return User(
            user_id=user_id,
            nickname=f"{nickname}" if nickname else f"用户{user_id}",
            card="00000",
            sex="0",
            age=0,
            city="通辽",
            permission=0,
            signed_days="[]",
            registration_date=datetime.date.today().isoformat(),
            ai_token_record=0,
            user_portrait="",
            portrait_update_time=""
        )

    try:
        # 确保数据库已初始化
        await ensure_db_initialized()

        init_redis()
        cache_key = f"user:{user_id}"

        # 检查 Redis 缓存
        if redis_client:
            try:
                cached_user = redis_client.get(cache_key)
                if cached_user:
                    return pickle.loads(cached_user)
            except Exception as e:
                logger.debug(f"Redis 读取失败: {e}")

        default_user = {
            "user_id": user_id,
            "nickname": f"{nickname}" if nickname else f"用户{user_id}",
            "card": "00000",
            "sex": "0",
            "age": 0,
            "city": "通辽",
            "permission": 0,
            "signed_days": "[]",
            "registration_date": datetime.date.today().isoformat(),
            'ai_token_record': 0,
            "user_portrait": "",
            "portrait_update_time": ""
        }

        async with await _safe_db_connect() as db:
            # 首先检查表是否存在
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';") as cursor:
                table_exists = await cursor.fetchone()

            if not table_exists:
                logger.warning("用户表不存在，可能数据库被删除，重新初始化...")
                _db_initialized = False
                try:
                    await ensure_db_initialized()
                except Exception as init_error:
                    logger.error(f"数据库初始化失败: {init_error}")
                    # 初始化失败时，不要递归，直接返回默认用户
                    if _recursion_depth < MAX_RECURSION_DEPTH - 1:
                        return await get_user(user_id, nickname, _recursion_depth + 1)
                    else:
                        logger.error("数据库初始化多次失败，返回默认用户对象")
                        return User(**default_user)

            # 检查表结构并添加缺失列
            async with db.execute("PRAGMA table_info(users);") as cursor:
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]

                for key in default_user.keys():
                    if key not in column_names:
                        default_value = "''" if isinstance(default_user[key], str) else "0"
                        await db.execute(f"ALTER TABLE users ADD COLUMN {key} TEXT DEFAULT {default_value};")
                        await db.commit()
                        logger.info(f"列 {key} 已成功添加至 'users' 表中。")

            # 查询用户
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                result = await cursor.fetchone()

                if result:
                    # 用户存在，构建用户对象
                    column_names = [description[0] for description in cursor.description]
                    existing_user = dict(zip(column_names, result))

                    # 检查是否有缺失的字段
                    missing_keys = [key for key in default_user if key not in existing_user]
                    if missing_keys:
                        for key in missing_keys:
                            existing_user[key] = default_user[key]
                        update_query = f"UPDATE users SET {', '.join(f'{key} = ?' for key in missing_keys)} WHERE user_id = ?"
                        update_values = [existing_user[key] for key in missing_keys] + [user_id]
                        await db.execute(update_query, update_values)
                        await db.commit()

                    user_obj = User(
                        existing_user['user_id'],
                        existing_user['nickname'],
                        existing_user['card'],
                        existing_user['sex'],
                        existing_user['age'],
                        existing_user['city'],
                        existing_user['permission'],
                        existing_user['signed_days'],
                        existing_user['registration_date'],
                        existing_user['ai_token_record'],
                        existing_user.get('user_portrait', ""),
                        existing_user.get('portrait_update_time', "")
                    )
                else:
                    # 用户不存在，创建新用户
                    await db.execute("""
                    INSERT INTO users (user_id, nickname, card, sex, age, city, permission, signed_days, 
                                     registration_date, ai_token_record, user_portrait, portrait_update_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (user_id, default_user["nickname"], default_user["card"], default_user["sex"],
                          default_user["age"], default_user["city"], default_user["permission"],
                          default_user["signed_days"], default_user["registration_date"],
                          default_user["ai_token_record"], default_user["user_portrait"],
                          default_user["portrait_update_time"]))
                    await db.commit()
                    logger.info(f"用户 {user_id} 不在数据库中，已创建默认用户。")

                    user_obj = User(
                        default_user['user_id'],
                        default_user['nickname'],
                        default_user['card'],
                        default_user['sex'],
                        default_user['age'],
                        default_user['city'],
                        default_user['permission'],
                        default_user['signed_days'],
                        default_user['registration_date'],
                        default_user['ai_token_record'],
                        default_user['user_portrait'],
                        default_user['portrait_update_time']
                    )

                # 存储到 Redis 缓存
                if redis_client:
                    try:
                        redis_client.setex(cache_key, REDIS_CACHE_TTL, pickle.dumps(user_obj))
                    except Exception as e:
                        logger.debug(f"Redis 缓存失败: {e}")

                return user_obj

    except sqlite3.OperationalError as db_error:
        error_msg = str(db_error).lower()
        if "no such table" in error_msg:
            logger.warning(f"表不存在错误，重新初始化数据库: {db_error}")
            _db_initialized = False
            try:
                await ensure_db_initialized()
                # 仅在递归深度允许时才递归
                if _recursion_depth < MAX_RECURSION_DEPTH - 1:
                    return await get_user(user_id, nickname, _recursion_depth + 1)
                else:
                    logger.error("递归深度超限，返回默认用户对象")
                    return User(**default_user)
            except Exception as init_error:
                logger.error(f"数据库初始化失败: {init_error}")
                return User(**default_user)
        else:
            logger.error(f"获取用户 {user_id} 时数据库错误：{db_error}")
            raise
    except Exception as e:
        logger.error(f"获取用户 {user_id} 时出错：{e}")
        logger.error(traceback.format_exc())

        # 清理操作（但不递归）
        try:
            async with await _safe_db_connect() as db:
                async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';") as cursor:
                    if await cursor.fetchone():
                        async with db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)) as cursor:
                            if await cursor.fetchone():
                                await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                                await db.commit()
                                logger.info(f"已删除损坏的用户数据: {user_id}")
        except Exception as cleanup_error:
            logger.error(f"清理损坏数据失败: {cleanup_error}")

        # 清除缓存
        if redis_client:
            try:
                redis_client.delete(f"user:{user_id}")
            except Exception:
                pass

        # 仅在递归深度允许时才递归
        if _recursion_depth < MAX_RECURSION_DEPTH - 1:
            return await get_user(user_id, nickname, _recursion_depth + 1)
        else:
            logger.error("递归深度超限，返回默认用户对象")
            return User(**default_user)


@database_retry()
async def get_signed_days(user_id):
    """获取用户签到记录"""
    # 确保数据库已初始化
    await ensure_db_initialized()

    async with await _safe_db_connect() as db:
        async with db.execute("SELECT signed_days FROM users WHERE user_id = ?", (user_id,)) as cursor:
            result = await cursor.fetchone()
            if result and result[0]:
                try:
                    return json.loads(result[0])
                except json.JSONDecodeError:
                    return []
            return []


@database_retry()
async def record_sign_in(user_id, nickname="DefaultUser", card="00000"):
    """记录用户签到"""
    # 确保数据库已初始化
    await ensure_db_initialized()

    async with await _safe_db_connect() as db:
        async with db.execute("SELECT signed_days FROM users WHERE user_id = ?", (user_id,)) as cursor:
            result = await cursor.fetchone()

            if not result:
                # 用户不存在，创建新用户
                registration_date = datetime.date.today().isoformat()
                await db.execute("""
                INSERT INTO users (user_id, nickname, card, signed_days, registration_date)
                VALUES (?, ?, ?, ?, ?)
                """, (user_id, nickname, card, "[]", registration_date))
                await db.commit()
                logger.info(f"用户 {user_id} 不存在，已创建新用户。")
                signed_days = []
            else:
                try:
                    signed_days = json.loads(result[0]) if result[0] else []
                except json.JSONDecodeError:
                    signed_days = []

        today = datetime.date.today().isoformat()
        if today not in signed_days:
            signed_days.append(today)
            signed_days.sort()
            await db.execute("UPDATE users SET signed_days = ? WHERE user_id = ?",
                             (json.dumps(signed_days), user_id))
            await db.commit()

            # 清除缓存
            if redis_client:
                try:
                    redis_client.delete(f"user:{user_id}")
                except Exception as e:
                    logger.debug(f"清除缓存失败: {e}")

            return f"用户 {user_id} 签到成功，日期：{today}"
        else:
            return f"用户 {user_id} 今天已经签到过了！"


@database_retry()
async def get_users_with_permission_above(permission_value):
    """查找权限高于指定值的用户"""
    # 确保数据库已初始化
    await ensure_db_initialized()

    async with await _safe_db_connect() as db:
        async with db.execute("SELECT user_id FROM users WHERE permission > ?", (permission_value,)) as cursor:
            result = await cursor.fetchall()
            return [user[0] for user in result]


def get_db_stats():
    """获取数据库统计信息"""
    return {
        "db_initialized": _db_initialized,
        "redis_connected": redis_client is not None,
        "db_path": dbpath
    }