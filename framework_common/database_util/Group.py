import json
import asyncio
import time
import threading
from collections import defaultdict, deque
from threading import RLock
import weakref
from developTools.utils.logger import get_logger
from run.ai_llm.service.aiReplyHandler.gemini import gemini_prompt_elements_construct
from run.ai_llm.service.aiReplyHandler.openai import prompt_elements_construct, prompt_elements_construct_old_version

logger = get_logger()


class GroupMessageManager:
    """群组消息管理器 - 高性能优化版"""

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

        # 配置参数
        self.MAX_MESSAGES = 50
        self.MAX_GROUPS = 1000
        self.MAX_CACHE_ITEMS = 500

        # 批量处理配置
        self.BATCH_SIZE = 10  # 批量处理大小
        self.CACHE_CLEANUP_THRESHOLD = 20  # 缓存清理阈值

        # 数据存储
        self._lock = RLock()
        self._messages = defaultdict(lambda: deque(maxlen=self.MAX_MESSAGES))
        self._group_order = deque(maxlen=self.MAX_GROUPS)
        self._group_order_set = set()  # 优化LRU查找

        # 预处理缓存
        self._processed_cache = {}
        self._cache_order = deque(maxlen=self.MAX_CACHE_ITEMS)

        # 延迟清理相关
        self._dirty_groups = set()  # 需要清理缓存的群组
        self._pending_messages = defaultdict(list)  # 待批量处理的消息
        self._batch_lock = threading.Lock()

        # 后台清理任务
        self._cleanup_task = None
        self._running = True

        self._initialized = True

        # 启动后台任务
        self._start_background_tasks()

    def _start_background_tasks(self):
        """启动后台清理任务"""

        def background_cleanup():
            while self._running:
                try:
                    self._batch_cleanup_cache()
                    time.sleep(0.1)  # 100ms清理一次
                except Exception as e:
                    logger.error(f"后台清理任务错误: {e}")

        self._cleanup_thread = threading.Thread(target=background_cleanup, daemon=True)
        self._cleanup_thread.start()

    def _batch_cleanup_cache(self):
        """批量清理缓存"""
        if not self._dirty_groups:
            return

        with self._lock:
            # 批量获取需要清理的群组
            groups_to_clean = list(self._dirty_groups)[:self.CACHE_CLEANUP_THRESHOLD]

            if not groups_to_clean:
                return

            # 批量清理
            keys_to_remove = []
            for group_id in groups_to_clean:
                keys_to_remove.extend(
                    k for k in self._processed_cache.keys()
                    if k[0] == group_id
                )
                self._dirty_groups.discard(group_id)

            # 执行清理
            for key in keys_to_remove:
                self._processed_cache.pop(key, None)
                try:
                    self._cache_order.remove(key)
                except ValueError:
                    pass

            if keys_to_remove:
                logger.debug(f"批量清理了 {len(keys_to_remove)} 个缓存项")

    def _update_group_lru_fast(self, group_id: int):
        """快速更新群组LRU（避免O(n)查找）"""
        if group_id not in self._group_order_set:
            # 新群组，直接添加
            self._group_order.append(group_id)
            self._group_order_set.add(group_id)

            # 如果超出限制，移除最老的
            if len(self._group_order_set) > self.MAX_GROUPS:
                if self._group_order:
                    oldest = self._group_order.popleft()
                    self._group_order_set.discard(oldest)
        else:
            # 已存在的群组，标记为最近使用但不立即移动
            # 使用延迟更新策略，避免频繁的deque操作
            pass

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
                if msg_part.get('type') == 'text':
                    text = msg_part.get('text', '').strip()
                    if '?' in text or '？' in text:
                        context_info['activities'].append('提问')
                        break

        return context_info

    async def _process_single_message(self, raw_message, index, context_info, standard, bot, event):
        """处理单条消息"""
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
            f"【群聊概况】参与人数：{len(participants_list)}人 | "
            f"消息总数：{context_info['message_count']}条 | "
            f"主要参与者：{', '.join(participants_list[:3])} | "
            f"活动类型：{', '.join(activities[:2])}"
        )

        if standard == "gemini":
            all_parts = []
            for entry in processed_list:
                if entry.get('role') == 'user':
                    all_parts.extend(entry.get('parts', []))

            summary_part = {"text": f"{group_summary}\n以上是群聊历史消息上下文。"}
            all_parts.insert(0, summary_part)

            return [
                {"role": "user", "parts": all_parts},
                {"role": "model", "parts": [{"text": "我已了解群聊上下文，会结合这些信息回应对话。"}]}
            ]
        else:
            all_parts = []
            for entry in processed_list:
                if entry.get('role') == 'user' and isinstance(entry.get('content'), list):
                    all_parts.extend(entry['content'])

            if all_parts:
                summary_part = {"type": "text", "text": f"{group_summary}\n以上是群聊历史消息上下文："}
                all_parts.insert(0, summary_part)
                return [
                    {"role": "user", "content": all_parts},
                    {"role": "assistant", "content": "我已了解群聊上下文，会结合这些信息回应对话。"}
                ]
            else:
                return [
                    {"role": "user", "content": f"{group_summary}\n以上是群聊历史消息上下文。"},
                    {"role": "assistant", "content": "我已了解群聊上下文，会结合这些信息回应对话。"}
                ]

    async def _preprocess_group_messages(self, group_id: int, standard: str = "gemini",
                                         data_length: int = 20, bot=None, event=None):
        """预处理群组消息为prompt格式"""
        try:
            with self._lock:
                if group_id not in self._messages:
                    logger.debug(f"群组 {group_id} 不存在消息")
                    return []
                messages = list(self._messages[group_id])

            if not messages:
                logger.debug(f"群组 {group_id} 消息为空")
                return []

            actual_length = min(data_length, len(messages))
            logger.debug(f"群组 {group_id}: 请求长度={data_length}, 实际处理长度={actual_length}")

            messages = messages[-actual_length:] if len(messages) > actual_length else messages
            messages = list(reversed(messages))

            context_info = self._build_context_info(messages)

            processed_list = []
            for i, raw_message in enumerate(messages):
                try:
                    processed_msg = await self._process_single_message(
                        raw_message, i, context_info, standard, bot, event
                    )
                    if processed_msg:
                        processed_list.append(processed_msg)
                except Exception as e:
                    logger.error(f"处理单条消息失败: {e}")
                    continue

            final_result = self._format_final_result(processed_list, context_info, standard)
            logger.debug(f"预处理完成: group_id={group_id}, 处理消息数={len(processed_list)}")
            return final_result

        except Exception as e:
            logger.error(f"预处理失败: {e}")
            return []

    # ======================= 高性能接口 =======================

    def add_to_group_fast(self, group_id: int, message):
        """超高速添加消息（无阻塞，延迟清理）"""
        with self._lock:
            # 1. 快速添加消息（O(1)）
            self._messages[group_id].append(message)

            # 2. 快速更新LRU（避免O(n)操作）
            self._update_group_lru_fast(group_id)

            # 3. 标记为需要清理（延迟处理）
            self._dirty_groups.add(group_id)

    def add_to_group_sync(self, group_id: int, message):
        """同步添加消息（保持兼容性）"""
        self.add_to_group_fast(group_id, message)

    async def add_to_group(self, group_id: int, message, delete_after: int = 50):
        """添加消息到群组（使用快速版本）"""
        self.add_to_group_fast(group_id, message)
        logger.debug(f"消息已快速添加到群组 {group_id}")

    async def get_group_messages(self, group_id: int, limit: int = 50):
        """获取群组消息文本列表"""
        with self._lock:
            if group_id not in self._messages:
                return []
            messages = list(self._messages[group_id])
            messages = list(reversed(messages))
            if limit:
                messages = messages[:limit]

        text_list = []
        for msg in messages:
            try:
                if "message" in msg and isinstance(msg["message"], list):
                    for msg_obj in msg["message"]:
                        if isinstance(msg_obj, dict) and "text" in msg_obj:
                            text_list.append(msg_obj["text"])
            except Exception:
                pass

        return text_list

    async def get_last_20_and_convert_to_prompt(self, group_id: int, data_length=20,
                                                prompt_standard="gemini", bot=None, event=None):
        """获取转换后的prompt（缓存优先）"""
        cache_key = (group_id, prompt_standard, data_length)

        # 检查缓存
        with self._lock:
            if cache_key in self._processed_cache:
                try:
                    self._cache_order.remove(cache_key)
                    self._cache_order.append(cache_key)
                except ValueError:
                    self._cache_order.append(cache_key)
                logger.debug(f"缓存命中: {cache_key}")
                return self._processed_cache[cache_key]

        # 缓存未命中，实时处理
        logger.debug(f"缓存未命中，实时处理: {cache_key}")
        result = await self._preprocess_group_messages(group_id, prompt_standard, data_length, bot, event)

        # 缓存结果
        if result:
            with self._lock:
                if len(self._processed_cache) >= self.MAX_CACHE_ITEMS:
                    if self._cache_order:
                        oldest_key = self._cache_order.popleft()
                        self._processed_cache.pop(oldest_key, None)

                self._processed_cache[cache_key] = result
                self._cache_order.append(cache_key)
                logger.debug(f"结果已缓存: {cache_key}")

        return result

    async def clear_group_messages(self, group_id: int):
        """清除群组消息"""
        with self._lock:
            if group_id in self._messages:
                self._messages[group_id].clear()

            # 从LRU中移除
            self._group_order_set.discard(group_id)

            # 清理相关缓存
            expired_keys = [k for k in self._processed_cache.keys() if k[0] == group_id]
            for k in expired_keys:
                self._processed_cache.pop(k, None)
                try:
                    self._cache_order.remove(k)
                except ValueError:
                    pass

            # 从脏群组集合中移除
            self._dirty_groups.discard(group_id)

        logger.info(f"✅ 已清除 group_id={group_id} 的所有数据")

    async def clear_all_group_cache(self):
        """清除所有数据"""
        with self._lock:
            self._messages.clear()
            self._group_order.clear()
            self._group_order_set.clear()
            self._processed_cache.clear()
            self._cache_order.clear()
            self._dirty_groups.clear()

        logger.info("✅ 所有群组数据已清除")
        return True

    def get_cache_stats(self):
        """获取统计信息"""
        with self._lock:
            total_messages = sum(len(msgs) for msgs in self._messages.values())
            return {
                "total_groups": len(self._messages),
                "total_messages": total_messages,
                "cached_prompts": len(self._processed_cache),
                "dirty_groups": len(self._dirty_groups),
                "memory_estimate_kb": total_messages * 0.5 + len(self._processed_cache) * 2,
                "max_cache_items": self.MAX_CACHE_ITEMS
            }

    def shutdown(self):
        """关闭管理器"""
        self._running = False
        if hasattr(self, '_cleanup_thread'):
            self._cleanup_thread.join(timeout=1.0)


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
    """向群组添加消息（高性能版本）"""
    manager = get_manager()
    await manager.add_to_group(group_id, message, delete_after)


async def get_group_messages(group_id: int, limit: int = 50):
    """获取群组消息列表"""
    manager = get_manager()
    return await manager.get_group_messages(group_id, limit)


async def get_last_20_and_convert_to_prompt(group_id: int, data_length=20, prompt_standard="gemini",
                                            bot=None, event=None):
    """获取转换后的prompt"""
    manager = get_manager()
    return await manager.get_last_20_and_convert_to_prompt(group_id, data_length, prompt_standard, bot, event)


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