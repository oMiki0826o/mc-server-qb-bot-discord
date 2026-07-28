#!/usr/bin/env bash
# core/qb/scripts/save.sh
#
# Modification():
# - 新增本檔案：獨立出「叫伺服器把記憶體中的世界資料寫回硬碟」這個
#   單一動作，stop.sh 會呼叫它，未來如果想加一個「不關伺服器、只是
#   存個檔」的指令，也可以直接重用。
#
# Description():
# - 用途：對 tmux session 送 save-all。
# - 用法：save.sh
# - 結束碼：0 = 已送出（或本來就沒在跑，視為無事可做）；
#   非 0 = tmux 操作失敗。

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_lib.sh

_require_tmux
_require_env QB_SESSION_NAME

if ! _session_alive; then
    _log "session「${QB_SESSION_NAME}」沒在跑，略過 save-all"
    exit 0
fi

_log "送出 save-all"
tmux send-keys -t "${QB_SESSION_NAME}" "save-all" Enter
sleep 2
