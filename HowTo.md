# HowTo：qb 系統架構說明

這份文件說明 `core/qb/` 底下每一支檔案在做什麼、彼此怎麼串起來，給往後要維護或修改這個系統的人看。公開給使用者看的說明在 README.md，這份是給要動程式碼的人看的內部文件。

---

## 整體架構

一次 `/qb make` 的完整呼叫路徑：

```
Discord 指令（/qb make、/qb back、/qb schedule）
        |
        v
cogs/qb.py              權限檢查、把訊息貼回 Discord
        |
        v
core/qb/backup.py        run_backup／run_restore：流程本身（取鎖、狀態機、Flow）
        |
        v
core/qb/server.py        start／stop／restart：伺服器生命週期
        |
        v
core/qb/process.py       Script Runner：統一呼叫 script、記錄時間軸
        |
        v
core/qb/scripts/*.sh      實際操作 tmux
        |
        v
tmux session -> Minecraft 伺服器行程
```

分層的原則：越下層越不知道上層在幹嘛。`scripts/` 不知道 Discord 存在，`server.py` 不知道有沒有人在排隊等鎖，`backup.py` 不知道訊息最後會被貼到哪個頻道。這樣任何一層要換掉（例如把 tmux 換成 systemd，或把 Discord 換成別的介面），其他層都不用跟著改。

---

## core/qb/exceptions.py

定義六個例外類別，全部繼承自共同的 `QBError`：

- `TMUXError`：呼叫 `scripts/` 底下的 script 失敗（找不到檔案、逾時、非零 returncode）。只在 `process.py` 產生，正常情況不會跑到 `cogs/` 層——`server.py` 會接住並轉成 `ServerError`。
- `ServerError`：伺服器啟動／關閉／重啟失敗。
- `BackupError`：建立備份失敗。
- `RestoreError`：回復備份失敗。
- `QBBusyError`：搶鎖失敗，代表已經有其他備份／回復作業在跑，不是「操作出錯」，是「現在不能做」，訊息要分開處理。

用例外取代舊版「回傳 `(成功與否, 訊息)`」的作法，呼叫端一個 `except QBError` 就能接住所有失敗情況，不用每一步都手動判斷。

---

## core/qb/state.py

兩件事：狀態機、三把鎖。

**狀態機**：`State` 是一個列舉，八種值（Idle、Starting、Running、Stopping、Stopped、BackingUp、Restoring、Failed）。`state.flow(某狀態)` 是一個情境管理器，進入時把狀態推進堆疊，離開時（不管成功或例外）自動退回進入前的狀態，可以巢狀——例如備份流程顯示 BackingUp，內部呼叫 `server.stop()` 時會短暫疊上 Stopping，`stop()` 結束後自動退回 BackingUp。`state.current_flow()` 回傳目前最新的流程狀態，沒有流程在跑就回傳 `None`，由 `server.status()` 自己決定沒有流程時要顯示 Running、Stopped 還是 Failed。

**三把鎖**：`server_lock`、`backup_lock`、`restore_lock`，各自是獨立的 `asyncio.Lock`。`state.guarded(...)` 依序非阻塞取得多把鎖，只要有一把已經被占用就立刻丟 `QBBusyError`，不會讓 Discord 指令傻等一個可能要跑好幾分鐘的鎖。備份流程的取鎖順序固定是「先 backup_lock，再 server_lock」，回復流程是「先 restore_lock，再 server_lock」——兩邊都把 server_lock 放在後面取，這樣備份跟回復才不會同時真的動到伺服器與存檔，也不會因為取鎖順序不一致而死結。

---

## core/qb/process.py

這支檔案就是「Script Runner」，負責「怎麼呼叫 `scripts/` 底下的 script」這件事本身，`server.py` 只管「什麼時候呼叫哪一支」。

`Flow` 是一次操作（例如一次完整備份）的容器，建立時會拿到一個短的隨機 ID（例如 `qb.make#a1b2c3d4`）。同一次操作裡不管跑了幾支 script、經過幾個純 Python 步驟，都用同一個 `Flow`，log 裡就能用同一個 ID 串出完整時間軸：

- `flow.run_script(名稱, *參數)`：執行一支 script，用 `bash 路徑` 執行（不依賴檔案本身有沒有執行權限，因為 zip／git 轉手常常會弄丟這個權限位元），記錄 returncode、stdout、stderr、耗時。預設非零結束碼會丟 `TMUXError`；傳 `check=False` 可以自己判讀結果（例如 `status.sh` 用非零代表「沒有在跑」，那不是錯誤）。
- `flow.step(名稱)`：包住一個純 Python 步驟（例如壓縮），量時間、寫 log，不吞例外。
- `flow.finish(success=...)`：流程結束時寫一行總結，方便在 log 裡快速掃描起訖。

---

## core/qb/server.py

伺服器生命週期，只剩四個函式，每一個都清楚知道會發生什麼事：

- `is_running()`：純粹問「tmux session 現在還在嗎」。
- `status()`：給 `/info` 用的完整狀態，優先回報進行中的流程，其次才是單純的線上／離線／上次失敗。
- `start()`：呼叫 `start.sh`。
- `stop()`：呼叫 `stop.sh`（內部會先 `save-all`，等到 session 真的消失或逾時）。
- `restart()`：依序呼叫 `stop()` 與 `start()`，自帶 `server_lock` 保護，適合被獨立呼叫；如果要在已經持有 `server_lock` 的流程裡重啟（例如備份流程），要直接照順序呼叫 `stop()`／`start()`，不要呼叫 `restart()`，否則會自己等自己、永遠等不到鎖。

原本這裡還有 `send_command()`，可以對執行中的伺服器送任意一行主控台指令。已經拿掉了：目前沒有任何 Discord 指令會用到它，留著等於是開一個「什麼指令都能送」的後門，風險跟實際用途不成比例。對應的 `scripts/command.sh` 也一併刪除。如果之後真的需要送特定指令（例如 `/say` 廣播），建議另外寫一個「只接受這幾種指令」的函式，而不是重新開放任意指令執行。

---

## core/qb/backup.py

兩層東西：檔案操作、完整流程。

**檔案操作**（不牽涉鎖、狀態機、Discord）：

- `sanitize_filename()`：清理檔名，踢掉路徑跳脫與奇怪字元。
- `default_filename()`：用時間戳記產生檔名。
- `human_size()`：bytes 轉成人看得懂的容量。
- `backup_path()` / `exists()` / `list_backups()`：檔名轉路徑、檢查存在、列出現有備份。
- `create(filename)`：把 `QB_SERVER_DIR` 整包壓成 `tar.gz`，失敗丟 `BackupError`。
- `restore(filename)`：先解壓到暫存資料夾，成功才整批換上，失敗丟 `RestoreError`，原本的世界資料夾不會被動到。
- `rotate_auto_backups(prefix, keep)`：砍掉超過 `keep` 份、檔名符合 `prefix` 的舊備份，只給自動備份用，手動備份不受影響。

**完整流程**（會取鎖、動狀態機、寫操作紀錄，唯一跟 Discord 有關係的地方是接受一個 `progress` 回呼，但完全不 import discord）：

- `run_backup(filename, operator, progress=None)`：取鎖 -> 關閉伺服器 -> 壓縮 -> 重啟伺服器 -> 寫入操作紀錄。
- `run_restore(filename, operator, progress=None)`：取鎖 -> 關閉伺服器 -> 自動存一份回復前快照 -> 解壓回復 -> 重啟伺服器 -> 寫入操作紀錄。

`cogs/qb.py` 只呼叫這兩個函式，不自己實作流程；未來如果要加別的觸發方式（例如排程），也是直接呼叫這兩個函式，不用重寫一次。

---

## core/qb/history.py

`/info` 顯示的操作紀錄，存成 `database/qb/history.json`。`HistoryEntry` 是一個 dataclass，欄位包含操作時間、動作、操作者、目標檔名、成功與否、說明文字，還有 `flow_id`／`duration`（跟 `process.py` 產生的時間軸 log 對得起來，想深入查某次備份卡在哪一步，可以拿 `flow_id` 去 log 檔案裡搜尋）。`record()` 寫入一筆，超過 `QB_HISTORY_KEEP` 筆自動砍掉最舊的；`recent(limit)` 取最近幾筆給 `/info` 顯示。

---

## core/qb/scheduler.py

只做一件事：每日自動備份「開／關」這個設定的持久化存取，存成 `database/qb/schedule.json`。跟「幾點觸發」無關——那是 `cogs/qb.py` 裡用 `discord.ext.tasks` 排程決定的，這裡只回答「現在該不該做」。獨立成一支檔案是因為這個開關要跨重啟保留，用一般的模組變數重開機就會消失，必須落地寫成檔案。

---

## core/qb/scripts/

實際操作 tmux 的 shell script，`process.py` 統一呼叫。每一支都只做一件事：

| 檔案 | 做什麼 |
| --- | --- |
| `_lib.sh` | 共用工具，其他 script 開頭都會 `source` 它：`_log`（印帶時間戳記的訊息到 stderr）、`_require_env`（檢查必要環境變數）、`_require_tmux`（確認 tmux 存在）、`_session_alive`（tmux session 是否存在） |
| `start.sh` | 建立 tmux session，在裡面執行 `QB_START_COMMAND` |
| `stop.sh` | `save-all` -> `stop` -> 等到 session 消失或逾時 |
| `save.sh` | 對執行中的 session 送 `save-all`，`stop.sh` 會呼叫它 |
| `restart.sh` | 依序呼叫 `stop.sh`、`start.sh`；只給人在終端機手動重啟或給 cron／systemd 用，bot 本身的重啟是在 Python 端分開呼叫 `stop()`／`start()`，才能各自記錄時間 |
| `status.sh` | 回報 tmux session 是否存在 |

拿掉 tmux 直接呼叫 Python 的原因：這樣以後要換掉行程監控方式（改用 systemd 或 docker），只需要換掉這些 script，`server.py` 完全不用動；script 也能脫離 bot 單獨用（手動執行、排程呼叫、SSH 進去跑），不綁死在 Discord 上。

---

## cogs/qb.py

介面層，看不到任何 tmux／tarfile 的細節：

- `/qb make [檔名]`、`/qb back [檔名]`：驗證權限、呼叫 `backup.run_backup()` / `run_restore()`、把過程中收到的進度文字接到同一則訊息下面。
- `/qb schedule <on|off>`：呼叫 `scheduler.set_enabled()`。
- `/info`：呼叫 `server.status()` 跟 `history.recent()`，組成一則文字訊息。
- `_daily_backup`：`discord.ext.tasks` 背景任務，每天固定時間檢查 `scheduler.is_enabled()`，開啟才呼叫 `backup.run_backup()`。整個函式本體包一層 `try/except Exception`，因為 `discord.ext.tasks` 有個坑——例外只要逃出任務函式，排程就會永久停止，之後每天都不會再觸發，所以必須確保無論出什麼包，明天都還會再試一次。

---

## 建議之後可以加的 script

`backup.sh`／`restore.sh` 目前刻意沒有做成 script：壓縮／解壓是純檔案操作，Python 內建的 `tarfile` 在 macOS 跟 Linux 上行為一致，不需要呼叫外部 `tar` 指令，硬要拆成 shell script 只是把同一套邏輯用兩種語言各寫一次。如果之後有明確理由要換（例如想要備份即使 Python／bot 本身壞掉也能跑），再另外評估。

`health.sh`（確認 Java 行程本身還活著，不是只看 tmux session 在不在）是比較值得考慮的下一步，因為目前 `is_running()` 只看 tmux session 存在與否，如果 Java 當掉但 shell 還留著，現有邏輯會誤判成「還在跑」。
