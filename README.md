# qb-bot

![Version](https://img.shields.io/badge/version-1.1-blue)
![License](https://img.shields.io/badge/license-PolyForm_Noncommercial_1.0.0-green)
![Tech](https://img.shields.io/badge/stack-Python-lightgrey)
![Python](https://img.shields.io/badge/Python-3.9%2B-orange)

[中文](#中文) | [English](#english)

---

## 中文

### 目錄
- [關於](#關於)
- [功能](#功能)
- [安裝](#安裝)
- [使用方式](#使用方式)
- [授權](#授權)

### 關於
qb-bot 是一個 Discord 機器人, 用來管理跟它跑在同一台機器上的 Minecraft 伺服器. 透過 Discord 的 slash command 就能備份, 回復伺服器存檔, 也可以開啟每日自動備份, 另外附一個 TNT 珍珠砲落點計算機. 設計給小型社群自己架設使用, 核心目標是讓動到存檔的操作(備份, 回復)夠安全, 出問題時也查得出來是哪一步壞的.

### 功能
- `/qb make [檔名]` - 關閉伺服器, 把整個伺服器資料夾壓成 tar.gz, 再重新啟動, 檔名可留空, 會自動用時間戳記命名
- `/qb back [檔名]` - 關閉伺服器, 用指定備份整批換上, 再重新啟動, 執行前需按按鈕二次確認, 回復前也會自動多存一份回復前快照
- `/qb schedule <on|off>` - 開關每日自動備份, 開啟後會回報下一次預計執行時間
- `/info` - 查看伺服器目前狀態, 每日自動備份開關與下次執行時間, 以及最近的備份, 回復紀錄
- `/pearl` - TNT 珍珠砲落點計算機

### 安裝
```bash
pip install -r requirements.txt
```

複製一份 `.env.example` 另存為 `.env`, 依照裡面的說明填入設定, 接著啟動機器人:

```bash
python bot.py
```

### 使用方式
在有權限的 Discord 頻道裡直接輸入 slash command 即可, 例如:

```bash
/qb make
/qb back
/qb schedule on
/info
```

### 授權
本專案採用 PolyForm Noncommercial 1.0.0 授權, 僅允許非商業用途使用, 詳見 [LICENSE](./LICENSE).

---

## English

### Table of Contents
- [About](#about)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [License](#license)

### About
qb-bot is a Discord bot that manages a Minecraft server running on the same machine. Through Discord slash commands, you can back up and restore the server's save data, and enable daily automatic backups. It also includes a TNT pearl cannon landing calculator. It is built for small communities running their own server, with a focus on making save-altering operations (backup, restore) safe, and traceable when something goes wrong.

### Features
- `/qb make [filename]` - stops the server, archives the whole server folder into a tar.gz, then restarts it. The filename can be left blank, in which case it is generated from a timestamp
- `/qb back [filename]` - stops the server, replaces the world with the given backup, then restarts it. Requires a confirmation button before running, and automatically saves a pre-restore snapshot first
- `/qb schedule <on|off>` - toggles daily automatic backups, reporting the next scheduled run time when enabled
- `/info` - shows the server's current status, the daily backup toggle and next run time, and recent backup/restore history
- `/pearl` - TNT pearl cannon landing calculator

### Installation
```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env`, fill in the values as documented inside it, then start the bot:

```bash
python bot.py
```

### Usage
Use the slash commands directly in an authorized Discord channel, for example:

```bash
/qb make
/qb back
/qb schedule on
/info
```

### License
This project is licensed under the PolyForm Noncommercial 1.0.0 License, which permits noncommercial use only, see [LICENSE](./LICENSE).
