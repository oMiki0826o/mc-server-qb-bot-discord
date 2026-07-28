"""
core/qb/scheduler.py

Modification():

- 新增本檔案：每日自動備份「開／關」這個設定的持久化存取。只管
  讀寫一個布林值，跟 Discord、跟「幾點觸發」都無關——幾點觸發是
  cogs/qb.py 裡用 discord.ext.tasks 排程決定的，這裡只回答
  「現在該不該做」。獨立成一支檔案，是因為這個開關要跨重啟保留，
  用一般的模組變數（像 core/qb/state.py 那樣）重開機就會消失，
  必須落地寫成檔案。

Description():

- is_enabled()：目前每日自動備份是否開啟，檔案不存在或壞掉一律
  視為關閉，不會讓 /qb schedule 或排程本身因為讀檔失敗而炸掉。
- set_enabled(value)：寫入開關狀態。
"""

from __future__ import annotations

import json

import config


def is_enabled() -> bool:
    path = config.QB_SCHEDULE_FILE
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return bool(data.get("enabled", False))


def set_enabled(value: bool) -> None:
    path = config.QB_SCHEDULE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"enabled": value}, ensure_ascii=False), encoding="utf-8")
