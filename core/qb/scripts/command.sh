#!/usr/bin/env bash
# core/qb/scripts/command.sh
#
# Modification():
# - 新增本檔案：讓 Python 端能在不了解 tmux 細節的情況下操作伺服器
#   主控台（例如 say、whitelist），對應 server.py 新增的
#   send_command()，也是「未來要加新指令」時唯一需要碰的進入點。
#
# Description():
# - 用途：對正在執行的 tmux session 送一行主控台指令。
# - 用法：command.sh "<console command>"
# - 結束碼：0 = 已送出；2 = 參數錯誤；3 = session 不存在或缺少設定。

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_lib.sh

_require_tmux
_require_env QB_SESSION_NAME

if [ "$#" -lt 1 ]; then
    _log '用法：command.sh "<console command>"'
    exit 2
fi

if ! _session_alive; then
    _log "session「${QB_SESSION_NAME}」沒在跑，無法送出指令"
    exit 3
fi

_log "送出指令：$1"
tmux send-keys -t "${QB_SESSION_NAME}" "$1" Enter
