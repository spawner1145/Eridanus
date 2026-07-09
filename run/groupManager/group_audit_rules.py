"""
group_audit_rules.py
per-group 加群审核条件 的持久化管理
存储位置：data/text/group_audit_rules.json
结构：
{
    "123456789": {
        "rule": "只允许说明来意为学习交流的申请，禁止纯数字/广告理由",
        "updated_by": 111222333,
        "updated_at": "2026-07-09 12:00:00"
    },
    ...
}
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Optional, Dict

RULES_DIR = Path("data/text")
RULES_PATH = RULES_DIR / "group_audit_rules.json"

_lock = asyncio.Lock()


def _ensure_file_sync() -> None:
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    if not RULES_PATH.exists():
        with open(RULES_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)


def _load_sync() -> Dict[str, dict]:
    _ensure_file_sync()
    try:
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {}
            return data
    except (json.JSONDecodeError, OSError):
        # 文件损坏时不至于让整个 handler 崩掉，退回空规则表
        return {}


def _save_sync(data: Dict[str, dict]) -> None:
    _ensure_file_sync()
    tmp_path = RULES_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, RULES_PATH)  # 原子替换，避免写到一半崩溃导致文件损坏


async def load_rules() -> Dict[str, dict]:
    async with _lock:
        return await asyncio.to_thread(_load_sync)


async def get_rule(group_id) -> Optional[str]:
    """返回某群设置的加群条件文本，没有设置则返回 None"""
    rules = await load_rules()
    entry = rules.get(str(group_id))
    if entry and entry.get("rule"):
        return entry["rule"]
    return None


async def set_rule(group_id, rule_text: str, operator_id=None) -> None:
    async with _lock:
        data = await asyncio.to_thread(_load_sync)
        data[str(group_id)] = {
            "rule": rule_text,
            "updated_by": operator_id,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        await asyncio.to_thread(_save_sync, data)


async def remove_rule(group_id) -> bool:
    """清除某群的加群条件设置，返回是否成功删除"""
    async with _lock:
        data = await asyncio.to_thread(_load_sync)
        if str(group_id) in data:
            del data[str(group_id)]
            await asyncio.to_thread(_save_sync, data)
            return True
        return False
