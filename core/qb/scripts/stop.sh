#!/usr/bin/env bash
# core/qb/scripts/stop.sh
#
# Modification():
# - 新增本檔案：把「save-all -> stop -> 等到 session 消失」這段完整
#   邏輯搬出 Python，對應原本規劃裡「Python → stop.sh → save-all →
#   stop → 等待 Java 結束 → tmux 消失」的流程。逾時秒數可由參數或
#   QB_STOP_TIMEOUT 決定，Python 端不用自己寫等待迴圈。
#
# Description():
# - 用途：送 save-all 與 stop 進 tmux session，等到 session 消失或
#   逾時。
# - 用法：stop.sh [timeout_seconds]（不給就用 QB_STOP_TIMEOUT，
#   兩者都沒有就預設 120 秒）
# - 結束碼：0 = 已確認關閉（或本來就沒在跑）；1 = 逾時仍在跑。

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_lib.sh

_require_tmux
_require_env QB_SESSION_NAME

timeout_seconds="${1:-${QB_STOP_TIMEOUT:-120}}"

if ! _session_alive; then
    _log "session「${QB_SESSION_NAME}」本來就不存在，視為已關閉"
    exit 0
fi

./save.sh

_log "送出 stop 指令"
tmux send-keys -t "${QB_SESSION_NAME}" "stop" Enter

waited=0
while _session_alive; do
    if [ "${waited}" -ge "${timeout_seconds}" ]; then
        _log "等待 ${timeout_seconds} 秒後仍未關閉，逾時"
        exit 1
    fi
    sleep 2
    waited=$((waited + 2))
done

_log "已確認關閉（耗時約 ${waited} 秒）"
