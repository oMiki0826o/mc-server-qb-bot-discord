"""
core/qb/server.py

Modification():

- 新增 tmux session 控制：確認伺服器活著沒、送 stop 指令等到它正常關掉、
  開新 session 把伺服器拉起來。Linux／macOS 都靠系統裝好的 tmux，
  沒有額外相依，也不用去猜 BSD／GNU 版工具參數的差異。

Description():

- 假設 MC 伺服器是跑在一個 tmux session（QB_SESSION_NAME）裡，
  session 裡直接執行啟動指令（QB_START_COMMAND），不是包一層 bash
  再把 java 丟到背景——這樣 session 存活時間才會等於伺服器存活時間，
  is_running() 才靠得住。如果實際架設方式不是這樣，換掉這支檔案就好，
  其他地方不用動。
"""

from __future__ import annotations

import asyncio
import subprocess
from typing import Optional

import config


# ── 檢查 tmux session 是否還在 ──────────────────────

def is_running() -> bool:
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", config.QB_SESSION_NAME],
            capture_output=True,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0


# ── 送 stop 指令，等到 session 消失或逾時 ──────────────────────

async def stop(timeout: Optional[int] = None) -> bool:
    if not is_running():
        return True

    timeout = timeout or config.QB_STOP_TIMEOUT
    subprocess.run(["tmux", "send-keys", "-t", config.QB_SESSION_NAME, "stop", "Enter"])

    waited = 0
    while is_running():
        if waited >= timeout:
            return False
        await asyncio.sleep(2)
        waited += 2

    return True


# ── 開新 session 把伺服器拉起來 ──────────────────────

def start() -> bool:
    if is_running():
        return True

    try:
        subprocess.run([
            "tmux", "new-session", "-d",
            "-s", config.QB_SESSION_NAME,
            "-c", str(config.QB_SERVER_DIR),
            config.QB_START_COMMAND,
        ])
    except FileNotFoundError:
        return False

    return is_running()
