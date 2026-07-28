#!/usr/bin/env bash
# core/qb/scripts/restart.sh
#
# Modification():
# - 新增本檔案：依序呼叫 stop.sh 與 start.sh。Bot 本身的 restart 流程
#   是在 Python 端（core/qb/server.py）分開呼叫 stop 與 start，才能
#   各自記錄時間與結果；這支腳本只給人在終端機手動重啟，或給
#   cron／systemd 這類外部排程使用。
#
# Description():
# - 用途：完整重啟一次（stop -> start）。
# - 用法：restart.sh [timeout_seconds]
# - 結束碼：延續 stop.sh／start.sh，任一失敗就以該步驟的結束碼中止。

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

./stop.sh "$@"
./start.sh
