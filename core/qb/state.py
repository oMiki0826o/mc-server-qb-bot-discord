"""
core/qb/state.py

Modification():

- 新增本檔案：定義 qb 系統的狀態機（State）與三把獨立的鎖
  （server_lock／backup_lock／restore_lock），取代原本 cogs/qb.py
  裡那把「make 跟 back 共用同一把」的單一 Lock。

Description():

- State：目前這個系統正在做什麼，給 /info 這類指令顯示用，一共
  八種：Idle／Starting／Running／Stopping／Stopped／BackingUp／
  Restoring／Failed。
- flow(state)：進入一段具名流程時使用的情境管理器，離開時自動還原
  成進入前的狀態，可以巢狀使用。例如 BackingUp 流程內部呼叫
  server.stop() 時會短暫疊上 Stopping，stop() 結束後自動退回
  BackingUp，/info 在這段期間看到的永遠是「目前實際在做的事」。
- current_flow()：目前最新（也就是巢狀最內層）進行中的流程狀態，
  沒有任何流程在跑就回傳 None；沒有流程時要顯示 Running／Stopped／
  Failed 何者，交由呼叫端（server.status()）自行判斷，state.py
  本身不去猜「沒有流程＝目前是哪種狀態」。
- has_failed()：最近一次生命週期操作（最外層的 flow）是否以例外
  收場，供 status() 在沒有流程進行、但上次操作沒有正常結束時回報
  Failed；只要有一次最外層流程順利跑完，就會清除這個旗標。
- server_lock／backup_lock／restore_lock：三把獨立的鎖。backup／
  restore 各自的鎖讓「已經有一個備份在跑」這類訊息可以在流程一開始
  就立刻回報；server_lock 則是兩者都會再往下取的鎖，確保備份與回復
  不會同時動到伺服器與存檔（取鎖順序固定是「自己的鎖→server_lock」，
  兩邊順序一致，不會互相等待造成死結）。
- guarded(*locks)：依序嘗試「非阻塞」取得多把鎖，任何一把已經被
  占用就立刻丟 QBBusyError（帶指定訊息），不會讓 Discord 指令傻等
  一個可能要跑好幾分鐘的鎖。全部取到才進入本體，離開時依相反順序
  釋放；由於 asyncio 是合作式排程，「檢查 locked() 再 acquire()」
  中間不會被其他工作插隊，這個非阻塞判斷是安全的。
"""

from __future__ import annotations

import asyncio
import contextlib
from enum import Enum

from core.qb.exceptions import QBBusyError


class State(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    BACKING_UP = "backing_up"
    RESTORING = "restoring"
    FAILED = "failed"


# ── 進行中流程的堆疊：空堆疊代表「目前沒有任何流程在跑」 ──────────────────────
_flow_stack: list[State] = []
_failed: bool = False


@contextlib.contextmanager
def flow(current: State):
    """進入一段具名流程，離開時（不管成功或例外）都還原成進入前的狀態。"""
    global _failed
    _flow_stack.append(current)
    try:
        yield
    except Exception:
        _failed = True
        raise
    else:
        if len(_flow_stack) == 1:
            _failed = False
    finally:
        _flow_stack.pop()


def current_flow() -> State | None:
    """目前進行中的流程狀態，沒有流程在跑就回傳 None。"""
    return _flow_stack[-1] if _flow_stack else None


def has_failed() -> bool:
    """最近一次最外層流程是否以例外收場（尚未被後續成功的流程清除）。"""
    return _failed


# ── 三把獨立的鎖：各自守住 backup／restore 的「是否已經有同類作業在跑」，
#    server_lock 則是兩邊都會再往下取的鎖，真正保護伺服器與存檔本身 ──────────────────────
server_lock = asyncio.Lock()
backup_lock = asyncio.Lock()
restore_lock = asyncio.Lock()


@contextlib.asynccontextmanager
async def guarded(*locks: tuple[asyncio.Lock, str]):
    """依序非阻塞取得多把鎖，任何一把被占用就立刻丟 QBBusyError。"""
    acquired: list[asyncio.Lock] = []
    try:
        for lock, busy_message in locks:
            if lock.locked():
                raise QBBusyError(busy_message)
            await lock.acquire()
            acquired.append(lock)
        yield
    finally:
        for lock in reversed(acquired):
            lock.release()
