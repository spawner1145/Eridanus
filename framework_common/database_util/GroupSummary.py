"""
群聊总结数据库管理模块
用于存储和管理群聊消息总结
"""
import os
import aiosqlite
import datetime
from developTools.utils.logger import get_logger

dbpath = "data/dataBase/group_summary.db"
logger = get_logger()

# 全局变量存储初始化状态
_db_initialized: bool = False


async def ensure_db_initialized():
    """确保数据库已初始化"""
    global _db_initialized
    if not _db_initialized:
        await initialize_db()
        _db_initialized = True


async def initialize_db():
    """初始化群聊总结数据库表结构"""
    try:
        db_dir = os.path.dirname(dbpath)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

        async with aiosqlite.connect(dbpath) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            await db.execute("PRAGMA cache_size=10000;")
            await db.execute("PRAGMA temp_store=MEMORY;")
            await db.execute("PRAGMA busy_timeout=5000;")

            await db.execute("""
            CREATE TABLE IF NOT EXISTS group_summaries (
                group_id INTEGER PRIMARY KEY,
                summary TEXT DEFAULT '',
                update_time TEXT DEFAULT '',
                message_count INTEGER DEFAULT 0,
                last_summarized_count INTEGER DEFAULT 0
            )
            """)

            # 检查并添加缺失的列
            required_columns = {
                'summary': 'TEXT DEFAULT ""',
                'update_time': 'TEXT DEFAULT ""',
                'message_count': 'INTEGER DEFAULT 0',
                'last_summarized_count': 'INTEGER DEFAULT 0'
            }

            async with db.execute("PRAGMA table_info(group_summaries);") as cursor:
                columns = await cursor.fetchall()
                existing_columns = [col[1] for col in columns]

            for column_name, column_def in required_columns.items():
                if column_name not in existing_columns:
                    await db.execute(f"ALTER TABLE group_summaries ADD COLUMN {column_name} {column_def};")
                    #logger.info(f"✅ 群聊总结表添加了 {column_name} 列")

            await db.execute("CREATE INDEX IF NOT EXISTS idx_group_id ON group_summaries(group_id);")

            await db.commit()
            #logger.info("✅ 群聊总结数据库初始化完成")

    except Exception as e:
        logger.error(f"群聊总结数据库初始化失败: {e}")
        raise


async def get_group_summary(group_id: int) -> dict:
    """获取群聊总结信息"""
    await ensure_db_initialized()
    try:
        async with aiosqlite.connect(dbpath) as db:
            async with db.execute(
                "SELECT summary, update_time, message_count, last_summarized_count FROM group_summaries WHERE group_id = ?",
                (group_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "group_id": group_id,
                        "summary": row[0] or "",
                        "update_time": row[1] or "",
                        "message_count": row[2] or 0,
                        "last_summarized_count": row[3] or 0
                    }
                else:
                    return {
                        "group_id": group_id,
                        "summary": "",
                        "update_time": "",
                        "message_count": 0,
                        "last_summarized_count": 0
                    }
    except Exception as e:
        logger.error(f"获取群聊总结失败: {e}")
        return {
            "group_id": group_id,
            "summary": "",
            "update_time": "",
            "message_count": 0,
            "last_summarized_count": 0
        }


async def update_group_summary(group_id: int, summary: str = None, message_count: int = None, 
                                last_summarized_count: int = None):
    """更新群聊总结"""
    await ensure_db_initialized()
    try:
        async with aiosqlite.connect(dbpath) as db:
            # 检查记录是否存在
            async with db.execute(
                "SELECT group_id FROM group_summaries WHERE group_id = ?", (group_id,)
            ) as cursor:
                exists = await cursor.fetchone()

            if not exists:
                # 插入新记录
                await db.execute(
                    "INSERT INTO group_summaries (group_id, summary, update_time, message_count, last_summarized_count) VALUES (?, ?, ?, ?, ?)",
                    (group_id, summary or "", datetime.datetime.now().isoformat(), message_count or 0, last_summarized_count or 0)
                )
            else:
                # 更新现有记录
                updates = []
                params = []
                
                if summary is not None:
                    updates.append("summary = ?")
                    params.append(summary)
                    updates.append("update_time = ?")
                    params.append(datetime.datetime.now().isoformat())
                
                if message_count is not None:
                    updates.append("message_count = ?")
                    params.append(message_count)
                
                if last_summarized_count is not None:
                    updates.append("last_summarized_count = ?")
                    params.append(last_summarized_count)
                
                if updates:
                    params.append(group_id)
                    await db.execute(
                        f"UPDATE group_summaries SET {', '.join(updates)} WHERE group_id = ?",
                        params
                    )
            
            await db.commit()
            logger.debug(f"群 {group_id} 总结已更新")
    except Exception as e:
        logger.error(f"更新群聊总结失败: {e}")


async def increment_group_message_count(group_id: int):
    """增加群消息计数"""
    await ensure_db_initialized()
    try:
        async with aiosqlite.connect(dbpath) as db:
            # 检查记录是否存在
            async with db.execute(
                "SELECT message_count FROM group_summaries WHERE group_id = ?", (group_id,)
            ) as cursor:
                row = await cursor.fetchone()

            if not row:
                # 插入新记录
                await db.execute(
                    "INSERT INTO group_summaries (group_id, message_count) VALUES (?, 1)",
                    (group_id,)
                )
            else:
                # 增加计数
                await db.execute(
                    "UPDATE group_summaries SET message_count = message_count + 1 WHERE group_id = ?",
                    (group_id,)
                )
            
            await db.commit()
    except Exception as e:
        logger.error(f"增加群消息计数失败: {e}")


async def clear_group_summary(group_id: int):
    """清除指定群的总结"""
    await ensure_db_initialized()
    try:
        async with aiosqlite.connect(dbpath) as db:
            await db.execute(
                "UPDATE group_summaries SET summary = '', update_time = '', last_summarized_count = 0 WHERE group_id = ?",
                (group_id,)
            )
            await db.commit()
            logger.info(f"群 {group_id} 总结已清除")
    except Exception as e:
        logger.error(f"清除群聊总结失败: {e}")


async def clear_all_group_summaries():
    """清除所有群的总结"""
    await ensure_db_initialized()
    try:
        async with aiosqlite.connect(dbpath) as db:
            await db.execute(
                "UPDATE group_summaries SET summary = '', update_time = '', last_summarized_count = 0"
            )
            await db.commit()
            logger.info("所有群聊总结已清除")
    except Exception as e:
        logger.error(f"清除所有群聊总结失败: {e}")


async def should_generate_summary(group_id: int, interval: int) -> bool:
    """检查是否应该生成新的总结"""
    info = await get_group_summary(group_id)
    message_count = info.get("message_count", 0)
    last_summarized_count = info.get("last_summarized_count", 0)
    
    # 如果消息数量增加了足够多，则需要生成新总结
    return (message_count - last_summarized_count) >= interval
