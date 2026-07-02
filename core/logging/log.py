"""
core/logging/log.py

Modification():

- 新增 _write_session_header()：每次啟動時寫入 session 分隔線（Python 版本、PID、時間）
- Singleton 保護、handler 重複掛載防護維持不變
- 壓制 discord 內部 logger 至 WARNING，避免 WebSocket 封包噪音

- 移除 attach_bot()：這個方法只設定了 self._bot 就沒有下文，文件字串
  宣稱要「掛載 DiscordErrorHandler 到 root logger」，但 DiscordErrorHandler
  這個類別整個專案從頭到尾都沒有定義過，也沒有任何地方呼叫過
  attach_bot()，是純粹的死程式碼。連帶把只為了它存在的 self._bot 屬性、
  TYPE_CHECKING 底下的 commands.Bot 型別匯入一起清掉。
- 修正檔頭路徑：原本寫 bot/core/logging/log.py，實際檔案在
  core/logging/log.py，兩者對不上，改成跟實際位置一致。
- 移除沒在用的 import sys。

"""

from __future__ import annotations

import logging
import os
import platform
import time
from datetime import datetime
from pathlib import Path

import discord

from .constants import DATE_FORMAT, LOG_DIR, LOG_FILE, LOG_FORMAT

# ── discord 內部 logger 壓制層級 ──────────────────────
_DISCORD_LOG_LEVEL = logging.WARNING

# ── 受壓制的 discord 子 logger 清單 ──────────────────────
_DISCORD_LOGGERS: tuple[str, ...] = (
    "discord",
    "discord.http",
    "discord.gateway",
    "discord.client",
    "discord.voice_client",
)


# ── 全域 Log 管理器（Singleton） ──────────────────────

class LogManager:
    """
    全域 Log 管理器（Singleton）。

    整個 process 生命週期內只存在一份實例，
    root logger 的 handler 只會被初始化一次。

    使用方式：
        log_manager = LogManager()
        logger = log_manager.get_logger("bot.music")
    """

    _instance:    LogManager | None = None
    _initialized: bool              = False

    def __new__(cls) -> LogManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # ── 已初始化則直接返回，避免重複 setup ──────────────────────
        if self._initialized:
            return

        LogManager._initialized = True
        self._had_errors: bool  = False
        self._start_time: float = time.monotonic()

        self._setup_logging()

    # ── logging 初始化（全域僅執行一次） ──────────────────────

    def _setup_logging(self) -> None:
        Path(LOG_DIR).mkdir(parents=True, exist_ok=True)

        root = logging.getLogger()

        # ── 防止重複掛載（掛在 root logger 物件上的旗標） ──────────────────────
        if getattr(root, "_logmanager_initialized", False):
            return
        root._logmanager_initialized = True  # type: ignore[attr-defined]

        formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

        # ── 終端輸出 handler ──────────────────────
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        # ── 檔案持久化 handler ──────────────────────
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)

        # ── error 追蹤 handler（標記本次是否有 ERROR） ──────────────────────
        tracker = _ErrorTracker(self)
        tracker.setLevel(logging.ERROR)

        root.setLevel(logging.DEBUG)
        root.addHandler(stream_handler)
        root.addHandler(file_handler)
        root.addHandler(tracker)

        # ── 壓制 discord 內部噪音 ──────────────────────
        for name in _DISCORD_LOGGERS:
            logging.getLogger(name).setLevel(_DISCORD_LOG_LEVEL)

        # ── 寫入本次 session 的啟動標頭 ──────────────────────
        self._write_session_header()

    # ── session 啟動標頭 ──────────────────────

    def _write_session_header(self) -> None:
        """
        每次 Bot 啟動時寫入一段標頭到 log，方便日後快速定位每次啟動的邊界。

        格式範例：
            ================================================
            Bot Session 開始
            時間    : 2026-06-29 20:08:46
            Python  : 3.11.13
            discord : 2.7.1
            OS      : macOS-14.5
            PID     : 12345
            ================================================
        """
        sep     = "=" * 48
        now_str = datetime.now().strftime(DATE_FORMAT)
        header  = (
            f"\n{sep}\n"
            f"Bot Session 開始\n"
            f"  時間        : {now_str}\n"
            f"  Python      : {platform.python_version()}\n"
            f"  discord.py  : {discord.__version__}\n"
            f"  OS          : {platform.system()}-{platform.release()}\n"
            f"  PID         : {os.getpid()}\n"
            f"{sep}"
        )

        # ── 寫入檔案（不透過 logging，避免格式被污染） ──────────────────────
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(header + "\n")
        except OSError:
            pass

        # ── 同步輸出到終端 ──────────────────────
        print(header)

    # ── 取得 logger ──────────────────────

    def get_logger(self, name: str = "bot") -> logging.Logger:
        return logging.getLogger(name)


# ── 內部 error 追蹤器 ──────────────────────

class _ErrorTracker(logging.Handler):
    """
    監聽 ERROR 以上等級的 log，標記 LogManager._had_errors。
    供關機報告判斷本次運行是否有錯誤。
    """

    def __init__(self, manager: LogManager) -> None:
        super().__init__()
        self._manager = manager

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno >= logging.ERROR:
            self._manager._had_errors = True