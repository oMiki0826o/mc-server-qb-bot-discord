"""
config.py

Modification():

- 移除 RCON 相關設定（QB_RCON_HOST／QB_RCON_PORT／QB_RCON_PASSWORD／
  QB_RCON_WARN_SECONDS）：這套功能判定為用不到的設計，直接砍掉，
  不再是「選填但沒人用」的殘留設定。
- QB_BACKUP_DIR 改為選填：預設值改成專案內的
  database/minecraft/Backup/，不用再手動填一個外部絕對路徑；不管是
  用預設值還是自己填，程式啟動時都會自動建立資料夾，不存在也不會
  出錯。
- QB_HISTORY_FILE／QB_STOP_TIMEOUT／QB_HISTORY_KEEP／
  QB_BACKUP_PREFIX／QB_PRE_RESTORE_PREFIX 一併改為選填並給預設值：
  這些填錯了頂多是行為不如預期，不像 QB_SERVER_DIR 那種填錯會讓
  備份／回復動到錯資料夾、覆水難收的等級，所以放寬成「沒填就用
  預設值」，降低第一次部署要填的欄位數量。
- 新增 QB_SCRIPT_DIR：core/qb/scripts/ 底下 shell script 的所在
  目錄，預設是專案內建的 core/qb/scripts，開機時會確認裡面該有的
  script 都存在，缺一個就直接拒絕啟動並列出缺項。
- 新增每日自動備份相關設定：QB_SCHEDULE_FILE（開關存放位置）、
  QB_AUTO_BACKUP_HOUR／QB_AUTO_BACKUP_MINUTE／QB_AUTO_BACKUP_TZ
  （幾點觸發、哪個時區）、QB_AUTO_BACKUP_PREFIX（自動備份的檔名
  前綴，跟手動備份分開好辨識）、QB_AUTO_BACKUP_KEEP（只保留最近
  幾份自動備份，避免每天執行、長期下來把硬碟塞滿）。
- OWNER_ID／QB_CHANNEL_ID／QB_ROLE_ID 改用共用的整數解析函式，
  格式錯誤時會直接說明是哪個變數、目前的值是什麼，而不是丟一個
  看不懂的 ValueError traceback。

Description():

- 一律用 python-dotenv 讀取專案根目錄的 .env。
- 必填的環境變數：DISCORD_TOKEN／OWNER_ID／QB_CHANNEL_ID／
  QB_ROLE_ID／QB_SERVER_DIR／QB_SESSION_NAME／QB_START_COMMAND。
  這幾項要嘛沒有安全的預設值（Token、Discord ID），要嘛填錯會讓
  備份／回復這種做錯就回不去的操作動到錯地方（QB_SERVER_DIR／
  QB_SESSION_NAME／QB_START_COMMAND），所以少一個都直接拒絕啟動，
  一次列出全部缺項，不會用猜的值偷偷跑起來。
- 其餘設定都選填，沒填就用本檔案集中定義的預設值。
- 相對路徑一律視為相對於本檔案所在的專案根目錄，跟啟動時的工作
  目錄無關。
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

load_dotenv()

# ── 專案根目錄：以本檔案位置為準 ──────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent

# ── 各項可選設定的預設值，集中寫在這裡，下面不要散著出現魔術數字 ──────────────────────
_DEFAULT_STOP_TIMEOUT = 120
_DEFAULT_HISTORY_KEEP = 50
_DEFAULT_BACKUP_PREFIX = "backup"
_DEFAULT_PRE_RESTORE_PREFIX = "prerestore"
_DEFAULT_BACKUP_DIR = PROJECT_ROOT / "database" / "minecraft" / "Backup"
_DEFAULT_HISTORY_FILE = PROJECT_ROOT / "database" / "qb" / "history.json"
_DEFAULT_SCRIPT_DIR = PROJECT_ROOT / "core" / "qb" / "scripts"
_DEFAULT_SCHEDULE_FILE = PROJECT_ROOT / "database" / "qb" / "schedule.json"
_DEFAULT_AUTO_BACKUP_HOUR = 4
_DEFAULT_AUTO_BACKUP_MINUTE = 0
_DEFAULT_AUTO_BACKUP_PREFIX = "auto"
_DEFAULT_AUTO_BACKUP_KEEP = 7

# ── 必填的環境變數：填錯會導致資料損毀或連錯身分，一項都不能少 ──────────────────────
_REQUIRED = [
    "DISCORD_TOKEN",
    "OWNER_ID",
    "QB_CHANNEL_ID",
    "QB_ROLE_ID",
    "QB_SERVER_DIR",
    "QB_SESSION_NAME",
    "QB_START_COMMAND",
]

_missing = [key for key in _REQUIRED if not os.getenv(key)]
if _missing:
    sys.exit(
        "缺少以下環境變數，請檢查 .env：\n"
        + "\n".join(f"- {key}" for key in _missing)
    )


def _required_int_env(key: str) -> int:
    """讀取必填的整數型環境變數，格式錯誤就直接說清楚並拒絕啟動。"""
    raw = os.getenv(key, "")
    try:
        return int(raw)
    except ValueError:
        sys.exit(f"環境變數 {key} 必須是整數，目前是：{raw!r}")


def _int_env(key: str, default: int) -> int:
    """讀取選填的整數型環境變數，沒填用預設值，格式錯誤就拒絕啟動。"""
    raw = os.getenv(key)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        sys.exit(f"環境變數 {key} 必須是整數，目前是：{raw!r}")


def _path_env(key: str, default: Path) -> Path:
    """讀取選填的路徑型環境變數，沒填用預設值；相對路徑一律視為相對於專案根目錄。"""
    raw = os.getenv(key)
    if not raw:
        return default
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _timezone_env(key: str) -> tzinfo:
    """讀取選填的時區名稱（例如 Asia/Taipei），沒填就用系統目前的本地時區。"""
    raw = os.getenv(key)
    if not raw:
        return datetime.now().astimezone().tzinfo
    try:
        return ZoneInfo(raw)
    except ZoneInfoNotFoundError:
        sys.exit(f"環境變數 {key} 不是合法的時區名稱：{raw!r}（例如 Asia/Taipei）")


TOKEN = os.getenv("DISCORD_TOKEN", "")
GEMINI_API = os.getenv("GEMINI_API", "")  # 目前沒有 cog 在用，選填，保留給未來擴充

OWNER_ID = _required_int_env("OWNER_ID")

# ── qb 頻道／身分組限制 ──────────────────────
QB_CHANNEL_ID = _required_int_env("QB_CHANNEL_ID")
QB_ROLE_ID = _required_int_env("QB_ROLE_ID")

# ── 伺服器生命週期設定 ──────────────────────
QB_SERVER_DIR = Path(os.getenv("QB_SERVER_DIR", ""))
QB_SESSION_NAME = os.getenv("QB_SESSION_NAME", "")
QB_START_COMMAND = os.getenv("QB_START_COMMAND", "")
QB_STOP_TIMEOUT = _int_env("QB_STOP_TIMEOUT", _DEFAULT_STOP_TIMEOUT)

# ── script runner 設定 ──────────────────────
QB_SCRIPT_DIR = _path_env("QB_SCRIPT_DIR", _DEFAULT_SCRIPT_DIR)

# ── 備份／回復設定 ──────────────────────
QB_BACKUP_DIR = _path_env("QB_BACKUP_DIR", _DEFAULT_BACKUP_DIR)
QB_BACKUP_PREFIX = os.getenv("QB_BACKUP_PREFIX") or _DEFAULT_BACKUP_PREFIX
QB_PRE_RESTORE_PREFIX = os.getenv("QB_PRE_RESTORE_PREFIX") or _DEFAULT_PRE_RESTORE_PREFIX

# ── /info 操作紀錄設定 ──────────────────────
QB_HISTORY_FILE = _path_env("QB_HISTORY_FILE", _DEFAULT_HISTORY_FILE)
QB_HISTORY_KEEP = _int_env("QB_HISTORY_KEEP", _DEFAULT_HISTORY_KEEP)

# ── 每日自動備份設定 ──────────────────────
QB_SCHEDULE_FILE = _path_env("QB_SCHEDULE_FILE", _DEFAULT_SCHEDULE_FILE)
QB_AUTO_BACKUP_HOUR = _int_env("QB_AUTO_BACKUP_HOUR", _DEFAULT_AUTO_BACKUP_HOUR)
QB_AUTO_BACKUP_MINUTE = _int_env("QB_AUTO_BACKUP_MINUTE", _DEFAULT_AUTO_BACKUP_MINUTE)
QB_AUTO_BACKUP_TZ = _timezone_env("QB_AUTO_BACKUP_TZ")
QB_AUTO_BACKUP_PREFIX = os.getenv("QB_AUTO_BACKUP_PREFIX") or _DEFAULT_AUTO_BACKUP_PREFIX
QB_AUTO_BACKUP_KEEP = _int_env("QB_AUTO_BACKUP_KEEP", _DEFAULT_AUTO_BACKUP_KEEP)

# ── 執行期需要用到的目錄，開機時就先確保存在，不要等到真的要寫入才發現沒建 ──────────────────────
QB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
QB_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
QB_SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── script 目錄本身跟著專案走，缺檔多半代表部署時漏複製，直接拒絕啟動並列清楚 ──────────────────────
_EXPECTED_SCRIPTS = (
    "start.sh", "stop.sh", "restart.sh", "status.sh", "save.sh", "command.sh",
)
_missing_scripts = [
    name for name in _EXPECTED_SCRIPTS if not (QB_SCRIPT_DIR / name).is_file()
]
if _missing_scripts:
    sys.exit(
        f"QB_SCRIPT_DIR（{QB_SCRIPT_DIR}）底下缺少以下 script：\n"
        + "\n".join(f"- {name}" for name in _missing_scripts)
    )
