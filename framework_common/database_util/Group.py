import aiosqlite
import json
import asyncio
import time
import os
import threading
import weakref
import gc
from collections import defaultdict, OrderedDict, deque
from threading import Lock
import hashlib
from developTools.utils.logger import get_logger
from framework_common.database_util.RedisCacheManager import create_group_cache_manager
from run.ai_llm.service.aiReplyHandler.gemini import gemini_prompt_elements_construct
from run.ai_llm.service.aiReplyHandler.openai import prompt_elements_construct, prompt_elements_construct_old_version

# 导入Redis缓存管理器


DB_NAME = "data/dataBase/group_messages.db"

# 优化后的缓存配置
REDIS_CACHE_TTL = 250  # 增加到5分钟
MEMORY_CACHE_TTL = 50  # 内存缓存1分钟
BATCH_SIZE = 10  # 批量写入大小

logger = get_logger()

# 使用Redis缓存管理器 (数据库0)
redis_cache = create_group_cache_manager(cache_ttl=REDIS_CACHE_TTL)


# ======================= 修复内存缓存管理 =======================
class LRUMemoryCache:
    """LRU内存缓存，防止无限增长"""

    def __init__(self, max_size=500, ttl=50):
        self.max_size = max_size
        self.ttl = ttl
        self.cache = OrderedDict()
        self.timestamps = {}
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            if key in self.cache:
                if time.time() - self.timestamps[key] < self.ttl:
                    self.cache.move_to_end(key)  # LRU更新
                    return self.cache[key]
                else:
                    # 过期清理
                    del self.cache[key]
                    del self.timestamps[key]
            return None

    def set(self, key, value):
        with self.lock:
            current_time = time.time()

            if key in self.cache:
                self.cache.move_to_end(key)
            else:
                # 如果缓存满了，移除最老的项
                if len(self.cache) >= self.max_size:
                    oldest = next(iter(self.cache))
                    del self.cache[oldest]
                    del self.timestamps[oldest]

            self.cache[key] = value
            self.timestamps[key] = current_time

    def pop(self, key, default=None):
        with self.lock:
            self.timestamps.pop(key, None)
            return self.cache.pop(key, default)

    def keys(self):
        with self.lock:
            return list(self.cache.keys())

    def __len__(self):
        with self.lock:
            return len(self.cache)

    def clear(self):
        with self.lock:
            self.cache.clear()
            self.timestamps.clear()

    def cleanup_expired(self):
        """手动清理过期项"""
        with self.lock:
            current_time = time.time()
            expired_keys = [
                k for k, t in self.timestamps.items()
                if current_time - t > self.ttl
            ]
            for k in expired_keys:
                self.cache.pop(k, None)
                self.timestamps.pop(k, None)
            return len(expired_keys)


# 使用LRU缓存替代原有的字典
memory_cache = LRUMemoryCache(max_size=500, ttl=MEMORY_CACHE_TTL)


# ======================= 修复批量写入数据管理 =======================
class BoundedPendingWrites:
    """有界的待写入数据管理，防止无限累积"""

    def __init__(self, max_per_group=100):
        self.max_per_group = max_per_group
        self.data = defaultdict(lambda: deque(maxlen=max_per_group))
        self.lock = threading.Lock()

    def append(self, group_id, message):
        with self.lock:
            self.data[group_id].append(message)

    def get_and_clear_group(self, group_id):
        with self.lock:
            if group_id in self.data:
                messages = list(self.data[group_id])
                self.data[group_id].clear()
                return messages
            return []

    def clear_all(self):
        with self.lock:
            result = {}
            for group_id, messages in self.data.items():
                if messages:
                    result[group_id] = list(messages)
                    messages.clear()
            return result

    def is_empty(self):
        with self.lock:
            return not any(self.data.values())

    def get_group_size(self, group_id):
        with self.lock:
            return len(self.data.get(group_id, []))

    def __len__(self):
        with self.lock:
            return len(self.data)

    def total_messages(self):
        with self.lock:
            return sum(len(messages) for messages in self.data.values())


pending_writes = BoundedPendingWrites(max_per_group=100)
write_lock = Lock()
last_batch_write = time.time()

# ======================= 修复数据库连接管理 =======================
# 优化后的数据库连接管理
MAX_RETRIES = 3
INITIAL_DELAY = 0.1
_db_connection = None
_connection_lock = threading.Lock()


async def get_db_connection():
    """获取数据库连接（单例模式，修复连接泄漏）"""
    global _db_connection

    if _db_connection is None:
        with _connection_lock:
            if _db_connection is None:
                _db_connection = await aiosqlite.connect(DB_NAME)
                # 优化数据库设置
                await _db_connection.execute("PRAGMA journal_mode=WAL;")
                await _db_connection.execute("PRAGMA synchronous=NORMAL;")
                await _db_connection.execute("PRAGMA cache_size=10000;")
                await _db_connection.execute("PRAGMA temp_store=MEMORY;")
                await _db_connection.execute("PRAGMA busy_timeout=5000;")

    return _db_connection


# 跟踪异步任务，防止任务泄漏
_running_tasks = weakref.WeakSet()


# ======================= 保持原有的缓存管理接口 =======================
def get_cache_key(group_id: int, prompt_standard: str, data_length: int = 20):
    """生成缓存键"""
    return f"group:{group_id}:{prompt_standard}:{data_length}"


def get_memory_cache(key: str):
    """获取内存缓存（保持原有接口）"""
    return memory_cache.get(key)


def set_memory_cache(key: str, value):
    """设置内存缓存（保持原有接口）"""
    memory_cache.set(key, value)


def get_redis_cache(key: str):
    """安全获取Redis缓存 - 使用Redis缓存管理器"""
    return redis_cache.get(key)


def set_redis_cache(key: str, value, ttl: int = REDIS_CACHE_TTL):
    """安全设置Redis缓存 - 使用Redis缓存管理器"""
    redis_cache.set(key, value, ttl)


def clear_redis_cache_pattern(pattern: str):
    """清理Redis缓存模式 - 使用Redis缓存管理器"""
    redis_cache.delete_pattern(pattern)


# ======================= 优化的数据库操作 =======================
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
    """批量写入待处理的数据（修复数据泄漏）"""
    global last_batch_write
    current_time = time.time()

    if current_time - last_batch_write < 1.0:  # 1秒内不重复写入
        return

    # 获取并清空待写入数据
    batch_data = pending_writes.clear_all()
    if not batch_data:
        return

    last_batch_write = current_time

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
        # logger.debug(f"批量写入完成: {len(batch_data)} 个群组")

        # 清理相关缓存 - 使用Redis缓存管理器
        for group_id in batch_data.keys():
            clear_redis_cache_pattern(f"group:{group_id}:*")
            # 清理内存缓存
            expired_keys = [k for k in memory_cache.keys() if f"group:{group_id}:" in k]
            for k in expired_keys:
                memory_cache.pop(k, None)

    except Exception as e:
        logger.error(f"批量写入失败: {e}")
        # 写入失败时，将数据重新放回队列（避免数据丢失）
        for group_id, messages in batch_data.items():
            for msg in messages:
                pending_writes.append(group_id, msg)


# ======================= 定期批量写入任务管理 =======================
from typing import Optional

# 全局变量存储任务和初始化状态
_periodic_task: Optional[asyncio.Task] = None
_db_initialized: bool = False


async def periodic_batch_write():
    """定期批量写入任务"""
    while True:
        try:
            await asyncio.sleep(5)  # 每5秒检查一次
            await batch_write_pending()

            # 定期清理过期缓存
            if time.time() % 60 < 5:  # 大约每分钟清理一次
                memory_cache.cleanup_expired()

        except Exception as e:
            logger.error(f"定期批量写入错误: {e}")


def start_periodic_batch_write():
    """启动定期批量写入任务"""
    global _periodic_task
    try:
        loop = asyncio.get_running_loop()
        if _periodic_task is None or _periodic_task.done():
            _periodic_task = loop.create_task(periodic_batch_write())
            _running_tasks.add(_periodic_task)  # 跟踪任务
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
            _running_tasks.add(_periodic_task)  # 跟踪任务
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
    # 确保数据库已初始化
    await ensure_db_initialized()

    # 确保定期任务正在运行
    ensure_periodic_task()

    pending_writes.append(group_id, message)

    # 如果积累了足够的消息，立即写入
    if pending_writes.get_group_size(group_id) >= BATCH_SIZE:
        # 检查是否已有批量写入任务在运行
        has_running_batch_task = any(
            not task.done() and hasattr(task, '_batch_write')
            for task in _running_tasks
        )

        if not has_running_batch_task:
            task = asyncio.create_task(batch_write_pending())
            task._batch_write = True  # 标记任务类型
            _running_tasks.add(task)


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
    # 确保数据库已初始化
    await ensure_db_initialized()

    cache_key = get_cache_key(group_id, prompt_standard, data_length)

    # 三级缓存：内存 -> Redis -> 数据库
    # 1. 检查内存缓存
    cached = get_memory_cache(cache_key)
    if cached:
        return cached

    # 2. 检查Redis缓存 - 使用Redis缓存管理器
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
            f"SELECT id, message, {selected_field}, timestamp FROM group_messages WHERE group_id = ? ORDER BY timestamp DESC LIMIT ?",
            (group_id, data_length)
        )
        rows = await cursor.fetchall()

        final_list = []
        updates_needed = []  # 收集需要更新的数据

        # 用于构建上下文摘要的信息（限制大小防止内存泄漏）
        MAX_PARTICIPANTS = 20
        MAX_ACTIVITIES = 10

        context_info = {
            'participants': set(),
            'message_count': len(rows),
            'topics': [],
            'activities': []
        }

        for i, row in enumerate(rows):
            message_id, raw_message, processed_message, timestamp = row
            raw_message = json.loads(raw_message)

            # 收集上下文信息（限制大小）
            user_name = raw_message.get('user_name', '未知用户')
            user_id = raw_message.get('user_id', '')

            if len(context_info['participants']) < MAX_PARTICIPANTS:
                context_info['participants'].add(f"{user_name}(ID:{user_id})")

            # 分析消息内容类型
            message_content = raw_message.get("message", [])
            content_types = []
            for msg_part in message_content:
                if msg_part.get('type') == 'text':
                    text = msg_part.get('text', '').strip()
                    if text:
                        # 简单的话题提取（可以根据需要扩展）
                        if '?' in text or '？' in text:
                            if len(context_info['activities']) < MAX_ACTIVITIES:
                                context_info['activities'].append('有人提问')
                        if any(word in text for word in ['图片', '照片', '看看']):
                            if len(context_info['activities']) < MAX_ACTIVITIES:
                                context_info['activities'].append('讨论图片')
                        if any(word in text for word in ['文件', '链接', 'http']):
                            if len(context_info['activities']) < MAX_ACTIVITIES:
                                context_info['activities'].append('分享文件/链接')
                elif msg_part.get('type') == 'image':
                    content_types.append('图片')
                elif msg_part.get('type') == 'file':
                    content_types.append('文件')
                elif msg_part.get('type') == 'audio':
                    content_types.append('语音')
                elif msg_part.get('type') == 'video':
                    content_types.append('视频')

            if content_types and len(context_info['activities']) < MAX_ACTIVITIES:
                context_info['activities'].extend([f"发送了{ct}" for ct in content_types[:3]])  # 限制数量

            # 如果已经处理过，使用缓存的消息
            if processed_message:
                final_list.append(json.loads(processed_message))
            else:
                # 构建更丰富的上下文提示信息
                position_desc = "最新" if i == 0 else f"第{i + 1}条"

                context_prompt = (
                    f"【群聊上下文-{position_desc}消息】"
                    f"发送者：{user_name}(ID:{user_id}) | "
                    f"时间戳：{timestamp} | "
                    f"消息位置：倒数第{i + 1}条"
                )

                raw_message["message"].insert(0, {
                    "text": f"{context_prompt}\n这是群聊历史消息，用于理解当前对话上下文。当我再次向你提问时，请结合这些上下文信息正常回复我。"
                })

                if prompt_standard == "gemini":
                    processed = await gemini_prompt_elements_construct(raw_message["message"], bot=bot, event=event)
                    final_list.append(processed)
                elif prompt_standard == "new_openai":
                    processed = await prompt_elements_construct(raw_message["message"], bot=bot, event=event)
                    final_list.append(processed)
                else:
                    processed = await prompt_elements_construct_old_version(raw_message["message"], bot=bot,
                                                                            event=event)
                    final_list.append(processed)

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

        # 构建群聊概况摘要
        participants_list = list(context_info['participants'])
        activities_summary = list(set(context_info['activities'])) if context_info['activities'] else ['正常聊天']

        group_summary = (
            f"【群聊概况】参与人数：{len(participants_list)}人 | "
            f"消息总数：{context_info['message_count']}条 | "
            f"主要参与者：{', '.join(participants_list[:5])}{'...' if len(participants_list) > 5 else ''} | "
            f"活动类型：{', '.join(activities_summary[:3])}{'...' if len(activities_summary) > 3 else ''}"
        )

        # 处理最终格式化的消息
        fl = []
        if prompt_standard == "gemini":
            all_parts = [part for entry in final_list if entry['role'] == 'user' for part in entry['parts']]

            # 在开头添加群聊概况
            summary_part = {"text": f"{group_summary}\n以上是群聊历史消息上下文，帮助你理解对话背景。"}
            all_parts.insert(0, summary_part)

            fl.append({"role": "user", "parts": all_parts})
            fl.append({"role": "model", "parts": {
                "text": "我已经了解了群聊的上下文背景，包括参与成员、消息历史和主要活动。我会结合这些信息来更好地理解和回应后续的对话。"}})
        else:
            all_parts = []
            all_parts_str = f"{group_summary}\n"

            for entry in final_list:
                if entry['role'] == 'user':
                    if isinstance(entry['content'], str):
                        all_parts_str += entry['content'] + "\n"
                    else:
                        for part in entry['content']:
                            all_parts.append(part)

            if all_parts:
                # 在开头添加概况说明
                summary_part = {"type": "text", "text": f"{group_summary}\n以上是群聊历史消息上下文："}
                all_parts.insert(0, summary_part)
                fl.append({"role": "user", "content": all_parts})
            else:
                fl.append({"role": "user", "content": all_parts_str + "以上是群聊历史消息上下文。"})

            fl.append({"role": "assistant",
                       "content": "我已经了解了群聊的上下文背景，包括参与成员、消息历史和主要活动。我会结合这些信息来更好地理解和回应后续的对话。"})

        # 设置三级缓存 - 使用Redis缓存管理器
        set_memory_cache(cache_key, fl)
        set_redis_cache(cache_key, fl)
        # print(fl)
        return fl

    except Exception as e:
        logger.info(f"Error getting last 20 and converting to prompt for group {group_id}: {e}")
        return []


# ======================= 优化的清除消息 =======================
async def clear_group_messages(group_id: int):
    """清除指定群组的所有消息（优化版）"""
    # 确保数据库已初始化
    await ensure_db_initialized()

    try:
        # 先清理待写入的数据
        pending_writes.get_and_clear_group(group_id)

        db = await get_db_connection()
        await execute_with_retry(
            db,
            "DELETE FROM group_messages WHERE group_id = ?",
            (group_id,)
        )
        await db.commit()
        logger.info(f"✅ 已清除 group_id={group_id} 的所有数据")

        # 清除所有缓存 - 使用Redis缓存管理器
        clear_redis_cache_pattern(f"group:{group_id}:*")

        # 清理内存缓存
        expired_keys = [k for k in memory_cache.keys() if f"group:{group_id}:" in k or f"messages:{group_id}:" in k]
        for k in expired_keys:
            memory_cache.pop(k, None)

    except Exception as e:
        logger.error(f"❌ 清理 group_id={group_id} 数据时出错: {e}")


# ======================= 新增：缓存管理功能 =======================
async def clear_all_group_cache():
    """清除所有群组相关的缓存"""
    try:
        # 清除Redis缓存
        redis_cache.delete_pattern("group:*")
        redis_cache.delete_pattern("messages:*")

        # 清除内存缓存
        memory_cache.clear()

        logger.info("✅ 所有群组缓存已清除")
        return True
    except Exception as e:
        logger.error(f"❌ 清除群组缓存失败: {e}")
        return False


async def get_group_cache_info(group_id: int):
    """获取指定群组的缓存信息"""
    try:
        # 获取Redis中该群组的所有缓存键
        redis_keys = redis_cache.get_keys(f"group:{group_id}:*")
        redis_keys.extend(redis_cache.get_keys(f"messages:{group_id}:*"))

        # 获取内存中该群组的缓存键
        memory_keys = [k for k in memory_cache.keys() if f"group:{group_id}:" in k or f"messages:{group_id}:" in k]

        # 获取待写入的消息数量
        pending_count = len(pending_writes.get(group_id, []))

        return {
            "group_id": group_id,
            "redis_cache_keys": len(redis_keys),
            "memory_cache_keys": len(memory_keys),
            "pending_writes": pending_count,
            "redis_connected": redis_cache.is_connected()
        }
    except Exception as e:
        logger.error(f"❌ 获取群组 {group_id} 缓存信息失败: {e}")
        return {
            "group_id": group_id,
            "error": str(e)
        }


# ======================= 性能监控 =======================
def get_cache_stats():
    """获取缓存统计信息"""
    redis_info = redis_cache.get_info()

    return {
        "memory_cache_size": len(memory_cache),
        "pending_writes_groups": len(pending_writes),
        "pending_writes_total": sum(len(msgs) for msgs in pending_writes.values()),
        "redis_connected": redis_cache.is_connected(),
        "redis_info": redis_info,
        "db_initialized": _db_initialized,
        "periodic_task_running": _periodic_task is not None and not _periodic_task.done()
    }

