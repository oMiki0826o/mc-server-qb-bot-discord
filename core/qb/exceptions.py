"""
core/qb/exceptions.py

Modification():

- 新增本檔案：qb 系統專用的例外階層，取代原本到處用
  tuple[bool, str] 或裸 Exception 傳遞失敗訊息的作法。呼叫端
  （cogs/qb.py）現在只需要 except QBError 就能穩穩接住所有 qb 系統
  丟出的錯誤，也可以視需要接更細的子類別給出更精準的訊息。
- 原本規劃中的 RCONError 已移除：RCON 整套功能（連線廣播、查詢
  線上玩家）判定為用不到的設計，一併從專案裡刪除，不再保留對應的
  例外類別。

Description():

- QBError：所有 qb 系統例外的共同基底類別，其餘例外都繼承自這裡。
- TMUXError：呼叫 core/qb/scripts/ 底下的 script 失敗（找不到檔案、
  沒有執行權限、逾時、非零 returncode）。只在 core/qb/process.py
  產生，正常情況不會直接跑到 cogs 層——server.py 會接住並轉成
  ServerError 再往上丟。
- ServerError：伺服器啟動／關閉／重啟／送主控台指令失敗。
- BackupError：建立備份失敗。
- RestoreError：回復備份失敗。
- QBBusyError：搶鎖失敗，代表已經有其他備份／回復／伺服器操作在
  進行中。這不算「操作本身出錯」，獨立成一種例外，讓呼叫端可以給出
  「請稍後再試」而不是「出錯了」這種更貼切的訊息。
"""

from __future__ import annotations


class QBError(Exception):
    """qb 系統所有自訂例外的共同基底類別。"""


class TMUXError(QBError):
    """執行 core/qb/scripts/ 底下的 script 時發生錯誤（找不到、逾時、非零 returncode）。"""


class ServerError(QBError):
    """Minecraft 伺服器啟動／關閉／重啟／送主控台指令失敗。"""


class BackupError(QBError):
    """建立備份失敗。"""


class RestoreError(QBError):
    """回復備份失敗。"""


class QBBusyError(QBError):
    """目前已有其他 qb 操作在進行中，搶鎖失敗。"""
