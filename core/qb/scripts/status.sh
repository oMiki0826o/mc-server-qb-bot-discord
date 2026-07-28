#!/usr/bin/env bash
# core/qb/scripts/status.sh
#
# Modification():
# - 新增本檔案：把「怎麼判斷伺服器活著」這件事完全留在 shell 這一層。
#   以後如果換掉行程監控方式（例如改用 systemd 或 docker），只要改
#   這支腳本，core/qb/server.py 完全不用動。
#
# Description():
# - 用途：回報 tmux session 是否存在。
# - 用法：status.sh
# - 結束碼：0 = 執行中；1 = 未執行。
#   stdout 會印 running 或 stopped，方便人工直接執行時閱讀。

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_lib.sh

_require_tmux
_require_env QB_SESSION_NAME

if _session_alive; then
    echo "running"
    exit 0
fi

echo "stopped"
exit 1
