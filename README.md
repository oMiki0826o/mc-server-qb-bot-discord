# qb-bot

Discord 機器人，管理跟它跑在同一台機器上的 Minecraft 伺服器：一鍵備份／回復存檔，
加上一個 TNT 珍珠砲落點計算機。設計給小型社群自己用，重點是動到存檔的操作要夠安全。

## 功能

- `!!qb make [檔名]` — 關閉伺服器、把整個伺服器資料夾壓成 `.tar.gz`、重啟。
  檔名可以不給，不給就自動用時間戳記命名。
- `!!qb back <檔名>` — 關閉伺服器、用指定備份整批換上、重啟。執行前要按按鈕
  二次確認，真正回復前還會自動多存一份「回復前快照」，選錯備份也回得去。
- `!!info` — 看伺服器目前線上／離線（有設定 RCON 的話還會顯示線上玩家），
  以及最近 10 次備份／回復是誰做的、做了什麼、結果如何。
- `/pearl` — TNT 珍珠砲落點計算機，輸入珍珠位置跟目的地座標，算出誤差最小的
  前 10 組 tick 數與紅石訊號碼。

### 安全設計

- 指令限定在特定頻道、特定身分組才能用。
- 每次備份／回復都會私訊 bot owner。
- 同一時間只允許一個備份／回復作業在跑，不會互相打架。
- 檔名會清理過，擋掉路徑跳脫（例如 `../../etc/passwd` 這種輸入）。
- 回復採「先解壓到暫存資料夾，成功才整批換上」，解壓到一半失敗不會把
  現有世界弄爛。
- 有設定 RCON 的話，關伺服器前會先在遊戲內廣播提醒，等一段緩衝時間才
  真的關，不會讓玩家毫無預警被踢出去。

## 需求

- Python 3.9 以上
- [tmux](https://github.com/tmux/tmux)：macOS 用 `brew install tmux`，
  Linux 用 `apt install tmux`（或對應套件管理器）
- 一個 Discord bot token（[Discord Developer Portal](https://discord.com/developers/applications) 建立）
- Minecraft 伺服器本身要跑在一個 tmux session 裡，且 session 裡直接執行
  啟動指令（不是包一層 bash 再把 java 丟到背景）。這樣 tmux session 的
  存活時間才會等於伺服器的存活時間，機器人才能準確判斷伺服器有沒有關乾淨。
  如果實際架設方式不是這樣，換掉 `core/qb/server.py` 這支檔案就好，
  其他地方不用動。

## 安裝

```bash
pip install -r requirements.txt
```

複製一份 `.env`，把裡面的值填成自己的（見下方設定表）。`DISCORD_TOKEN`／
`OWNER_ID` 沒有合理的預設值，一定要自己填；其他項目 `.env` 裡已經放了
範例值，直接用或依自己的環境調整都可以。

啟動 Minecraft 伺服器（跑在 tmux session 裡，session 名稱要跟 `.env` 的
`QB_SESSION_NAME` 一致），接著啟動機器人：

```bash
python bot.py
```

`config.py` 開機時會檢查 `.env` 裡的必填項目，少填哪一個會直接報錯並列出來，
不會用猜的值默默跑起來。

## 設定（.env）

| 變數 | 必填 | 說明 |
|---|---|---|
| `DISCORD_TOKEN` | 必填 | Discord bot token |
| `OWNER_ID` | 必填 | bot owner 的 Discord 使用者 ID，備份／回復都會私訊通知 |
| `QB_CHANNEL_ID` | 必填 | 允許使用 `!!qb`／`!!info` 的頻道 ID |
| `QB_ROLE_ID` | 必填 | 允許使用 `!!qb`／`!!info` 的身分組 ID |
| `QB_SERVER_DIR` | 必填 | Minecraft 伺服器資料夾的絕對路徑 |
| `QB_BACKUP_DIR` | 必填 | 備份檔存放的絕對路徑 |
| `QB_SESSION_NAME` | 必填 | 執行 Minecraft 伺服器的 tmux session 名稱 |
| `QB_START_COMMAND` | 必填 | 啟動伺服器的指令，在 `QB_SERVER_DIR` 底下執行 |
| `QB_STOP_TIMEOUT` | 必填 | 送出關閉指令後，最多等幾秒才視為逾時（秒） |
| `QB_BACKUP_PREFIX` | 必填 | 自動命名備份檔時使用的前綴 |
| `QB_PRE_RESTORE_PREFIX` | 必填 | 回復前自動快照使用的前綴 |
| `QB_HISTORY_FILE` | 必填 | `!!info` 操作紀錄存放的檔案路徑 |
| `QB_HISTORY_KEEP` | 必填 | 操作紀錄最多保留幾筆 |
| `QB_RCON_HOST` | 選填 | Minecraft RCON 主機位址，三項要一起填才會啟用 |
| `QB_RCON_PORT` | 選填 | RCON 埠號 |
| `QB_RCON_PASSWORD` | 選填 | RCON 密碼，跟 `server.properties` 的 `rcon.password` 一致 |
| `QB_RCON_WARN_SECONDS` | 選填 | 廣播提醒後，等幾秒再真的關伺服器（預設 10） |

RCON 相關三項要啟用的話，Minecraft 的 `server.properties` 要先設定：

```properties
enable-rcon=true
rcon.port=25575
rcon.password=你的密碼
```

## 專案結構

```
qb-bot/
├── bot.py                          進入點：載入 cogs、同步 slash command、啟動連線
├── config.py                       設定入口，全部從 .env 讀，缺項直接拒絕啟動
├── requirements.txt
├── .env
├── cogs/
│   ├── qb.py                       !!qb make / !!qb back / !!info
│   ├── minecraft.py                /pearl
│   └── load.py                     owner 專用的 cog 載入／卸載／重載／關機指令
├── core/
│   ├── qb/
│   │   ├── backup.py               備份／回復的檔案操作（壓縮、解壓、清理檔名）
│   │   ├── server.py               tmux 開關 Minecraft 伺服器
│   │   ├── history.py              !!info 用的操作紀錄
│   │   └── rcon.py                 RCON 用戶端，廣播提醒與查詢線上玩家
│   ├── minecraft/
│   │   ├── mc_pearl_calculator.py  珍珠砲落點運算核心
│   │   └── mc_pearl_config.py      珍珠砲計算機的參數
│   └── logging/
│       ├── log.py                  全域 log 管理（單例）
│       └── constants.py            log 路徑、格式等常數
└── database/
    ├── qb/                         history.json 存放位置
    └── log/                        log 檔案存放位置
```

## 之後可以考慮的擴充

以下先列出構想，還沒實作：

- 備份自動輪替：只留最近 N 份，太舊自動砍掉
- 排程自動備份（固定時間自動觸發 `make`）
- 伺服器當機偵測並自動重啟
- 差異備份（rsync 硬連結或 borgbackup），省時間跟硬碟空間
- 備份異地上傳（rclone 丟雲端），防單一硬碟掛掉整組沒了
- `core/logging/log.py` 的 `LOG_MAX_BYTES` 常數目前沒被套用，log 檔案會
  無限長大，可以換成 `RotatingFileHandler` 解決
