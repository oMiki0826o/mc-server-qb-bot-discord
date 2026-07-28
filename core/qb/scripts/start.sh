#!/usr/bin/env bash
# core/qb/scripts/start.sh
#
# Modification():
# - 新增本檔案：把原本寫在 core/qb/server.py 裡、直接組 tmux 指令的
#   邏輯搬出來，Python 端只負責「呼叫這支 script」。以後不管是要換
#   別的方式監控行程，還是要調整啟動前的檢查，都只需要動這支檔案。
#
# Description():
# - 用途：開一個新的 tmux session，在 QB_SERVER_DIR 底下執行
#   QB_START_COMMAND。
# - 用法：start.sh（不需要參數，所有設定都從環境變數讀）
# - 結束碼：0 = 成功（session 已建立且存在，或本來就在跑）；
#   非 0 = 失敗，詳見 stderr。

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_lib.sh

_require_tmux
_require_env QB_SESSION_NAME QB_SERVER_DIR QB_START_COMMAND

if _session_alive; then
    _log "session「${QB_SESSION_NAME}」已經存在，視為啟動成功"
    exit 0
fi

if [ ! -d "${QB_SERVER_DIR}" ]; then
    _log "QB_SERVER_DIR 不存在：${QB_SERVER_DIR}"
    exit 3
fi

_log "建立 session「${QB_SESSION_NAME}」，工作目錄：${QB_SERVER_DIR}"
tmux new-session -d -s "${QB_SESSION_NAME}" -c "${QB_SERVER_DIR}" "${QB_START_COMMAND}"

# ── 給 tmux 一點時間把 session 建起來，再次確認真的活著 ──────────────────────
sleep 1

if _session_alive; then
    _log "啟動成功"
    exit 0
fi

_log "session 建立後立刻消失，啟動失敗，請檢查 QB_START_COMMAND 是否能正常執行"
exit 1
