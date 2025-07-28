import aiosqlite
import json
import asyncio
import redis
import time
import os
from collections import defaultdict
from threading import Lock
import hashlib
from developTools.utils.logger import get_logger
from run.ai_llm.service.aiReplyHandler.gemini import gemini_prompt_elements_construct
from run.ai_llm.service.aiReplyHandler.openai import prompt_elements_construct, prompt_elements_construct_old_version

DB_NAME = "data/dataBase/group_messages.db"


def is_running_in_docker():
    return os.path.exists("/.dockerenv") or os.environ.get("IN_DOCKER") == "1"


if is_running_in_docker():
    REDIS_URL = "redis://redis:6379/0"
else:
    REDIS_URL = "redis://localhost"

# 优化后的缓存配置
REDIS_CACHE_TTL = 300  # 增加到5分钟
MEMORY_CACHE_TTL = 60  # 内存缓存1分钟
BATCH_SIZE = 10  # 批量写入大小

logger = get_logger()

redis_client = None

# 内存缓存和批量写入
memory_cache = {}
cache_timestamps = {}
pending_writes = defaultdict(list)
write_lock = Lock()
last_batch_write = time.time()

import subprocess
import platform
import zipfile

REDIS_EXECUTABLE = "redis-server.exe"
REDIS_ZIP_PATH = os.path.join("data", "Redis-x64-5.0.14.1.zip")
REDIS_FOLDER = os.path.join("data", "redis_extracted")


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
        # 优化Redis连接配置
        redis_client = redis.StrictRedis.from_url(
            REDIS_URL,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30
        )
        redis_client.ping()
        logger.info("✅ Redis 连接成功（数据库 db group）")
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


init_redis()


# ======================= 优化的缓存管理 =======================
def get_cache_key(group_id: int, prompt_standard: str, data_length: int = 20):
    """生成缓存键"""
    return f"group:{group_id}:{prompt_standard}:{data_length}"


def get_memory_cache(key: str):
    """获取内存缓存"""
    if key in memory_cache:
        timestamp = cache_timestamps.get(key, 0)
        if time.time() - timestamp < MEMORY_CACHE_TTL:
            return memory_cache[key]
        else:
            # 过期清理
            memory_cache.pop(key, None)
            cache_timestamps.pop(key, None)
    return None


def set_memory_cache(key: str, value):
    """设置内存缓存"""
    memory_cache[key] = value
    cache_timestamps[key] = time.time()

    # 定期清理过期缓存
    if len(memory_cache) > 1000:
        current_time = time.time()
        expired_keys = [
            k for k, t in cache_timestamps.items()
            if current_time - t > MEMORY_CACHE_TTL
        ]
        for k in expired_keys:
            memory_cache.pop(k, None)
            cache_timestamps.pop(k, None)


def get_redis_cache(key: str):
    """安全获取Redis缓存"""
    if not redis_client:
        return None
    try:
        cached = redis_client.get(key)
        return json.loads(cached) if cached else None
    except Exception as e:
        logger.debug(f"Redis读取失败: {e}")
        return None


def set_redis_cache(key: str, value, ttl: int = REDIS_CACHE_TTL):
    """安全设置Redis缓存"""
    if not redis_client:
        return
    try:
        redis_client.setex(key, ttl, json.dumps(value))
    except Exception as e:
        logger.debug(f"Redis写入失败: {e}")


def clear_redis_cache_pattern(pattern: str):
    """清理Redis缓存模式"""
    if not redis_client:
        return
    try:
        keys = redis_client.keys(pattern)
        if keys:
            redis_client.delete(*keys)
    except Exception as e:
        logger.debug(f"Redis清理失败: {e}")


# ======================= 优化的数据库操作 =======================
MAX_RETRIES = 3
INITIAL_DELAY = 0.1
CONNECTION_POOL = {}


async def get_db_connection():
    """获取数据库连接（连接池）"""
    thread_id = id(asyncio.current_task())
    if thread_id not in CONNECTION_POOL:
        db = await aiosqlite.connect(DB_NAME)
        # 优化数据库设置
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute("PRAGMA cache_size=10000;")
        await db.execute("PRAGMA temp_store=MEMORY;")
        await db.execute("PRAGMA busy_timeout=5000;")
        CONNECTION_POOL[thread_id] = db
    return CONNECTION_POOL[thread_id]


async def execute_with_retry(db, query, params=None):
    """优化的带重试机制的数据库操作"""
    for attempt in range(MAX_RETRIES):
        try:
            if params:
                cursor = await db.execute(query, params)
            else:
                cursor = await db.execute(query)
            return cursor
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) or "busy" in str(e):
                delay = INITIAL_DELAY * (2 ** attempt) + (attempt * 0.05)  # 更短的退避时间
                logger.debug(f"Database busy, retrying in {delay:.3f}s (attempt {attempt + 1})")
                await asyncio.sleep(delay)
            else:
                raise
        except Exception as e:
            logger.error(f"Database error: {e}")
            raise
    raise Exception(f"Database still busy after {MAX_RETRIES} attempts")


# ======================= 批量写入优化 =======================
async def batch_write_pending():
    """批量写入待处理的数据"""
    global last_batch_write
    current_time = time.time()

    if current_time - last_batch_write < 1.0:  # 1秒内不重复写入
        return

    with write_lock:
        if not pending_writes:
            return

        batch_data = dict(pending_writes)
        pending_writes.clear()
        last_batch_write = current_time

    if not batch_data:
        return

    try:
        db = await get_db_connection()
        for group_id, messages in batch_data.items():
            if messages:
                # 批量插入
                insert_data = [
                    (group_id, json.dumps(msg), None, None, None)
                    for msg in messages
                ]
                await db.executemany(
                    "INSERT INTO group_messages (group_id, message, processed_message, new_openai_processed_message, old_openai_processed_message) VALUES (?, ?, ?, ?, ?)",
                    insert_data
                )

                # 清理旧数据
                cursor = await db.execute("SELECT COUNT(*) FROM group_messages WHERE group_id = ?", (group_id,))
                count = (await cursor.fetchone())[0]

                if count > 50:
                    excess = count - 50
                    await execute_with_retry(
                        db,
                        "DELETE FROM group_messages WHERE id IN (SELECT id FROM group_messages WHERE group_id = ? ORDER BY timestamp ASC LIMIT ?)",
                        (group_id, excess)
                    )

        await db.commit()
        logger.debug(f"批量写入完成: {len(batch_data)} 个群组")

        # 清理相关缓存
        for group_id in batch_data.keys():
            clear_redis_cache_pattern(f"group:{group_id}:*")
            # 清理内存缓存
            expired_keys = [k for k in memory_cache.keys() if f"group:{group_id}:" in k]
            for k in expired_keys:
                memory_cache.pop(k, None)
                cache_timestamps.pop(k, None)

    except Exception as e:
        logger.error(f"批量写入失败: {e}")


# ======================= 定期批量写入任务管理 =======================
from typing import Optional

# 全局变量存储任务和初始化状态
_periodic_task: Optional[asyncio.Task] = None
_db_initialized: bool = False


# 定期批量写入任务
async def periodic_batch_write():
    """定期批量写入任务"""
    while True:
        try:
            await asyncio.sleep(2)  # 每2秒检查一次
            await batch_write_pending()
        except Exception as e:
            logger.error(f"定期批量写入错误: {e}")


def start_periodic_batch_write():
    """启动定期批量写入任务"""
    global _periodic_task
    try:
        loop = asyncio.get_running_loop()
        if _periodic_task is None or _periodic_task.done():
            _periodic_task = loop.create_task(periodic_batch_write())
            logger.info("✅ 定期批量写入任务已启动")
    except RuntimeError:
        # 没有运行的事件循环，稍后再启动
        logger.debug("暂时无法启动定期任务，等待事件循环启动")


def stop_periodic_batch_write():
    """停止定期批量写入任务"""
    global _periodic_task
    if _periodic_task and not _periodic_task.done():
        _periodic_task.cancel()
        logger.info("🛑 定期批量写入任务已停止")


def ensure_periodic_task():
    """确保定期任务正在运行"""
    global _periodic_task
    try:
        loop = asyncio.get_running_loop()
        if _periodic_task is None or _periodic_task.done():
            _periodic_task = loop.create_task(periodic_batch_write())
            logger.debug("✅ 定期批量写入任务已启动")
    except RuntimeError:
        # 没有事件循环，忽略
        pass


async def ensure_db_initialized():
    """确保数据库已初始化"""
    global _db_initialized
    if not _db_initialized:
        await init_db()
        _db_initialized = True


# ======================= 初始化 =======================
async def init_db():
    """初始化数据库，检查并添加必要的字段"""
    db = await get_db_connection()
    try:
        await execute_with_retry(db, """
            CREATE TABLE IF NOT EXISTS group_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                processed_message TEXT,
                new_openai_processed_message TEXT,
                old_openai_processed_message TEXT
            )
        """)

        # 创建索引优化查询
        await db.execute("CREATE INDEX IF NOT EXISTS idx_group_timestamp ON group_messages(group_id, timestamp);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_group_id ON group_messages(group_id);")

        await db.commit()
        logger.info("✅ 数据库初始化完成")

        # 启动定期任务
        start_periodic_batch_write()

    except Exception as e:
        logger.warning(f"Error initializing database: {e}")


# ======================= 优化的添加消息 =======================
async def add_to_group(group_id: int, message, delete_after: int = 50):
    """向群组添加消息（优化版：使用批量写入）"""
    init_redis()

    # 确保数据库已初始化
    await ensure_db_initialized()

    # 确保定期任务正在运行
    ensure_periodic_task()

    with write_lock:
        pending_writes[group_id].append(message)

        # 如果积累了足够的消息，立即写入
        if len(pending_writes[group_id]) >= BATCH_SIZE:
            asyncio.create_task(batch_write_pending())


async def get_group_messages(group_id: int, limit: int = 50):
    """获取指定群组的指定数量消息，仅返回文本的列表（优化版）"""
    # 确保数据库已初始化
    await ensure_db_initialized()

    # 先检查内存缓存
    cache_key = f"messages:{group_id}:{limit}"
    cached = get_memory_cache(cache_key)
    if cached:
        return cached

    try:
        query = "SELECT message FROM group_messages WHERE group_id = ? ORDER BY timestamp DESC"
        params = (group_id,)
        if limit is not None:
            query += " LIMIT ?"
            params += (limit,)

        db = await get_db_connection()
        cursor = await execute_with_retry(db, query, params)
        rows = await cursor.fetchall()

        text_list = []
        for row in rows:
            try:
                raw_message = json.loads(row[0])
                if "message" in raw_message and isinstance(raw_message["message"], list):
                    for msg_obj in raw_message["message"]:
                        if isinstance(msg_obj, dict) and "text" in msg_obj and isinstance(msg_obj["text"], str):
                            text_list.append(msg_obj["text"])
            except (json.JSONDecodeError, KeyError):
                pass

        # 缓存结果
        set_memory_cache(cache_key, text_list)
        return text_list

    except Exception as e:
        logger.info(f"Error getting messages for group {group_id}: {e}")
        return []


# ======================= 优化的获取并转换消息 =======================
async def get_last_20_and_convert_to_prompt(group_id: int, data_length=20, prompt_standard="gemini", bot=None,
                                            event=None):
    """获取最近的消息并转换为指定格式的 prompt（优化版）"""
    init_redis()

    # 确保数据库已初始化
    await ensure_db_initialized()

    cache_key = get_cache_key(group_id, prompt_standard, data_length)

    # 三级缓存：内存 -> Redis -> 数据库
    # 1. 检查内存缓存
    cached = get_memory_cache(cache_key)
    if cached:
        return cached

    # 2. 检查Redis缓存
    cached = get_redis_cache(cache_key)
    if cached:
        set_memory_cache(cache_key, cached)
        return cached

    # 映射不同的标准字段
    field_mapping = {
        "gemini": "processed_message",
        "new_openai": "new_openai_processed_message",
        "old_openai": "old_openai_processed_message"
    }

    if prompt_standard not in field_mapping:
        raise ValueError(f"不支持的 prompt_standard: {prompt_standard}")

    selected_field = field_mapping[prompt_standard]

    # 3. 从数据库获取
    try:
        # 先立即写入待处理的消息
        await batch_write_pending()

        db = await get_db_connection()
        cursor = await execute_with_retry(
            db,
            f"SELECT id, message, {selected_field} FROM group_messages WHERE group_id = ? ORDER BY timestamp DESC LIMIT ?",
            (group_id, data_length)
        )
        rows = await cursor.fetchall()

        final_list = []
        updates_needed = []  # 收集需要更新的数据

        for row in rows:
            message_id, raw_message, processed_message = row
            raw_message = json.loads(raw_message)

            # 如果已经处理过，使用缓存的消息
            if processed_message:
                final_list.append(json.loads(processed_message))
            else:
                raw_message["message"].insert(0, {
                    "text": f"本条消息消息发送者为 {raw_message['user_name']} id为{raw_message['user_id']} 这是参考消息，当我再次向你提问时，请正常回复我。"
                })

                if prompt_standard == "gemini":
                    processed = await gemini_prompt_elements_construct(raw_message["message"], bot=bot, event=event)
                    final_list.append(processed)
                elif prompt_standard == "new_openai":
                    processed = await prompt_elements_construct(raw_message["message"], bot=bot, event=event)
                    final_list.append(processed)
                    final_list.append(
                        {"role": "assistant", "content": [{"type": "text", "text": "(群聊背景消息已记录)"}]})
                else:
                    processed = await prompt_elements_construct_old_version(raw_message["message"], bot=bot,
                                                                            event=event)
                    final_list.append(processed)
                    final_list.append({"role": "assistant", "content": "(群聊背景消息已记录)"})

                # 收集更新数据
                updates_needed.append((json.dumps(processed), message_id, selected_field))

        # 批量更新数据库
        if updates_needed:
            for processed_json, message_id, field in updates_needed:
                await execute_with_retry(
                    db,
                    f"UPDATE group_messages SET {field} = ? WHERE id = ?",
                    (processed_json, message_id)
                )
            await db.commit()

        # 处理最终格式化的消息
        fl = []
        if prompt_standard == "gemini":
            all_parts = [part for entry in final_list if entry['role'] == 'user' for part in entry['parts']]
            fl.append({"role": "user", "parts": all_parts})
            fl.append({"role": "model", "parts": {"text": "嗯嗯，我记住了"}})
        else:
            all_parts = []
            all_parts_str = ""
            for entry in final_list:
                if entry['role'] == 'user':
                    if isinstance(entry['content'], str):
                        all_parts_str += entry['content'] + "\n"
                    else:
                        for part in entry['content']:
                            all_parts.append(part)
            fl.append({"role": "user", "content": all_parts if all_parts else all_parts_str})
            fl.append({"role": "assistant", "content": "嗯嗯我记住了"})

        # 设置三级缓存
        set_memory_cache(cache_key, fl)
        set_redis_cache(cache_key, fl)

        return fl

    except Exception as e:
        logger.info(f"Error getting last 20 and converting to prompt for group {group_id}: {e}")
        return []


# ======================= 优化的清除消息 =======================
async def clear_group_messages(group_id: int):
    """清除指定群组的所有消息（优化版）"""
    init_redis()

    # 确保数据库已初始化
    await ensure_db_initialized()

    try:
        # 先清理待写入的数据
        with write_lock:
            pending_writes.pop(group_id, None)

        db = await get_db_connection()
        await execute_with_retry(
            db,
            "DELETE FROM group_messages WHERE group_id = ?",
            (group_id,)
        )
        await db.commit()
        logger.info(f"✅ 已清除 group_id={group_id} 的所有数据")

        # 清除所有缓存
        clear_redis_cache_pattern(f"group:{group_id}:*")

        # 清理内存缓存
        expired_keys = [k for k in memory_cache.keys() if f"group:{group_id}:" in k or f"messages:{group_id}:" in k]
        for k in expired_keys:
            memory_cache.pop(k, None)
            cache_timestamps.pop(k, None)

    except Exception as e:
        logger.error(f"❌ 清理 group_id={group_id} 数据时出错: {e}")


# ======================= 性能监控 =======================
def get_cache_stats():
    """获取缓存统计信息"""
    return {
        "memory_cache_size": len(memory_cache),
        "pending_writes_groups": len(pending_writes),
        "pending_writes_total": sum(len(msgs) for msgs in pending_writes.values()),
        "redis_connected": redis_client is not None,
        "db_initialized": _db_initialized,
        "periodic_task_running": _periodic_task is not None and not _periodic_task.done()
    }