# How To：Server Shell Scripts

本專案將所有 **Minecraft Server 系統操作** 獨立為 Shell Script，Python 不直接操作 `tmux`，而是透過這些 Script 完成所有控制。

---

# 整體架構

```
Discord Bot
    │
    ▼
cogs/qb.py
    │
    ▼
core/qb/server.py
    │
    ▼
scripts/*.sh
    │
    ▼
tmux
    │
    ▼
Minecraft Server
```

所有與 Linux、tmux、Server 啟停有關的事情，都由 `scripts/` 負責。

Python 僅負責：

- Discord 指令
- 權限判斷
- 回傳訊息
- 呼叫 Shell Script

---

# Script 一覽

```
scripts/
│
├── _lib.sh
├── start.sh
├── stop.sh
├── restart.sh
├── status.sh
├── save.sh
└── command.sh
```

---

# _lib.sh

## 用途

所有 Script 的共用函式庫。

每支 Script 都會先：

```bash
source _lib.sh
```

因此可以共用：

- `_log`
- `_require_env`
- `_require_tmux`
- `_session_alive`

避免重複程式碼。

---

## _log()

輸出除錯訊息。

例如：

```bash
_log "Starting server"
```

輸出：

```
[2026-07-28 10:00:00] Starting server
```

注意：

Log 輸出至 **stderr**。

真正資料仍使用 stdout。

方便 Python 擷取結果。

---

## _require_env()

檢查必要環境變數。

例如：

```bash
_require_env QB_SERVER_DIR QB_SESSION_NAME
```

若缺少：

```
QB_SERVER_DIR
```

立即結束。

避免使用空值造成危險。

---

## _require_tmux()

確認系統已安裝 tmux。

沒有安裝：

```
exit 3
```

---

## _session_alive()

封裝：

```bash
tmux has-session
```

讓程式碼更簡潔。

---

# start.sh

## 功能

啟動 Minecraft Server。

流程：

```
檢查 tmux
        │
檢查環境變數
        │
Session 是否存在？
        │
        ├──存在
        │      │
        │   已啟動
        │
        ▼
建立 tmux Session
        │
等待
        │
再次確認
```

主要工作：

```
tmux new-session
```

建立新的背景 Session。

---

# stop.sh

## 功能

正常關閉 Server。

流程：

```
save-all
      │
      ▼
stop
      │
等待 Java 結束
      │
完成
```

而不是：

```
stop

↓

直接退出
```

因此可避免世界尚未儲存完成。

---

# restart.sh

## 功能

重新啟動 Server。

內容非常簡單：

```
stop.sh

↓

start.sh
```

所有流程皆重複利用。

---

# save.sh

## 功能

執行：

```
save-all
```

並等待數秒。

Minecraft 世界存檔不是立即完成。

因此需要等待。

---

# status.sh

## 功能

檢查 Server 是否仍在執行。

成功：

```
running
```

失敗：

```
stopped
```

Python 可直接依 Exit Code 判斷。

---

# command.sh

## 功能

送出任意 Minecraft Console 指令。

例如：

```
say Hello
```

Python：

```python
await server.send_command("say Hello")
```

Shell：

```
command.sh "say Hello"
```

最後：

```
tmux send-keys

↓

Minecraft Console
```

因此：

```
whitelist

op

deop

say

gamemode

tp

difficulty

save-all
```

全部都透過同一支 Script。

---

# Python 對應關係

```
Discord Command
        │
        ▼
cogs/qb.py
        │
        ▼
core/qb/server.py
        │
        ▼
scripts/*.sh
```

其中：

```
server.send_command()

↓

command.sh
```

```
server.start()

↓

start.sh
```

```
server.stop()

↓

stop.sh
```

```
server.restart()

↓

restart.sh
```

```
server.status()

↓

status.sh
```

```
server.save()

↓

save.sh
```

因此：

所有 Shell Script 都由

```
core/qb/server.py
```

統一管理。

Discord Cog 不需要知道 tmux 的存在。

---

# 為什麼不用 Python 直接操作 tmux？

如果全部寫在 Python：

```
subprocess.run(...)
tmux send-keys
tmux has-session
tmux kill-session
tmux new-session
```

這些 Linux 指令會散落在整個專案。

修改成本非常高。

目前架構：

```
Python

↓

Script

↓

tmux

↓

Minecraft
```

形成清楚的分層。

---

# 設計優點

## 1. 職責分離（Separation of Concerns）

Python：

- Discord
- API
- 權限
- 商業邏輯

Shell：

- Linux
- tmux
- Process
- Server

---

## 2. 易於維護

若未來：

```
tmux

↓

systemd
```

甚至：

```
Docker
```

Python 幾乎不用修改。

只需要修改 Script。

---

## 3. 高重用性

Script 可以：

- 手動執行
- Python 呼叫
- Cron 呼叫
- CI/CD 呼叫
- SSH 執行

完全不依賴 Discord Bot。

---

## 4. 模組化

每支 Script 只做一件事情：

```
start

stop

restart

save

status

command
```

符合 Single Responsibility Principle。

---

# 建議新增 Script

未來可加入：

```
backup.sh
```

建立世界備份。

---

```
update.sh
```

更新 Server。

---

```
health.sh
```

檢查 Java 是否仍正常執行。

---

```
logs.sh
```

取得最新 Console Log。

---

```
players.sh
```

取得目前在線玩家。

---

# 總結

本專案透過 Shell Script 將所有 Server 管理功能與 Python 完全解耦。

```
Discord Bot
        │
        ▼
server.py
        │
        ▼
scripts/*.sh
        │
        ▼
tmux
        │
        ▼
Minecraft Server
```

此設計具有：

- 高模組化
- 易於維護
- 易於測試
- 易於重構
- 易於替換底層實作

是一種相當典型且成熟的分層架構設計。