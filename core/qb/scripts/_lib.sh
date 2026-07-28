#!/usr/bin/env bash
# core/qb/scripts/_lib.sh
#
# Modification():
# - 新增本檔案：抽出所有 script 都會用到的共用邏輯（錯誤即停、
#   必要環境變數檢查、tmux 是否安裝、簡單的時間戳記 log 函式），
#   避免同一段檢查在六支 script 裡各寫一次。
#
# Description():
# - 這支檔案不是獨立執行的 script，是給其他 script 用 `source` 載入的
#   共用函式庫，本身不做任何事。
# - _log：印一行帶時間戳記的訊息到 stderr（stdout 留給真正的資料，
#   例如 status.sh 要印 running/stopped 給呼叫端讀）。
# - _require_env：檢查指定的環境變數都有值，缺一個就列出來並結束。
# - _require_tmux：確認 tmux 指令存在。
# - _session_alive：判斷 QB_SESSION_NAME 這個 tmux session 是否存在。

set -euo pipefail

_log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
}

_require_env() {
    local name missing=0
    for name in "$@"; do
        if [ -z "${!name:-}" ]; then
            _log "缺少環境變數：${name}"
            missing=1
        fi
    done
    if [ "${missing}" -ne 0 ]; then
        exit 3
    fi
}

_require_tmux() {
    if ! command -v tmux >/dev/null 2>&1; then
        _log "找不到 tmux，請先安裝（例如 apt install tmux）"
        exit 3
    fi
}

_session_alive() {
    tmux has-session -t "${QB_SESSION_NAME}" 2>/dev/null
}
