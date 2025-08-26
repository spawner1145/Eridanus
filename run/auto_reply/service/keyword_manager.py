import aiosqlite
import json
import random
import asyncio
from pathlib import Path

from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.utils.install_and_import import install_and_import

fuzzywuzzy = install_and_import("fuzzywuzzy")
from fuzzywuzzy import fuzz, process
config=YAMLManager.get_instance()

class KeywordManager:
    def __init__(self, db_path="data/database/keywords.db"):
        self.db_path = db_path
        self.lock = asyncio.Lock()
        asyncio.run(self.init_db())

    async def init_db(self):
        """初始化数据库"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT,  -- NULL表示全局词库
                    keyword TEXT NOT NULL,
                    responses TEXT NOT NULL,  -- JSON格式存储多个回复
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建索引提高查询性能
            await db.execute("CREATE INDEX IF NOT EXISTS idx_group_keyword ON keywords(group_id, keyword)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_keyword ON keywords(keyword)")
            await db.commit()

    async def add_keyword(self, keyword: str, responses: list, group_id: str = None, cache_manager=None):
        """添加关键词 - 修复：正确合并已存在的关键词并清除缓存"""
        try:
            async with self.lock:
                async with aiosqlite.connect(self.db_path) as db:
                    # 检查是否已存在
                    cursor = await db.execute(
                        "SELECT id, responses FROM keywords WHERE keyword = ? AND group_id = ?",
                        (keyword, group_id)
                    )
                    existing = await cursor.fetchone()

                    if existing:
                        # 合并回复：将旧的和新的合并
                        old_responses = json.loads(existing[1])
                        # 转换message_chain为字符串格式存储
                        new_responses = [str(resp) for resp in responses]
                        # 合并而不是覆盖
                        combined_responses = old_responses + new_responses

                        await db.execute(
                            "UPDATE keywords SET responses = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                            (json.dumps(combined_responses), existing[0])
                        )
                        print(
                            f"关键词 '{keyword}' 已存在，已合并 {len(new_responses)} 个新回复到现有的 {len(old_responses)} 个回复中")

                        # 修复1: 清除相关缓存 - 更彻底的缓存清除
                        if cache_manager:
                            await self._clear_keyword_cache(cache_manager, keyword, group_id)
                            print(f"已清除关键词 '{keyword}' 的所有相关缓存")
                    else:
                        # 新增
                        response_strings = [str(resp) for resp in responses]
                        await db.execute(
                            "INSERT INTO keywords (group_id, keyword, responses) VALUES (?, ?, ?)",
                            (group_id, keyword, json.dumps(response_strings))
                        )
                        print(f"新增关键词 '{keyword}' 包含 {len(response_strings)} 个回复")

                    await db.commit()
                    return True
        except Exception as e:
            print(f"添加关键词错误: {e}")
            return False

    async def _clear_keyword_cache(self, cache_manager, keyword, group_id):
        """清除关键词相关的所有缓存 - 修复缓存清理逻辑"""
        try:
            # 方案1: 清除直接匹配的缓存
            await cache_manager.delete_cache(keyword, group_id)

            # 方案2: 清除所有可能匹配到这个关键词的缓存（模糊匹配相关）
            await cache_manager.clear_keyword_related_cache(keyword, group_id)

            # 方案3: 如果关键词很短或很常见，建议清空所有缓存确保一致性
            if len(keyword.strip()) <= 2:
                print(f"关键词 '{keyword}' 较短，清空所有缓存以确保匹配准确性")
                await cache_manager.clear_all_cache()

            print(f"缓存清理完成: keyword='{keyword}', group_id={group_id}")
        except Exception as e:
            print(f"清除缓存时发生错误: {e}")

    async def delete_keyword(self, keyword: str, group_id: str = None):
        """删除指定关键词 - 修复3: 如果不存在，返回可能匹配的关键词"""
        try:
            async with self.lock:
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute(
                        "SELECT id FROM keywords WHERE keyword = ? AND group_id = ?",
                        (keyword, group_id)
                    )
                    existing = await cursor.fetchone()

                    if existing:
                        await db.execute(
                            "DELETE FROM keywords WHERE id = ?",
                            (existing[0],)
                        )
                        await db.commit()
                        return {"success": True, "deleted": keyword}

                    # 修复3: 关键词不存在时，查找可能匹配的关键词
                    possible_matches = await self._find_similar_keywords(keyword, group_id, db)
                    return {"success": False, "keyword": keyword, "similar": possible_matches}

        except Exception as e:
            print(f"删除关键词错误: {e}")
            return {"success": False, "keyword": keyword, "error": str(e)}

    async def _find_similar_keywords(self, target_keyword: str, group_id: str, db):
        """查找相似的关键词 - 用于删除失败时的提示"""
        try:
            # 获取所有关键词
            cursor = await db.execute(
                "SELECT keyword FROM keywords WHERE group_id = ? OR group_id IS NULL",
                (group_id,)
            )
            all_keywords = [row[0] for row in await cursor.fetchall()]

            if not all_keywords:
                return []

            # 使用模糊匹配找到最相似的关键词
            similar_keywords = []
            target_clean = target_keyword.strip().lower()

            for kw in all_keywords:
                kw_clean = kw.strip().lower()
                score = fuzz.ratio(target_clean, kw_clean)
                if score >= 60:  # 相似度阈值
                    similar_keywords.append({"keyword": kw, "similarity": score})

            # 按相似度排序，返回前5个
            similar_keywords.sort(key=lambda x: x["similarity"], reverse=True)
            return similar_keywords[:5]

        except Exception as e:
            print(f"查找相似关键词错误: {e}")
            return []

    async def match_keyword(self, text: str, group_id: str):
        """智能匹配关键词 - 修复2: 确保随机选择回复"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 优先匹配群专用词库
                cursor = await db.execute(
                    "SELECT keyword, responses FROM keywords WHERE group_id = ?",
                    (group_id,)
                )
                group_keywords = await cursor.fetchall()

                # 获取全局词库
                cursor = await db.execute(
                    "SELECT keyword, responses FROM keywords WHERE group_id IS NULL"
                )
                global_keywords = await cursor.fetchall()

                # 合并词库，群词库优先
                all_keywords = group_keywords + global_keywords

                if not all_keywords:
                    return None

                # 智能匹配策略
                best_match_result = self._smart_match(text, all_keywords)

                if best_match_result:
                    matched_keyword, responses_json = best_match_result
                    responses = json.loads(responses_json)

                    # 修复2: 确保真正随机选择回复
                    if responses:
                        # 使用随机种子确保每次调用都是真正随机的
                        random.seed()
                        selected_response = random.choice(responses)
                        print(
                            f"关键词 '{matched_keyword}' 匹配成功，从 {len(responses)} 个回复中随机选择了第 {responses.index(selected_response) + 1} 个")
                        return selected_response
                    else:
                        print(f"关键词 '{matched_keyword}' 匹配成功但没有回复内容")
                        return None

                return None
        except Exception as e:
            print(f"匹配关键词错误: {e}")
            return None

    def _smart_match(self, text: str, keywords_data: list):
        """智能匹配算法 - 根据关键词长度动态调整策略"""
        text_clean = text.strip().lower()
        best_match = None
        best_score = 0

        for keyword, responses_json in keywords_data:
            keyword_clean = keyword.strip().lower()
            keyword_len = len(keyword_clean)

            # 1. 完全匹配 - 最高优先级
            if keyword_clean == text_clean:
                return (keyword, responses_json)

            # 2. 包含匹配 - 针对短关键词
            if keyword_len <= 3:
                # 短关键词使用严格策略
                contain_score = self._calculate_contain_score(text_clean, keyword_clean)
                if contain_score > best_score:
                    best_score = contain_score
                    best_match = (keyword, responses_json)
            else:
                # 长关键词使用模糊匹配
                fuzzy_score = self._calculate_fuzzy_score(text_clean, keyword_clean)
                if fuzzy_score > best_score:
                    best_score = fuzzy_score
                    best_match = (keyword, responses_json)

        # 3. 如果没有高分匹配，尝试部分匹配
        if best_score < 80:
            partial_match = self._partial_match(text_clean, keywords_data)
            if partial_match:
                return partial_match

        return best_match if best_score >= MatchConfig.MINIMUM_MATCH_SCORE else None

    def _calculate_contain_score(self, text: str, keyword: str):
        """计算包含匹配分数 - 针对短关键词"""
        keyword_len = len(keyword)

        # 完全包含
        if keyword in text:
            # 根据关键词在文本中的位置和周围内容给分
            if text == keyword:
                return 100  # 完全匹配

            # 检查是否是独立词汇（被空格、标点分隔）
            import re
            pattern = r'(?<![a-zA-Z\u4e00-\u9fff])' + re.escape(keyword) + r'(?![a-zA-Z\u4e00-\u9fff])'
            if re.search(pattern, text):
                return 95  # 独立词汇

            # 普通包含
            return max(85, 100 - (len(text) - keyword_len) * 2)

        # 2字关键词的特殊处理
        if keyword_len == 2:
            # 检查字符交换（如"你好" vs "好你"）
            if len(text) >= 2 and keyword[0] in text and keyword[1] in text:
                char1_pos = text.find(keyword[0])
                char2_pos = text.find(keyword[1])
                if abs(char1_pos - char2_pos) <= 2:  # 两字距离很近
                    return 75

        # 使用编辑距离for短关键词
        if keyword_len <= 3:
            distance = self._edit_distance(keyword, text[:keyword_len + 2])
            if distance <= 1:  # 允许1个字符差异
                return max(70, 90 - distance * 20)

        return 0

    def _calculate_fuzzy_score(self, text: str, keyword: str):
        """计算模糊匹配分数 - 针对长关键词"""
        # 使用多种匹配算法取最高分
        ratio_score = fuzz.ratio(text, keyword)
        partial_score = fuzz.partial_ratio(text, keyword)
        token_sort_score = fuzz.token_sort_ratio(text, keyword)
        token_set_score = fuzz.token_set_ratio(text, keyword)

        # 综合得分，partial_ratio权重更高（适合包含匹配）
        final_score = max(
            ratio_score,
            partial_score * 0.9,  # 稍微降权避免过度匹配
            token_sort_score * 0.8,
            token_set_score * 0.8
        )

        return final_score

    def _partial_match(self, text: str, keywords_data: list):
        """部分匹配 - 最后的尝试"""
        text_chars = set(text)

        for keyword, responses_json in keywords_data:
            keyword_clean = keyword.strip().lower()
            keyword_chars = set(keyword_clean)

            # 计算字符重叠度
            if len(keyword_clean) <= 4:  # 只对短关键词使用
                overlap = len(text_chars & keyword_chars)
                overlap_ratio = overlap / len(keyword_chars)

                if overlap_ratio >= 0.8 and overlap >= 2:  # 80%字符重叠且至少2个字符
                    return (keyword, responses_json)

        return None

    def _edit_distance(self, s1: str, s2: str):
        """计算编辑距离"""
        if len(s1) > len(s2):
            s1, s2 = s2, s1

        distances = list(range(len(s1) + 1))
        for i2, c2 in enumerate(s2):
            distances_ = [i2 + 1]
            for i1, c1 in enumerate(s1):
                if c1 == c2:
                    distances_.append(distances[i1])
                else:
                    distances_.append(1 + min((distances[i1], distances[i1 + 1], distances_[-1])))
            distances = distances_

        return distances[-1]


# config.py - 匹配配置管理
class MatchConfig:
    """匹配算法配置"""
    MINIMUM_MATCH_SCORE = config.auto_reply.config["minimum_match_score"]

    @classmethod
    def get_threshold_by_length(cls, keyword_length: int) -> int:
        """根据关键词长度返回匹配阈值"""
        if keyword_length <= 2:
            return 94  # 影响：超短词使用最严格阈值，最大化精度，防止单字误匹配
        elif keyword_length == 3:
            return 85  # 影响：3字词适中阈值，平衡精度与召回率
        else:
            return 80  # 影响：长词可放宽阈值，因为长词误匹配概率天然较低