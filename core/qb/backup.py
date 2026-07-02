"""
core/qb/backup.py

Modification():

- 新增備份／回復的檔案層操作：壓縮、解壓、檔名清理、容量格式化、
  備份清單查詢。跟「伺服器要不要關」這件事完全分開，那是 server.py 管的。
- restore() 用「先解壓到暫存資料夾，成功才整批換上」的方式，
  避免解壓到一半失敗把原本的世界資料夾弄爛；換上去之前的舊資料夾
  是真的砍掉，回不去，所以呼叫端記得在這之前自己先存一份快照
  （cogs/qb.py 就是這樣做的）。
- extractall() 補上 filter="data"：Python 3.12 開始不帶 filter 參數
  解壓會跳 DeprecationWarning，3.14 起預設就是這個過濾器（會擋掉
  特殊檔案類型、外部符號連結等）。備份本來就是 bot 自己壓的，
  內容可信，用 "data" 過濾器單純是提前對齊未來版本的預設行為，
  不影響現在的解壓結果。

Description():

- create(filename)：把 QB_SERVER_DIR 整包壓成 tar.gz 放進 QB_BACKUP_DIR。
- restore(filename)：把指定備份解壓回去蓋掉 QB_SERVER_DIR。
- 兩個都是同步、會卡住 event loop 的操作，呼叫端請自己丟 asyncio.to_thread。
- 全部用 Python 內建的 tarfile／pathlib，不呼叫外部 tar／du 指令，
  macOS 跟 Linux 的行為才會一致。
"""

from __future__ import annotations

import re
import shutil
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import config


# ── 檔名清理：踢掉路徑跳脫與奇怪字元，只留字母數字底線和連字號 ──────────────────────

def sanitize_filename(name: str) -> str:
    name = name.strip().removesuffix(".tar.gz")
    name = re.sub(r"[^\w\-]", "_", name)
    return name.strip("_") or "backup"


# ── 產生時間戳記檔名，prefix 沒給就用預設的備份 prefix ──────────────────────

def default_filename(prefix: Optional[str] = None) -> str:
    prefix = prefix or config.QB_BACKUP_PREFIX
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M')}"


# ── bytes 轉成人看得懂的容量，格式跟手動 tar 完看到的一樣（例：8.6G） ──────────────────────

def human_size(num_bytes: float) -> str:
    for unit in ("B", "K", "M", "G", "T"):
        if num_bytes < 1024:
            return f"{int(num_bytes)}B" if unit == "B" else f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}P"


# ── 檔名轉實際備份路徑，順便擋掉跳出 QB_BACKUP_DIR 的怪路徑 ──────────────────────

def backup_path(filename: str) -> Path:
    path = (config.QB_BACKUP_DIR / f"{filename}.tar.gz").resolve()
    if config.QB_BACKUP_DIR.resolve() not in path.parents:
        raise ValueError("檔名不合法")
    return path


def exists(filename: str) -> bool:
    return backup_path(filename).exists()


# ── 列出現有備份，新到舊排序 ──────────────────────

def list_backups() -> list[Path]:
    if not config.QB_BACKUP_DIR.exists():
        return []
    return sorted(
        config.QB_BACKUP_DIR.glob("*.tar.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


# ── 建立備份（同步，呼叫端請丟 thread） ──────────────────────

def create(filename: str) -> tuple[bool, str]:
    config.QB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = backup_path(filename)

    try:
        with tarfile.open(target, "w:gz") as tar:
            tar.add(config.QB_SERVER_DIR, arcname=".")
    except Exception as exc:
        target.unlink(missing_ok=True)
        return False, str(exc)

    return True, human_size(target.stat().st_size)


# ── 回復備份（同步，呼叫端請丟 thread） ──────────────────────

def restore(filename: str) -> tuple[bool, str]:
    source = backup_path(filename)
    if not source.exists():
        return False, "找不到這個備份檔"

    temp_dir = config.QB_SERVER_DIR.parent / ".qb_restore_tmp"
    old_dir = config.QB_SERVER_DIR.parent / ".qb_restore_old"
    shutil.rmtree(temp_dir, ignore_errors=True)
    shutil.rmtree(old_dir, ignore_errors=True)

    try:
        temp_dir.mkdir(parents=True)
        with tarfile.open(source, "r:gz") as tar:
            tar.extractall(temp_dir, filter="data")
    except Exception as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, str(exc)

    try:
        config.QB_SERVER_DIR.rename(old_dir)
        temp_dir.rename(config.QB_SERVER_DIR)
    except Exception as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, str(exc)

    shutil.rmtree(old_dir, ignore_errors=True)
    return True, "回復完成"
