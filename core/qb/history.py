"""
core/qb/history.py

Modification():

- HistoryEntry 從裸 dict 改成 dataclass，欄位有型別可以檢查，也不用
  在到處用字串 key 存取字典。
- 新增 flow_id／duration 兩個欄位，把每筆紀錄跟 core/qb/process.py
  產生的時間軸 log 串起來：以後想深入了解某次備份到底卡在哪一步，
  可以直接拿 flow_id 去 log 檔案裡搜尋完整過程。這兩個欄位都是選填，
  讀取舊格式（沒有這兩個欄位）的紀錄檔不會壞掉。

Description():

- HistoryEntry.from_dict()：把 JSON 裡的一筆資料轉成 HistoryEntry，
  缺欄位一律給預設值，不會因為讀到舊格式就丟例外。
- record(...)：新增一筆操作紀錄，超過 QB_HISTORY_KEEP 筆自動砍掉
  最舊的。
- recent(limit)：取得最近 limit 筆，新到舊排序，給 /info 顯示用。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime

import config


@dataclass(frozen=True)
class HistoryEntry:
    time: str
    action: str
    user: str
    target: str
    success: bool
    detail: str
    flow_id: str | None = None
    duration: float | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "HistoryEntry":
        return cls(
            time=data.get("time", ""),
            action=data.get("action", ""),
            user=data.get("user", ""),
            target=data.get("target", ""),
            success=bool(data.get("success", False)),
            detail=data.get("detail", ""),
            flow_id=data.get("flow_id"),
            duration=data.get("duration"),
        )


# ── 讀寫紀錄檔，壞掉或不存在都當作空清單，不讓 /info 直接掛掉 ──────────────────────

def _load() -> list[HistoryEntry]:
    if not config.QB_HISTORY_FILE.exists():
        return []
    try:
        raw = json.loads(config.QB_HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [HistoryEntry.from_dict(item) for item in raw]


def _save(entries: list[HistoryEntry]) -> None:
    config.QB_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.QB_HISTORY_FILE.write_text(
        json.dumps([asdict(e) for e in entries], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def record(
    *,
    action: str,
    user: str,
    target: str,
    success: bool,
    detail: str,
    flow_id: str | None = None,
    duration: float | None = None,
) -> None:
    """新增一筆操作紀錄，超過 QB_HISTORY_KEEP 筆自動砍掉最舊的。"""
    entries = _load()
    entries.append(HistoryEntry(
        time=datetime.now().strftime("%Y-%m-%d %H:%M"),
        action=action,
        user=user,
        target=target,
        success=success,
        detail=detail,
        flow_id=flow_id,
        duration=duration,
    ))
    entries = entries[-config.QB_HISTORY_KEEP:]
    _save(entries)


def recent(limit: int = 10) -> list[HistoryEntry]:
    """取得最近 limit 筆，新到舊排序。"""
    return list(reversed(_load()))[:limit]
