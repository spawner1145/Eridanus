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
    """群组消息管理器 - 单例模式"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 防止重复初始化
        if hasattr(self, '_initialized'):
            return

        # 配置参数
        self.MAX_MESSAGES = 50  # 每群最大消息数
        self.MAX_GROUPS = 1000  # 最大群组数
        self.MAX_CACHE_ITEMS = 500  # 最大缓存项数

        # 数据存储
        self._lock = RLock()
        self._messages = defaultdict(lambda: deque(maxlen=self.MAX_MESSAGES))
        self._group_order = deque(maxlen=self.MAX_GROUPS)  # LRU顺序

        # 预处理缓存 - 有界LRU缓存
        self._processed_cache = {}  # {(group_id, standard, length): processed_data}
        self._cache_order = deque(maxlen=self.MAX_CACHE_ITEMS)  # LRU顺序

        self._initialized = True

    def _build_context_info(self, messages):
        """构建上下文信息"""
        context_info = {
            'participants': set(),
            'message_count': len(messages),
            'activities': []
        }

        for msg in messages[:10]:  # 只分析前10条避免过度处理
            user_name = msg.get('user_name', '未知用户')
            user_id = msg.get('user_id', '')

            if len(context_info['participants']) < 10:
                context_info['participants'].add(f"{user_name}(ID:{user_id})")

            # 简单活动分析
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

        # 复制消息避免修改原始数据
        message_copy = json.loads(json.dumps(raw_message))
        message_copy["message"].insert(0, {
            "text": f"{context_prompt}\n这是群聊历史消息，用于理解当前对话上下文。"
        })

        # 根据标准处理
        if standard == "gemini":
            return await gemini_prompt_elements_construct(message_copy["message"], bot=bot, event=event)
        elif standard == "new_openai":
            return await prompt_elements_construct(message_copy["message"], bot=bot, event=event)
        else:  # old_openai
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

            # 添加概况
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
            # 获取原始消息
            with self._lock:
                if group_id not in self._messages:
                    logger.debug(f"群组 {group_id} 不存在消息")
                    return []
                messages = list(self._messages[group_id])

            if not messages:
                logger.debug(f"群组 {group_id} 消息为空")
                return []

            # 处理请求长度超出实际消息数量的情况
            actual_length = min(data_length, len(messages))
            logger.debug(
                f"群组 {group_id}: 请求长度={data_length}, 实际消息数={len(messages)}, 实际处理长度={actual_length}")

            # 获取最新的消息并倒序（最新的在前）
            messages = messages[-actual_length:] if len(messages) > actual_length else messages
            messages = list(reversed(messages))

            # 构建上下文信息
            context_info = self._build_context_info(messages)

            # 处理消息
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

            # 格式化最终结果
            final_result = self._format_final_result(processed_list, context_info, standard)

            logger.debug(f"预处理完成: group_id={group_id}, standard={standard}, 处理消息数={len(processed_list)}")
            return final_result

        except Exception as e:
            logger.error(f"预处理失败: {e}")
            return []

    # ======================= 公共接口 =======================
    def add_to_group_sync(self, group_id: int, message):
        """同步添加消息（最快路径，无阻塞）"""
        with self._lock:
            # 1. 添加消息（O(1)操作）
            self._messages[group_id].append(message)

            # 2. 更新LRU顺序（优化：避免重复查找）
            try:
                self._group_order.remove(group_id)  # 如果存在则移除
            except ValueError:
                pass  # 不存在就忽略
            self._group_order.append(group_id)

            # 3. 清理相关缓存（批量操作，减少锁竞争）
            keys_to_remove = [k for k in self._processed_cache.keys() if k[0] == group_id]
            for k in keys_to_remove:
                self._processed_cache.pop(k, None)
                try:
                    self._cache_order.remove(k)
                except ValueError:
                    pass

    async def add_to_group(self, group_id: int, message, delete_after: int = 50):
        """添加消息到群组（移除了后台处理，只做简单存储）"""
        # 只做同步快速添加，不进行后台预处理
        self.add_to_group_sync(group_id, message)
        logger.debug(f"消息已添加到群组 {group_id}")

    async def get_group_messages(self, group_id: int, limit: int = 50):
        """获取群组消息文本列表"""
        with self._lock:
            if group_id not in self._messages:
                return []

            messages = list(self._messages[group_id])
            messages = list(reversed(messages))  # 最新的在前

            if limit:
                messages = messages[:limit]

        # 提取文本
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
        """获取转换后的prompt（优先返回缓存，缓存未命中时实时处理）"""
        cache_key = (group_id, prompt_standard, data_length)

        # 检查缓存
        with self._lock:
            if cache_key in self._processed_cache:
                # 更新LRU顺序
                try:
                    self._cache_order.remove(cache_key)
                except ValueError:
                    pass
                self._cache_order.append(cache_key)
                logger.debug(f"缓存命中: group_id={group_id}, standard={prompt_standard}, length={data_length}")
                return self._processed_cache[cache_key]

        # 缓存未命中，实时处理
        logger.debug(f"缓存未命中，开始实时处理: group_id={group_id}, standard={prompt_standard}, length={data_length}")
        result = await self._preprocess_group_messages(group_id, prompt_standard, data_length, bot, event)

        # 缓存结果
        if result:
            with self._lock:
                # 如果缓存满了，移除最老的项
                if len(self._processed_cache) >= self.MAX_CACHE_ITEMS:
                    if self._cache_order:
                        oldest_key = self._cache_order.popleft()
                        self._processed_cache.pop(oldest_key, None)
                        logger.debug(f"缓存已满，移除最老项: {oldest_key}")

                self._processed_cache[cache_key] = result

                # 更新LRU顺序
                if cache_key in self._cache_order:
                    try:
                        self._cache_order.remove(cache_key)
                    except ValueError:
                        pass
                self._cache_order.append(cache_key)

                logger.debug(f"结果已缓存: group_id={group_id}, standard={prompt_standard}, length={data_length}")

        return result

    async def clear_group_messages(self, group_id: int):
        """清除群组消息"""
        with self._lock:
            if group_id in self._messages:
                self._messages[group_id].clear()

            try:
                self._group_order.remove(group_id)
            except ValueError:
                pass

            # 清理相关缓存
            expired_keys = [k for k in self._processed_cache.keys() if k[0] == group_id]
            for k in expired_keys:
                self._processed_cache.pop(k, None)
                try:
                    self._cache_order.remove(k)
                except ValueError:
                    pass

        logger.info(f"✅ 已清除 group_id={group_id} 的所有数据")

    async def clear_all_group_cache(self):
        """清除所有数据"""
        with self._lock:
            self._messages.clear()
            self._group_order.clear()
            self._processed_cache.clear()
            self._cache_order.clear()

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
                "memory_estimate_kb": total_messages * 0.5 + len(self._processed_cache) * 2,
                "max_cache_items": self.MAX_CACHE_ITEMS
            }


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
    """向群组添加消息（简化版，不进行后台处理）"""
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