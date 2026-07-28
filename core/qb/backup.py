"""
core/qb/backup.py

Modification():

- 原本備份／回復的檔案層操作（壓縮、解壓、檔名清理、容量格式化、
  備份清單查詢）保留，只是把回傳值從 tuple[bool, str] 改成「成功就
  回傳結果、失敗就丟 BackupError／RestoreError」，跟專案其他地方
  統一用例外處理失敗，呼叫端不用每一步都手動 if not ok。
- 新增 run_backup()／run_restore()：把原本寫在 cogs/qb.py 裡的完整
  流程（關伺服器 -> 動檔案 -> 開伺服器，中間還要取鎖、記錄時間軸、
  更新狀態機、寫操作紀錄）搬進這裡，變成跟 Discord 完全無關的兩個
  函式。cogs/qb.py 現在只需要呼叫這兩個函式、把過程中的訊息轉貼到
  Discord，商業邏輯跟指令介面正式分開；之後要加排程自動備份這種
  「不是從 Discord 指令觸發」的入口，也能直接重用同一份流程，不用
  重寫一次。
- run_backup()／run_restore() 都接受選填的 progress 回呼（收到一段
  文字訊息時要做什麼，由呼叫端決定，例如編輯 Discord 訊息），本檔案
  完全不 import discord。
- 備份／回復都改用 core/qb/state.py 的鎖（backup_lock／restore_lock
  加上 server_lock）取代原本 cogs/qb.py 裡那把兩個指令共用的單一
  Lock，「已經有備份在跑」跟「已經有回復在跑」現在是各自獨立、
  訊息也更精準的檢查。
- QB_BACKUP_DIR 不存在時自動建立的邏輯移到 config.py 統一處理，本
  檔案不用再自己處理「萬一資料夾不見了」的邊界情況（create() 裡仍
  保留一次防禦性的 mkdir，避免資料夾在執行期間被外部刪除）。
- 新增 rotate_auto_backups()：只清理「檔名前綴符合自動備份」的舊
  備份，只保留最近幾份，供每日自動備份使用；手動備份的檔名前綴不同，
  不會被誤刪。

Description():

- sanitize_filename()／default_filename()／human_size()／
  backup_path()／exists()／list_backups()：跟檔名、路徑、容量顯示
  有關的小工具，彼此獨立，沒有副作用。
- create(filename)：純粹的壓縮動作，把 QB_SERVER_DIR 整包壓成
  tar.gz，回傳人看得懂的容量字串，失敗就丟 BackupError 並清掉壓到
  一半的檔案。
- restore(filename)：純粹的解壓動作，「先解壓到暫存資料夾，成功才
  整批換上」，失敗就丟 RestoreError，原本的世界資料夾不會被動到。
- rotate_auto_backups(prefix, keep)：砍掉超過 keep 份、檔名符合
  prefix 的舊備份，回傳被刪除的路徑清單。
- run_backup(filename, operator, progress=None)：完整備份流程——
  取鎖 -> 關閉伺服器 -> 壓縮 -> 重啟伺服器 -> 寫入操作紀錄，回傳
  BackupOutcome。
- run_restore(filename, operator, progress=None)：完整回復流程——
  取鎖 -> 關閉伺服器 -> 自動存一份回復前快照 -> 解壓回復 -> 重啟
  伺服器 -> 寫入操作紀錄，回傳 RestoreOutcome。
- 兩個 run_* 函式都用同一個 Flow 貫穿全程，log 裡看得到完整時間軸；
  也都會不論成功失敗都呼叫 history.record()，並在最後呼叫
  flow.finish() 寫一行總結。
"""

from __future__ import annotations

import asyncio
import re
import shutil
import tarfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import config
from core.qb import history, server, state
from core.qb.exceptions import BackupError, RestoreError
from core.qb.process import Flow
from core.qb.state import State

ProgressCallback = Callable[[str], Awaitable[None]]


# ── 檔名清理：踢掉路徑跳脫與奇怪字元，只留字母數字底線和連字號 ──────────────────────

def sanitize_filename(name: str) -> str:
    name = name.strip()
    if name.endswith(".tar.gz"):
        name = name[: -len(".tar.gz")]
    name = re.sub(r"[^\w\-]", "_", name)
    return name.strip("_") or "backup"


# ── 產生時間戳記檔名，prefix 沒給就用預設的手動備份 prefix ──────────────────────

def default_filename(prefix: str | None = None) -> str:
    prefix = prefix or config.QB_BACKUP_PREFIX
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M')}"


# ── bytes 轉成人看得懂的容量 ──────────────────────

def human_size(num_bytes: float) -> str:
    for unit in ("B", "K", "M", "G", "T"):
        if num_bytes < 1024:
            return f"{int(num_bytes)}B" if unit == "B" else f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}P"


# ── 檔名轉實際備份路徑，順便擋掉跳出 QB_BACKUP_DIR 的怪路徑 ──────────────────────

def backup_path(filename: str) -> Path:
    root = config.QB_BACKUP_DIR.resolve()
    path = (config.QB_BACKUP_DIR / f"{filename}.tar.gz").resolve()
    if root != path.parent:
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


# ── 建立備份（同步、會卡住 event loop，呼叫端請丟到 thread 執行） ──────────────────────

def create(filename: str) -> str:
    config.QB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = backup_path(filename)

    try:
        with tarfile.open(target, "w:gz") as tar:
            tar.add(config.QB_SERVER_DIR, arcname=".")
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise BackupError(str(exc)) from exc

    return human_size(target.stat().st_size)


# ── 回復備份（同步、會卡住 event loop，呼叫端請丟到 thread 執行） ──────────────────────

def restore(filename: str) -> None:
    source = backup_path(filename)
    if not source.exists():
        raise RestoreError("找不到這個備份檔")

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
        raise RestoreError(str(exc)) from exc

    try:
        config.QB_SERVER_DIR.rename(old_dir)
        temp_dir.rename(config.QB_SERVER_DIR)
    except Exception as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RestoreError(str(exc)) from exc

    shutil.rmtree(old_dir, ignore_errors=True)


# ── 只清理符合前綴的舊備份，供自動備份使用 ──────────────────────

def rotate_auto_backups(prefix: str, keep: int) -> list[Path]:
    matched = [p for p in list_backups() if p.name.startswith(f"{prefix}_")]
    removed = matched[keep:]
    for path in removed:
        path.unlink(missing_ok=True)
    return removed


# ── 流程結果 ──────────────────────

@dataclass(frozen=True)
class BackupOutcome:
    filename: str
    size: str
    flow_id: str
    duration: float


@dataclass(frozen=True)
class RestoreOutcome:
    filename: str
    snapshot: str
    flow_id: str
    duration: float


async def _report(progress: ProgressCallback | None, text: str) -> None:
    if progress is not None:
        await progress(text)


# ── 完整備份流程：關閉伺服器 -> 壓縮 -> 重啟伺服器 ──────────────────────

async def run_backup(
    filename: str,
    *,
    operator: str,
    progress: ProgressCallback | None = None,
) -> BackupOutcome:
    f = Flow("qb.make")
    try:
        async with state.guarded(
            (state.backup_lock, "目前已經有備份作業在進行中，請稍後再試"),
            (state.server_lock, "伺服器目前正被其他作業占用，請稍後再試"),
        ):
            with state.flow(State.BACKING_UP):
                await _report(progress, "關閉伺服器中...")
                await server.stop(flow=f)

                await _report(progress, "壓縮中...")
                with f.step("壓縮"):
                    size = await asyncio.to_thread(create, filename)

                await _report(progress, "重啟伺服器中...")
                await server.start(flow=f)
    except Exception as exc:
        f.finish(success=False)
        history.record(
            action="make", user=operator, target=filename,
            success=False, detail=str(exc),
            flow_id=f.id, duration=f.elapsed,
        )
        raise

    f.finish(success=True)
    history.record(
        action="make", user=operator, target=filename,
        success=True, detail=f"備份完成，大小 {size}",
        flow_id=f.id, duration=f.elapsed,
    )
    return BackupOutcome(filename=filename, size=size, flow_id=f.id, duration=f.elapsed)


# ── 完整回復流程：關閉伺服器 -> 回復前快照 -> 解壓回復 -> 重啟伺服器 ──────────────────────

async def run_restore(
    filename: str,
    *,
    operator: str,
    progress: ProgressCallback | None = None,
) -> RestoreOutcome:
    f = Flow("qb.back")
    snapshot = default_filename(config.QB_PRE_RESTORE_PREFIX)

    try:
        async with state.guarded(
            (state.restore_lock, "目前已經有回復作業在進行中，請稍後再試"),
            (state.server_lock, "伺服器目前正被其他作業占用，請稍後再試"),
        ):
            with state.flow(State.RESTORING):
                await _report(progress, "關閉伺服器中...")
                await server.stop(flow=f)

                await _report(progress, f"關好了，先存一份回復前快照 `{snapshot}`...")
                with f.step("回復前快照"):
                    await asyncio.to_thread(create, snapshot)

                await _report(progress, "快照存好，開始回復...")
                with f.step("回復"):
                    await asyncio.to_thread(restore, filename)

                await _report(progress, "重啟伺服器中...")
                await server.start(flow=f)
    except Exception as exc:
        f.finish(success=False)
        history.record(
            action="back", user=operator, target=filename,
            success=False, detail=str(exc),
            flow_id=f.id, duration=f.elapsed,
        )
        raise

    f.finish(success=True)
    history.record(
        action="back", user=operator, target=filename,
        success=True, detail=f"回復完成（回復前快照：{snapshot}）",
        flow_id=f.id, duration=f.elapsed,
    )
    return RestoreOutcome(filename=filename, snapshot=snapshot, flow_id=f.id, duration=f.elapsed)
