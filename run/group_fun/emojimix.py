import os
import aiosqlite
import httpx
import aiofiles
import asyncio
from pathlib import Path

from developTools.event.events import GroupMessageEvent
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from developTools.message.message_components import Image, Reply

BASE_DIR = Path(__file__).resolve().parents[2]
db_path = BASE_DIR / 'data/dataBase/emoji_metadata.db'
local_path = BASE_DIR / 'data/pictures/emojimix'
os.makedirs(local_path, exist_ok=True)

MAX_CACHE = 20
supported_emojis = set()
async def init_emoji_cache():
    """启动时加载所有支持的emoji到内存中"""
    global supported_emojis
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute('SELECT code FROM emoji')
        rows = await cursor.fetchall()
        await cursor.close()
        supported_emojis = {row[0] for row in rows}
def emoji_to_codepoint_string(char: str) -> str:
    return '-'.join(f"{ord(c):x}" for c in char)


async def is_supported_emoji(char: str) -> bool:
    return char in supported_emojis
"""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute('SELECT 1 FROM emoji WHERE code = ?', (char,))
        res = await cursor.fetchone()
        await cursor.close()
        return res is not None
"""
async def get_combinations(base_code: str, left_code: str, right_code: str):
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute('''
            SELECT date, gStaticUrl FROM combinations
            WHERE base_code = ? AND left_code = ? AND right_code = ?
        ''', (base_code, left_code, right_code))
        rows = await cursor.fetchall()
        await cursor.close()
        return rows

async def download_image(url: str, save_path: Path) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                async with aiofiles.open(save_path, 'wb') as f:
                    await f.write(resp.content)
                await enforce_cache_limit()
                return True
            return False
    except:
        return False

async def enforce_cache_limit():
    files = sorted(local_path.glob("*.png"), key=lambda f: f.stat().st_mtime)
    while len(files) > MAX_CACHE:
        try:
            files[0].unlink()
            files.pop(0)
        except Exception:
            break

async def try_mix(left_code: str, right_code: str, reverse: bool = False) -> str | None:
    base_code = right_code if not reverse else left_code
    combos = await get_combinations(base_code, left_code, right_code)

    if combos:
        latest_combo = max(combos, key=lambda row: int(row[0]) if row[0].isdigit() else -1)
        url = latest_combo[1]
    else:
        latest = '20250130'
        if not reverse:
            url = f'https://www.gstatic.com/android/keyboard/emojikitchen/{latest}/u{right_code}/u{left_code}_u{right_code}.png'
        else:
            url = f'https://www.gstatic.com/android/keyboard/emojikitchen/{latest}/u{left_code}/u{left_code}_u{right_code}.png'

    filename = f'u{left_code}_u{right_code}.png'
    path = local_path / filename

    if path.exists():
        return str(path)

    success = await download_image(url, path)
    return str(path) if success else None

async def emojimix_handle(a: str, b: str) -> str | None:
    if not await is_supported_emoji(a):
        return 'a'
    if not await is_supported_emoji(b):
        return 'b'

    a_code = emoji_to_codepoint_string(a)
    b_code = emoji_to_codepoint_string(b)

    filename = f'u{a_code}_u{b_code}.png'
    local_file = local_path / filename
    if local_file.exists():
        return str(local_file)

    result = await try_mix(a_code, b_code)
    if result:
        return result

    return await try_mix(b_code, a_code, reverse=True)

def main(bot: ExtendBot, config: YAMLManager):
    asyncio.create_task(init_emoji_cache())
    @bot.on(GroupMessageEvent)
    async def handle_group_message(event: GroupMessageEvent):
        if len(event.pure_text) == 2:
            emoji1, emoji2 = event.pure_text[0], event.pure_text[1]
            result = await emojimix_handle(emoji1, emoji2)
            if isinstance(result, str) and result.endswith('.png'):
                await bot.send(event, [Reply(id=event.message_id), Image(file=result)])
