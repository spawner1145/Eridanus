import asyncio
import aiosqlite
#抄(x)借鉴自llmDB

DATABASE_FILE = "data/dataBase/webui_chat_database.db"

# --- 异步数据库操作 ---

async def init_db():
    """初始化数据库"""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversation_history (
                msg_id INTEGER PRIMARY KEY,
                data TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS file_list (
                origin_url TEXT PRIMARY KEY,
                data TEXT
            )
        """)
        await db.commit()

async def get_msg(start = 0,end = 1)->list:
    """获取历史聊天记录"""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        #按照msg_id（ms时间戳）降序排序，取第start到第end个
        async with db.execute("SELECT data FROM conversation_history ORDER BY msg_id DESC LIMIT ? OFFSET ?", (end - start + 1, start)) as cursor:
            results = await cursor.fetchall()
            if results:
                return results
            else:
                return []

async def update_msg(msg_id, data):
    """更新聊天记录"""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("INSERT OR REPLACE INTO conversation_history (msg_id, data) VALUES (?, ?)",
                         (msg_id, data))
        await db.commit()

async def delete_specified_msg(msg_id):
    """删除指定id的聊天记录"""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("DELETE FROM conversation_history WHERE msg_id = ?", (msg_id,))
        await db.commit()

async def delete_all_msg():
    """清理所有聊天记录"""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("DELETE FROM conversation_history")
        await db.execute("DELETE FROM file_list")
        await db.commit()
        print("已清理WebUI的所有对话记录。")

async def get_file_storage(origin_url):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        #按照msg_id（ms时间戳）降序排序，取第start到第end个
        async with db.execute("SELECT data FROM file_list WHERE origin_url = ?", (origin_url,)) as cursor:
            result = await cursor.fetchone()
            if result:
                return result[0]
            else:
                return None

async def update_file_storage(origin_url, file_name):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("INSERT OR REPLACE INTO file_list (origin_url, data) VALUES (?, ?)", (origin_url, file_name))
        await db.commit()

asyncio.run(init_db())
