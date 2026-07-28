"""
core/qb/server.py

Modification():

- 全面改為呼叫 core/qb/scripts/ 底下的 shell script（透過
  core/qb/process.py 的 Flow／run_script），不再由這支檔案自己組
  tmux 指令。「怎麼判斷伺服器活著、怎麼關、怎麼開」全部收斂到
  scripts/ 底下，以後要換掉行程監控方式（例如改用 systemd 或
  docker），只需要換掉對應的 script，這支檔案完全不用動。
- 新增 restart()：依序呼叫 stop() 與 start()，並自己取得
  state.server_lock，適合被獨立呼叫。若要在「已經持有 server_lock
  的流程」裡重啟（例如 backup.py 的備份流程），請直接照順序呼叫
  stop()／start()，不要呼叫 restart()——stop()／start() 都不會自己
  搶 server_lock，才不會跟外層流程已經持有的鎖形成死結。
- 新增 send_command()：對正在執行的伺服器送一行主控台指令，以後要
  加 /say、/whitelist 這類指令時，不用再讓 cogs 直接碰 tmux。
- status() 改為回傳 core.qb.state.State，不是單純的布林值：如果目前
  有備份／回復／重啟之類的流程在跑，回傳的就是那個流程當下的狀態
  （例如 BackingUp，或流程內部呼叫 stop() 時短暫看到 Stopping）；
  沒有流程在跑，才回報 Running／Stopped／Failed。is_running() 保留
  成單純的布林版本，給只在乎「現在是否在跑」、不在乎流程細節的地方
  用（例如 send_command() 自己的前置檢查）。
- 所有函式改成 async：底層都要呼叫子行程，統一成 async 介面，呼叫端
  不用去記哪個函式是同步、哪個是非同步。
- 移除直接呼叫 subprocess／tmux 的程式碼，改為透過 process.py。

Description():

- is_running()：純粹問「tmux session 現在還在嗎」，不牽涉狀態機。
- status()：給 /info 這類指令用的完整狀態。
- start()／stop()：伺服器生命週期最基本的兩個動作，不處理鎖，由
  呼叫端（backup.py 或未來的獨立指令）自行決定要不要保護。
- restart()：獨立可用的重啟，自帶 server_lock 保護。
- send_command(command)：對執行中的伺服器送一行主控台指令。
- 每個函式都接受選填的 flow 參數：不給就自己開一個新的 Flow；在
  backup／restore 這類多步驟流程裡，把同一個 Flow 往下傳，log 裡
  就能看到整段操作共用同一個 Flow ID。
- 刪除執行任意 Console 指令
"""

from __future__ import annotations

import config
from core.qb import state
from core.qb.exceptions import ServerError, TMUXError
from core.qb.process import Flow
from core.qb.state import State


async def is_running(*, flow: Flow | None = None) -> bool:
    """純粹問 tmux session 是否存在，不牽涉狀態機。"""
    f = flow or Flow("server.status")
    result = await f.run_script("status.sh", check=False)
    return result.success


async def status(*, flow: Flow | None = None) -> State:
    """給 /info 用的完整狀態：優先回報進行中的流程，其次才是單純的線上／離線。"""
    active = state.current_flow()
    if active is not None:
        return active
    if await is_running(flow=flow):
        return State.RUNNING
    return State.FAILED if state.has_failed() else State.STOPPED


async def start(*, flow: Flow | None = None) -> None:
    """啟動伺服器。不處理鎖，呼叫端自行決定是否需要保護。"""
    f = flow or Flow("server.start")
    with state.flow(State.STARTING):
        try:
            await f.run_script("start.sh")
        except TMUXError as exc:
            raise ServerError(f"啟動伺服器失敗：{exc}") from exc


async def stop(*, flow: Flow | None = None) -> None:
    """關閉伺服器：save-all -> stop -> 等待 session 消失，邏輯全在 stop.sh 裡。"""
    f = flow or Flow("server.stop")
    with state.flow(State.STOPPING):
        try:
            await f.run_script("stop.sh", timeout=config.QB_STOP_TIMEOUT + 30)
        except TMUXError as exc:
            raise ServerError(f"關閉伺服器失敗或逾時：{exc}") from exc


async def restart(*, flow: Flow | None = None) -> None:
    """獨立可用的完整重啟。內部會取得 server_lock，不要在已經持有
    server_lock 的流程裡呼叫（會自己等自己，永遠等不到）。"""
    f = flow or Flow("server.restart")
    async with state.guarded((state.server_lock, "伺服器目前正被其他作業占用，請稍後再試")):
        await stop(flow=f)
        await start(flow=f)