"""
config.py

Modification():

- 新增 qb 備份／回復需要的設定：頻道、身分組、伺服器路徑、備份路徑、
  tmux session 名稱、啟動指令、關閉逾時秒數、備份檔名 prefix、
  操作紀錄檔設定。
- 全部設定改成一定要在 .env 裡填，config.py 本身不再放任何預設值。
  少填哪個變數，開機當下就直接報錯講清楚缺什麼，不會用一個猜的值
  偷偷跑起來（例如 QB_SERVER_DIR 沒填卻默默指向錯的資料夾，
  備份/回復這種動了就回不去的操作，寧可拒絕啟動也不要用錯路徑跑）。
  GEMINI_API 目前沒有任何 cog 在用，先保留成選填，沒填不擋開機。
- 新增 RCON 選填設定：關伺服器前廣播提醒玩家、!!info 顯示線上玩家用。
  這組是錦上添花的功能，MC 伺服器不一定開了 RCON，所以刻意不列進
  必填清單，沒填就讓相關功能自動跳過，不會擋住備份／回復這種
  核心功能的啟動。

Description():

- 全域設定入口，統一從 .env 讀。開機時一次檢查所有必填項目，
  缺什麼直接列出來，不用一個一個試。其他檔案都從這裡拿設定值，
  不要在別的地方寫死路徑或 ID。
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


# ── 必填的環境變數，缺一個都不給開機，一次列出全部缺項 ──────────────────────

_REQUIRED = [
    "DISCORD_TOKEN",
    "OWNER_ID",
    "QB_CHANNEL_ID",
    "QB_ROLE_ID",
    "QB_SERVER_DIR",
    "QB_BACKUP_DIR",
    "QB_SESSION_NAME",
    "QB_START_COMMAND",
    "QB_STOP_TIMEOUT",
    "QB_BACKUP_PREFIX",
    "QB_PRE_RESTORE_PREFIX",
    "QB_HISTORY_FILE",
    "QB_HISTORY_KEEP",
]

_missing = [key for key in _REQUIRED if not os.getenv(key)]
if _missing:
    sys.exit(
        "缺少以下環境變數，請檢查 .env：\n"
        + "\n".join(f"- {key}" for key in _missing)
    )


TOKEN = os.getenv("DISCORD_TOKEN", "")
GEMINI_API = os.getenv("GEMINI_API", "")  # 目前沒有 cog 在用，選填
OWNER_ID = int(os.getenv("OWNER_ID"))

# ── qb 備份／回復設定 ──────────────────────
QB_CHANNEL_ID = int(os.getenv("QB_CHANNEL_ID"))
QB_ROLE_ID = int(os.getenv("QB_ROLE_ID"))

QB_SERVER_DIR = Path(os.getenv("QB_SERVER_DIR"))
QB_BACKUP_DIR = Path(os.getenv("QB_BACKUP_DIR"))

QB_SESSION_NAME = os.getenv("QB_SESSION_NAME")
QB_START_COMMAND = os.getenv("QB_START_COMMAND")
QB_STOP_TIMEOUT = int(os.getenv("QB_STOP_TIMEOUT"))

QB_BACKUP_PREFIX = os.getenv("QB_BACKUP_PREFIX")
QB_PRE_RESTORE_PREFIX = os.getenv("QB_PRE_RESTORE_PREFIX")

# ── !!info 操作紀錄設定 ──────────────────────
QB_HISTORY_FILE = Path(os.getenv("QB_HISTORY_FILE"))
QB_HISTORY_KEEP = int(os.getenv("QB_HISTORY_KEEP"))

# ── RCON 設定（選填）：關伺服器前廣播提醒玩家、!!info 顯示線上玩家 ──────────────────────
# 沒填就自動略過，不影響備份／回復本身，所以不列進必填清單。
QB_RCON_HOST = os.getenv("QB_RCON_HOST", "")
QB_RCON_PORT = int(os.getenv("QB_RCON_PORT") or 0)
QB_RCON_PASSWORD = os.getenv("QB_RCON_PASSWORD", "")
QB_RCON_WARN_SECONDS = int(os.getenv("QB_RCON_WARN_SECONDS") or 10)
