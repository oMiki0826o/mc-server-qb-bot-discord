"""
core/qb/history.py

Modification():

- 新增操作紀錄：每次 make／back 執行完（不管成功失敗）都記一筆，
  存成 JSON 檔案而不是純記憶體變數，bot 重啟紀錄也不會不見。
  供 !!info 指令讀取顯示。

Description():

- record(...)：新增一筆操作紀錄，超過 QB_HISTORY_KEEP 筆自動砍掉最舊的。
- recent(limit)：取得最近 limit 筆，新到舊排序，給 !!info 顯示用。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import config


# ── 讀寫紀錄檔，壞掉或不存在都當作空清單，不讓 !!info 直接掛掉 ──────────────────────

def _load() -> list[dict[str, Any]]:
    if not config.QB_HISTORY_FILE.exists():
        return []
    try:
        return json.loads(config.QB_HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(entries: list[dict[str, Any]]) -> None:
    config.QB_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.QB_HISTORY_FILE.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── 新增一筆操作紀錄 ──────────────────────

def record(action: str, user: str, target: str, success: bool, detail: str) -> None:
    entries = _load()
    entries.append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "action": action,
        "user": user,
        "target": target,
        "success": success,
        "detail": detail,
    })
    entries = entries[-config.QB_HISTORY_KEEP:]
    _save(entries)


# ── 取得最近 limit 筆，新到舊排序 ──────────────────────

def recent(limit: int = 10) -> list[dict[str, Any]]:
    return list(reversed(_load()))[:limit]
