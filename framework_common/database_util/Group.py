"""
群组消息管理器 - 数据库持久化版本
支持 SQLite 持久化存储 + 内存缓存
"""
import json
import asyncio
import os
import time
import threading
from collections import defaultdict, deque
from threading import RLock
import aiosqlite
from developTools.utils.logger import get_logger
from run.ai_llm.service.aiReplyHandler.gemini import gemini_prompt_elements_construct
from run.ai_llm.service.aiReplyHandler.openai import prompt_elements_construct, prompt_elements_construct_old_version

logger = get_logger()

# 数据库路径
DB_PATH = "data/dataBase/group_messages.db"

# 全局数据库初始化状态
_db_initialized: bool = False


async def ensure_db_initialized():
    """确保数据库已初始化"""
    global _db_initialized
    if not _db_initialized:
        await initialize_db()
        _db_initialized = True


async def initialize_db():
    """初始化群消息数据库"""
    try:
        db_dir = os.path.dirname(DB_PATH)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            await db.execute("PRAGMA cache_size=10000;")
            await db.execute("PRAGMA temp_store=MEMORY;")
            await db.execute("PRAGMA busy_timeout=5000;")

            # 创建群消息表
            await db.execute("""
            CREATE TABLE IF NOT EXISTS group_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                user_id INTEGER,
                user_name TEXT,
                message TEXT,
                timestamp TEXT,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            )
            """)

            # 创建索引
            await db.execute("CREATE INDEX IF NOT EXISTS idx_group_id ON group_messages(group_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_group_created ON group_messages(group_id, created_at);")

            await db.commit()
            #logger.info("群消息数据库初始化完成")

    except Exception as e:
        logger.error(f"群消息数据库初始化失败: {e}")
        os.remove(DB_PATH)
        raise


class GroupMessageManager:
    """群组消息管理器"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return

        # 配置参数（默认值，可通过 set_max_messages 修改）
        self.MAX_MESSAGES = 100
        self.MAX_GROUPS = 1000
        self.MAX_CACHE_ITEMS = 500

        # 批量处理配置
        self.BATCH_SIZE = 10
        self.CACHE_CLEANUP_THRESHOLD = 20

        # 内存缓存（用于快速访问）
        self._lock = RLock()
        self._messages_cache = defaultdict(lambda: deque(maxlen=self.MAX_MESSAGES))
        self._group_order = deque(maxlen=self.MAX_GROUPS)
        self._group_order_set = set()

        # 预处理缓存
        self._processed_cache = {}
        self._cache_order = deque(maxlen=self.MAX_CACHE_ITEMS)

        # 延迟清理相关
        self._dirty_groups = set()
        self._pending_messages = []  # 待写入数据库的消息
        self._batch_lock = threading.Lock()

        # 后台任务
        self._running = True
        self._db_initialized = False

        self._initialized = True

        # 启动后台任务
        self._start_background_tasks()

    def set_max_messages(self, max_messages: int):
        """设置每个群的最大消息数量"""
        with self._lock:
            self.MAX_MESSAGES = max_messages
            old_messages = dict(self._messages_cache)
            self._messages_cache = defaultdict(lambda: deque(maxlen=self.MAX_MESSAGES))
            for group_id, msgs in old_messages.items():
                new_deque = deque(maxlen=self.MAX_MESSAGES)
                new_deque.extend(msgs)
                self._messages_cache[group_id] = new_deque
            logger.info(f"群消息保留数量已更新为 {max_messages}")

    def _start_background_tasks(self):
        """启动后台任务"""
        def background_worker():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            while self._running:
                try:
                    # 批量写入待处理的消息到数据库
                    loop.run_until_complete(self._flush_pending_messages())
                    # 清理缓存
                    self._batch_cleanup_cache()
                    time.sleep(0.5)  # 500ms处理一次
                except Exception as e:
                    logger.error(f"后台任务错误: {e}")
                    time.sleep(1)
            
            loop.close()

        self._worker_thread = threading.Thread(target=background_worker, daemon=True)
        self._worker_thread.start()

    async def _flush_pending_messages(self):
        """将待处理消息写入数据库"""
        if not self._pending_messages:
            return

        with self._batch_lock:
            messages_to_write = self._pending_messages.copy()
            self._pending_messages.clear()

        if not messages_to_write:
            return

        try:
            await ensure_db_initialized()
            async with aiosqlite.connect(DB_PATH) as db:
                await db.executemany(
                    """INSERT INTO group_messages (group_id, user_id, user_name, message, timestamp)
                       VALUES (?, ?, ?, ?, ?)""",
                    messages_to_write
                )
                await db.commit()
                logger.debug(f"批量写入 {len(messages_to_write)} 条消息到数据库")
        except Exception as e:
            logger.error(f"写入数据库失败: {e}")
            # 失败的消息放回队列
            with self._batch_lock:
                self._pending_messages.extend(messages_to_write)

    def _batch_cleanup_cache(self):
        """批量清理缓存"""
        if not self._dirty_groups:
            return

        with self._lock:
            groups_to_clean = list(self._dirty_groups)[:self.CACHE_CLEANUP_THRESHOLD]
            if not groups_to_clean:
                return

            keys_to_remove = []
            for group_id in groups_to_clean:
                keys_to_remove.extend(
                    k for k in self._processed_cache.keys()
                    if k[0] == group_id
                )
                self._dirty_groups.discard(group_id)

            for key in keys_to_remove:
                self._processed_cache.pop(key, None)
                try:
                    self._cache_order.remove(key)
                except ValueError:
                    pass

    def _update_group_lru_fast(self, group_id: int):
        """快速更新群组LRU"""
        if group_id not in self._group_order_set:
            self._group_order.append(group_id)
            self._group_order_set.add(group_id)

            if len(self._group_order_set) > self.MAX_GROUPS:
                if self._group_order:
                    oldest = self._group_order.popleft()
                    self._group_order_set.discard(oldest)

    def _build_context_info(self, messages):
        """构建上下文信息"""
        context_info = {
            'participants': set(),
            'message_count': len(messages),
            'activities': []
        }

        for msg in messages[:10]:
            user_name = msg.get('user_name', '未知用户')
            user_id = msg.get('user_id', '')

            if len(context_info['participants']) < 10:
                context_info['participants'].add(f"{user_name}(ID:{user_id})")

            message_content = msg.get("message", [])
            for msg_part in message_content:
                if isinstance(msg_part, dict) and msg_part.get('type') == 'text':
                    text = msg_part.get('text', '').strip()
                    if '?' in text or '？' in text:
                        context_info['activities'].append('提问')
                        break

        return context_info

    async def _process_single_message(self, raw_message, index, context_info, standard, bot, event, include_images=True):
        """处理单条消息
        
        Args:
            include_images: 是否包含图片，False时会过滤掉图片消息
        """
        user_name = raw_message.get('user_name', '未知用户')
        user_id = raw_message.get('user_id', '')
        timestamp = raw_message.get('timestamp', time.strftime('%Y-%m-%d %H:%M:%S'))

        position_desc = "最新" if index == 0 else f"第{index + 1}条"
        context_prompt = (
            f"【群聊上下文-{position_desc}消息】"
            f"发送者：{user_name}(ID:{user_id}) | "
            f"时间：{timestamp}"
        )

        message_copy = json.loads(json.dumps(raw_message))
        
        # 如果不包含图片，过滤掉图片消息
        if not include_images:
            filtered_message = []
            for item in message_copy["message"]:
                if isinstance(item, dict):
                    # 跳过图片和表情
                    if "image" in item or "mface" in item:
                        # 添加占位文本表示有图片
                        filtered_message.append({"text": "[图片]"})
                    else:
                        filtered_message.append(item)
                else:
                    filtered_message.append(item)
            message_copy["message"] = filtered_message
        
        message_copy["message"].insert(0, {
            "text": f"{context_prompt}\n这是群聊历史消息，用于理解当前对话上下文。"
        })

        if standard == "gemini":
            return await gemini_prompt_elements_construct(message_copy["message"], bot=bot, event=event)
        elif standard == "new_openai":
            return await prompt_elements_construct(message_copy["message"], bot=bot, event=event)
        else:
            return await prompt_elements_construct_old_version(message_copy["message"], bot=bot, event=event)

    def _format_final_result(self, processed_list, context_info, standard):
        """格式化最终结果"""
        participants_list = list(context_info['participants'])
        activities = list(set(context_info['activities'])) if context_info['activities'] else ['正常聊天']

        group_summary = (
            "================== 群聊上下文 开始 ==================\n"
            f"【群聊概况】参与人数：{len(participants_list)}人 | "
            f"消息总数：{context_info['message_count']}条 | "
            f"主要参与者：{', '.join(participants_list[:3])} | "
            f"活动类型：{', '.join(activities[:2])}"
        )
        
        context_end = "================== 群聊上下文 结束 =================="

        if standard == "gemini":
            all_parts = []
            for entry in processed_list:
                if entry.get('role') == 'user':
                    all_parts.extend(entry.get('parts', []))

            summary_part = {"text": f"{group_summary}"}
            end_part = {"text": f"{context_end}\n以上是群聊历史消息上下文，仅供参考，请根据之后的用户消息进行回复。"}
            all_parts.insert(0, summary_part)
            all_parts.append(end_part)

            return [
                {"role": "user", "parts": all_parts},
                {"role": "model", "parts": [{"text": "好的，我已了解群聊上下文，会根据之后的用户消息进行回复。"}]}
            ]
        else:
            all_parts = []
            for entry in processed_list:
                if entry.get('role') == 'user' and isinstance(entry.get('content'), list):
                    all_parts.extend(entry['content'])

            if all_parts:
                summary_part = {"type": "text", "text": f"{group_summary}"}
                end_part = {"type": "text", "text": f"{context_end}\n以上是群聊历史消息上下文，仅供参考，请根据之后的用户消息进行回复。"}
                all_parts.insert(0, summary_part)
                all_parts.append(end_part)
                return [
                    {"role": "user", "content": all_parts},
                    {"role": "assistant", "content": "好的，我已了解群聊上下文，会根据之后的用户消息进行回复。"}
                ]
            else:
                return [
                    {"role": "user", "content": f"{group_summary}\n{context_end}\n以上是群聊历史消息上下文。"},
                    {"role": "assistant", "content": "好的，我已了解群聊上下文，会根据之后的用户消息进行回复。"}
                ]


    def add_to_group_fast(self, group_id: int, message):
        """快速添加消息（写入内存缓存 + 异步写入数据库）"""
        with self._lock:
            # 添加到内存缓存
            self._messages_cache[group_id].append(message)
            self._update_group_lru_fast(group_id)
            self._dirty_groups.add(group_id)

        # 准备写入数据库的数据
        user_id = message.get('user_id', 0)
        user_name = message.get('user_name', '未知用户')
        msg_content = json.dumps(message.get('message', []), ensure_ascii=False)
        timestamp = message.get('timestamp', time.strftime('%Y-%m-%d %H:%M:%S'))

        with self._batch_lock:
            self._pending_messages.append((group_id, user_id, user_name, msg_content, timestamp))

    def add_to_group_sync(self, group_id: int, message):
        """同步添加消息"""
        self.add_to_group_fast(group_id, message)

    async def add_to_group(self, group_id: int, message, delete_after: int = 50):
        """添加消息到群组"""
        self.add_to_group_fast(group_id, message)
        logger.debug(f"消息已添加到群组 {group_id}")

    async def get_group_messages(self, group_id: int, limit: int = 50):
        """获取群组消息（优先从内存，不足时从数据库补充并加载到缓存）"""
        messages = []
        
        # 从内存缓存获取
        with self._lock:
            if group_id in self._messages_cache:
                messages = list(self._messages_cache[group_id])

        # 如果内存中的消息不足，从数据库补充
        if len(messages) < limit:
            try:
                await ensure_db_initialized()
                async with aiosqlite.connect(DB_PATH) as db:
                    async with db.execute(
                        """SELECT user_id, user_name, message, timestamp 
                           FROM group_messages 
                           WHERE group_id = ? 
                           ORDER BY created_at DESC 
                           LIMIT ?""",
                        (group_id, limit)
                    ) as cursor:
                        rows = await cursor.fetchall()
                        
                        # 转换数据库记录为消息格式
                        db_messages = []
                        for row in rows:
                            try:
                                msg_content = json.loads(row[2]) if row[2] else []
                                db_messages.append({
                                    'user_id': row[0],
                                    'user_name': row[1],
                                    'message': msg_content,
                                    'timestamp': row[3]
                                })
                            except:
                                continue
                        
                        # 如果数据库有消息且内存缓存为空，将数据库消息加载到内存缓存
                        if db_messages and len(messages) == 0:
                            with self._lock:
                                # 按时间顺序加载（旧的在前）
                                for msg in reversed(db_messages):
                                    self._messages_cache[group_id].append(msg)
                                self._update_group_lru_fast(group_id)
                            logger.debug(f"从数据库加载 {len(db_messages)} 条消息到群 {group_id} 的内存缓存")
                        
                        # 使用数据库消息
                        if db_messages:
                            messages = list(reversed(db_messages))[:limit]
            except Exception as e:
                logger.error(f"从数据库读取消息失败: {e}")

        # 返回消息列表
        messages = list(reversed(messages))[:limit]
        return messages

    async def get_group_messages_raw(self, group_id: int, limit: int = 50):
        """获取群组原始消息对象列表"""
        return await self.get_group_messages(group_id, limit)

    async def _preprocess_group_messages(self, group_id: int, standard: str = "gemini",
                                         data_length: int = 20, bot=None, event=None, include_images=True):
        """预处理群组消息为prompt格式
        
        Args:
            include_images: 是否包含图片，False时会跳过图片消息内容
        """
        try:
            messages = await self.get_group_messages(group_id, data_length)

            if not messages:
                logger.debug(f"群组 {group_id} 消息为空")
                return []

            actual_length = min(data_length, len(messages))
            messages = messages[-actual_length:] if len(messages) > actual_length else messages
            messages = list(reversed(messages))

            context_info = self._build_context_info(messages)

            processed_list = []
            for i, raw_message in enumerate(messages):
                try:
                    processed_msg = await self._process_single_message(
                        raw_message, i, context_info, standard, bot, event, include_images
                    )
                    if processed_msg:
                        processed_list.append(processed_msg)
                except Exception as e:
                    logger.error(f"处理单条消息失败: {e}")
                    continue

            final_result = self._format_final_result(processed_list, context_info, standard)
            return final_result

        except Exception as e:
            logger.error(f"预处理失败: {e}")
            return []

    async def get_last_20_and_convert_to_prompt(self, group_id: int, data_length=20,
                                                prompt_standard="gemini", bot=None, event=None, include_images=True):
        """获取转换后的prompt（缓存优先）
        
        Args:
            include_images: 是否包含图片，False时会跳过图片消息内容
        """
        cache_key = (group_id, prompt_standard, data_length, include_images)

        with self._lock:
            if cache_key in self._processed_cache:
                try:
                    self._cache_order.remove(cache_key)
                    self._cache_order.append(cache_key)
                except ValueError:
                    self._cache_order.append(cache_key)
                return self._processed_cache[cache_key]

        result = await self._preprocess_group_messages(group_id, prompt_standard, data_length, bot, event, include_images)

        if result:
            with self._lock:
                if len(self._processed_cache) >= self.MAX_CACHE_ITEMS:
                    if self._cache_order:
                        oldest_key = self._cache_order.popleft()
                        self._processed_cache.pop(oldest_key, None)

                self._processed_cache[cache_key] = result
                self._cache_order.append(cache_key)

        return result

    async def clear_group_messages(self, group_id: int):
        """清除群组消息（内存 + 数据库）"""
        # 清除内存缓存
        with self._lock:
            if group_id in self._messages_cache:
                self._messages_cache[group_id].clear()

            self._group_order_set.discard(group_id)

            expired_keys = [k for k in self._processed_cache.keys() if k[0] == group_id]
            for k in expired_keys:
                self._processed_cache.pop(k, None)
                try:
                    self._cache_order.remove(k)
                except ValueError:
                    pass

            self._dirty_groups.discard(group_id)

        # 清除数据库记录
        try:
            await ensure_db_initialized()
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DELETE FROM group_messages WHERE group_id = ?", (group_id,))
                await db.commit()
        except Exception as e:
            logger.error(f"清除数据库消息失败: {e}")

        logger.info(f"已清除 group_id={group_id} 的所有消息")

    async def clear_all_group_cache(self):
        """清除所有数据（内存 + 数据库）"""
        with self._lock:
            self._messages_cache.clear()
            self._group_order.clear()
            self._group_order_set.clear()
            self._processed_cache.clear()
            self._cache_order.clear()
            self._dirty_groups.clear()

        # 清除数据库
        try:
            await ensure_db_initialized()
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DELETE FROM group_messages")
                await db.commit()
        except Exception as e:
            logger.error(f"清除数据库失败: {e}")

        logger.info("所有群组数据已清除")
        return True

    async def cleanup_old_messages(self):
        """清理超出限制的旧消息"""
        try:
            await ensure_db_initialized()
            async with aiosqlite.connect(DB_PATH) as db:
                # 获取所有群组
                async with db.execute("SELECT DISTINCT group_id FROM group_messages") as cursor:
                    groups = await cursor.fetchall()

                for (group_id,) in groups:
                    # 保留每个群最新的 MAX_MESSAGES 条消息
                    await db.execute("""
                        DELETE FROM group_messages 
                        WHERE group_id = ? AND id NOT IN (
                            SELECT id FROM group_messages 
                            WHERE group_id = ? 
                            ORDER BY created_at DESC 
                            LIMIT ?
                        )
                    """, (group_id, group_id, self.MAX_MESSAGES))

                await db.commit()
                logger.debug("已清理超出限制的旧消息")
        except Exception as e:
            logger.error(f"清理旧消息失败: {e}")

    def get_cache_stats(self):
        """获取统计信息"""
        with self._lock:
            total_messages = sum(len(msgs) for msgs in self._messages_cache.values())
            return {
                "total_groups": len(self._messages_cache),
                "total_messages_in_cache": total_messages,
                "cached_prompts": len(self._processed_cache),
                "dirty_groups": len(self._dirty_groups),
                "pending_writes": len(self._pending_messages),
                "max_messages_per_group": self.MAX_MESSAGES
            }

    def shutdown(self):
        """关闭管理器"""
        self._running = False
        # 同步写入剩余消息
        if self._pending_messages:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._flush_pending_messages())
            loop.close()
        if hasattr(self, '_worker_thread'):
            self._worker_thread.join(timeout=2.0)


# ======================= 全局单例实例 =======================
_manager = None


def get_manager():
    """获取单例管理器"""
    global _manager
    if _manager is None:
        _manager = GroupMessageManager()
    return _manager


# ======================= 外部接口函数（保持兼容） =======================
async def add_to_group(group_id: int, message, delete_after: int = 50):
    """向群组添加消息"""
    manager = get_manager()
    await manager.add_to_group(group_id, message, delete_after)


async def get_group_messages(group_id: int, limit: int = 50):
    """获取群组消息列表"""
    manager = get_manager()
    return await manager.get_group_messages(group_id, limit)


async def get_last_20_and_convert_to_prompt(group_id: int, data_length=20, prompt_standard="gemini",
                                            bot=None, event=None, include_images=True):
    """获取转换后的prompt
    
    Args:
        include_images: 是否包含图片，False时会跳过图片消息内容
    """
    manager = get_manager()
    return await manager.get_last_20_and_convert_to_prompt(group_id, data_length, prompt_standard, bot, event, include_images)


async def clear_group_messages(group_id: int):
    """清除群组消息"""
    manager = get_manager()
    await manager.clear_group_messages(group_id)


async def clear_all_group_cache():
    """清除所有缓存"""
    manager = get_manager()
    return await manager.clear_all_group_cache()


def get_cache_stats():
    """获取统计信息"""
    manager = get_manager()
    return manager.get_cache_stats()
