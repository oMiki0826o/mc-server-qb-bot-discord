"""
core/qb/rcon.py

Modification():

- 新增最小可用的 RCON 用戶端（Source RCON 協定，Minecraft 內建支援這套），
  純手刻、不額外依賴套件。拿來在關伺服器前廣播提醒玩家，
  以及讓 !!info 能顯示真正在線的玩家，而不是只有 tmux session 死活。

Description():

- execute(command)：對伺服器送一個 RCON 指令，回傳伺服器的回應文字。
- warn_and_wait(message)：廣播一句話，等一段緩衝時間讓玩家看到再回傳。
- player_summary()：查詢目前線上玩家（list 指令）。
- 全部函式都不拋例外——RCON 沒設定、連不上、密碼錯誤，一律回傳 None
  或直接跳過。這是錦上添花的功能，不該讓備份／回復本身因為它失敗。
"""

from __future__ import annotations

import asyncio
import struct
from typing import Optional

import config

_AUTH = 3
_EXECCOMMAND = 2


# ── 有沒有設定 RCON，沒設定就不用白費力氣去連 ──────────────────────

def configured() -> bool:
    return bool(config.QB_RCON_HOST and config.QB_RCON_PORT and config.QB_RCON_PASSWORD)


# ── 打包送出一個 RCON 封包 ──────────────────────

async def _send(writer: asyncio.StreamWriter, request_id: int, packet_type: int, body: str) -> None:
    payload = struct.pack("<ii", request_id, packet_type) + body.encode("utf-8") + b"\x00\x00"
    writer.write(struct.pack("<i", len(payload)) + payload)
    await writer.drain()


# ── 讀一個 RCON 回應封包 ──────────────────────

async def _read(reader: asyncio.StreamReader) -> tuple[int, int, str]:
    size = struct.unpack("<i", await reader.readexactly(4))[0]
    payload = await reader.readexactly(size)
    request_id, packet_type = struct.unpack("<ii", payload[:8])
    body = payload[8:-2].decode("utf-8", errors="replace")
    return request_id, packet_type, body


# ── 送一個指令，拿伺服器的回應文字，任何狀況出錯都回傳 None ──────────────────────

async def execute(command: str, timeout: float = 5) -> Optional[str]:
    if not configured():
        return None

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(config.QB_RCON_HOST, config.QB_RCON_PORT),
            timeout=timeout,
        )
    except (OSError, asyncio.TimeoutError):
        return None

    try:
        await _send(writer, 1, _AUTH, config.QB_RCON_PASSWORD)
        request_id, _, _ = await asyncio.wait_for(_read(reader), timeout=timeout)
        if request_id == -1:
            return None

        await _send(writer, 2, _EXECCOMMAND, command)
        _, _, body = await asyncio.wait_for(_read(reader), timeout=timeout)
        return body
    except (OSError, asyncio.TimeoutError, struct.error):
        return None
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass


# ── 廣播訊息，等一段緩衝時間讓玩家看到再繼續 ──────────────────────

async def warn_and_wait(message: str, wait_seconds: Optional[int] = None) -> None:
    if not configured():
        return
    if await execute(f"say {message}") is not None:
        await asyncio.sleep(wait_seconds or config.QB_RCON_WARN_SECONDS)


# ── 查詢線上玩家 ──────────────────────

async def player_summary() -> Optional[str]:
    return await execute("list")
