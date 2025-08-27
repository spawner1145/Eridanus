import asyncio
import time
from collections import OrderedDict


class LRUCache:
    def __init__(self, max_size: int = 1000, ttl: int = 300):  # 5分钟TTL
        self.max_size = max_size
        self.ttl = ttl
        self.cache = OrderedDict()
        self.timestamps = {}
        self.lock = asyncio.Lock()

    async def get(self, key: str):
        async with self.lock:
            if key not in self.cache:
                return None

            # 检查是否过期
            if time.time() - self.timestamps[key] > self.ttl:
                del self.cache[key]
                del self.timestamps[key]
                return None

            # 移到最后（最近使用）
            value = self.cache.pop(key)
            self.cache[key] = value
            return value

    async def set(self, key: str, value):
        async with self.lock:
            # 如果已存在，更新
            if key in self.cache:
                self.cache.pop(key)
            # 如果达到最大容量，删除最旧的
            elif len(self.cache) >= self.max_size:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                del self.timestamps[oldest_key]

            self.cache[key] = value
            self.timestamps[key] = time.time()

    async def delete(self, key: str):
        async with self.lock:
            if key in self.cache:
                del self.cache[key]
                del self.timestamps[key]

    async def clear_all(self):
        """清空所有缓存"""
        async with self.lock:
            self.cache.clear()
            self.timestamps.clear()

    async def delete_by_pattern(self, keyword: str):
        """删除包含特定关键词的缓存项 - 修复：更精准的模式匹配"""
        async with self.lock:
            keys_to_delete = []
            keyword_lower = keyword.lower()

            for cache_key in self.cache.keys():
                # 缓存键格式通常是 "text:hash"，我们检查text部分
                if ':' in cache_key:
                    text_part = cache_key.split(':')[0]
                    text_lower = text_part.lower()

                    # 精准匹配策略：
                    # 1. 完全匹配
                    # 2. 关键词包含在文本中
                    # 3. 文本包含在关键词中（用于短关键词）
                    if (keyword_lower == text_lower or
                            keyword_lower in text_lower or
                            text_lower in keyword_lower):
                        keys_to_delete.append(cache_key)
                elif keyword_lower in cache_key.lower():
                    keys_to_delete.append(cache_key)

            for key in keys_to_delete:
                if key in self.cache:
                    del self.cache[key]
                    del self.timestamps[key]

            return len(keys_to_delete)


class CacheManager:
    def __init__(self, max_size: int = 1000):
        self.group_caches = {}
        self.global_cache = LRUCache(max_size)
        self.max_size = max_size
        self.lock = asyncio.Lock()

    def _get_cache_key(self, text: str, group_id: str):
        """生成缓存键"""
        return f"{text}:{hash(text) % 10000}"  # 限制键长度

    async def get(self, text: str, group_id: str):
        """获取缓存 - 修复：处理NO_MATCH标记"""
        cache_key = self._get_cache_key(text, group_id)

        # 先检查群缓存
        if group_id:
            async with self.lock:
                if group_id not in self.group_caches:
                    self.group_caches[group_id] = LRUCache(self.max_size // 10)

            group_result = await self.group_caches[group_id].get(cache_key)
            if group_result:
                # 如果是NO_MATCH标记，返回None（表示确认无匹配）
                if group_result == "NO_MATCH":
                    return None
                return group_result

        # 检查全局缓存
        global_result = await self.global_cache.get(cache_key)
        if global_result == "NO_MATCH":
            return None
        return global_result

    async def set(self, text: str, group_id: str, response):
        """设置缓存 - 修复：支持NO_MATCH标记"""
        cache_key = self._get_cache_key(text, group_id)

        if group_id:
            async with self.lock:
                if group_id not in self.group_caches:
                    self.group_caches[group_id] = LRUCache(self.max_size // 10)

            await self.group_caches[group_id].set(cache_key, response)
        else:
            await self.global_cache.set(cache_key, response)

    async def delete_cache(self, text: str, group_id: str):
        """删除指定关键词的缓存"""
        cache_key = self._get_cache_key(text, group_id)
        if group_id:
            async with self.lock:
                if group_id in self.group_caches:
                    await self.group_caches[group_id].delete(cache_key)
        else:
            await self.global_cache.delete(cache_key)

    async def clear_keyword_related_cache(self, keyword: str, group_id: str = None):
        """清除与特定关键词相关的所有缓存 - 修复：更彻底的清理"""
        cleared_count = 0

        try:
            # 清除群缓存
            if group_id:
                async with self.lock:
                    if group_id in self.group_caches:
                        cleared_count += await self.group_caches[group_id].delete_by_pattern(keyword)

            # 清除全局缓存
            cleared_count += await self.global_cache.delete_by_pattern(keyword)

            # 额外清除直接匹配的缓存
            await self.delete_cache(keyword, group_id)

            # 修复：对于短关键词或常用词，清除可能的变体
            if len(keyword.strip()) <= 3:
                # 为短关键词清除更多相关缓存
                similar_patterns = [
                    keyword.upper(),
                    keyword.lower(),
                    keyword.strip(),
                    f" {keyword} ",
                    f"{keyword}!",
                    f"{keyword}？",
                    f"{keyword}。",
                ]

                for pattern in similar_patterns:
                    if pattern != keyword:  # 避免重复
                        if group_id:
                            async with self.lock:
                                if group_id in self.group_caches:
                                    cleared_count += await self.group_caches[group_id].delete_by_pattern(pattern)
                        cleared_count += await self.global_cache.delete_by_pattern(pattern)

            print(f"清除了 {cleared_count} 个与关键词 '{keyword}' 相关的缓存项")
            return cleared_count

        except Exception as e:
            print(f"清除关键词相关缓存时发生错误: {e}")
            return 0

    async def clear_all_cache(self):
        """清空所有缓存 - 调试用"""
        async with self.lock:
            # 清空所有群缓存
            for group_cache in self.group_caches.values():
                await group_cache.clear_all()

            # 清空全局缓存
            await self.global_cache.clear_all()

        print("已清空所有缓存")

    async def invalidate_cache_for_text(self, text: str):
        """使特定文本的所有缓存失效 - 新增方法"""
        """当关键词被修改时，需要清除所有可能匹配到该文本的缓存"""
        try:
            cleared_count = 0

            # 清除所有群的相关缓存
            async with self.lock:
                for group_id, group_cache in self.group_caches.items():
                    cleared_count += await group_cache.delete_by_pattern(text)

            # 清除全局缓存
            cleared_count += await self.global_cache.delete_by_pattern(text)

            print(f"为文本 '{text}' 清除了 {cleared_count} 个缓存项")
            return cleared_count

        except Exception as e:
            print(f"清除文本相关缓存时发生错误: {e}")
            return 0