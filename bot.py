"""
bot.py

Modification():

- 修正 _EXTENSIONS 誤用連鎖賦值：原本寫成
  _EXTENSIONS = list[str] = ["cogs.qb"]，這行在執行期會對 list[str]
  直接賦值丟 TypeError，bot 根本開不起來。改回正常的型別註記寫法。
- 移除沒在用的 discord.Client 與沒接上 bot 的 intents 變數；
  intents 從 Intents.all() 改成 default() + message_content，
  不多要不需要的特權 intent。
- 補上真正會去載入 extension 的邏輯（原本 _EXTENSIONS 定義了但沒人用）、
  slash command 同步、以及讓程式真的能執行的 __main__ 進入點
  （原本 main() 定義了但沒有任何地方呼叫它）。
- 載入清單補上 cogs.load（原本沒排進開機清單，指令等於裝好也用不到）
  跟 cogs.minecraft（珍珠砲計算機）。
- 移除 main() 裡對 config.TOKEN 的檢查：config.py 開機時已經會驗證
  DISCORD_TOKEN 有沒有填，填了才可能走到這裡，這裡再檢查一次是死路徑。

Description():

- Bot 進入點：設定 intents、註冊開機要載入的 cogs、啟動連線。
"""

from __future__ import annotations

import asyncio

import discord
from discord.ext import commands

import config
from core.logging.log import LogManager

log_manager = LogManager()
logger = log_manager.get_logger("bot")

# ── intents：夠用就好，不多要 ──────────────────────
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!!", intents=intents)

# ── 開機自動載入的 cogs ──────────────────────
_EXTENSIONS: list[str] = [
    "cogs.load",
    "cogs.qb",
    "cogs.minecraft",
]

_synced = False


@bot.event
async def on_ready() -> None:
    global _synced
    print(f"目前登入身份 --> {bot.user}")

    if not _synced:
        await bot.tree.sync()
        _synced = True


async def main() -> None:
    async with bot:
        for extension in _EXTENSIONS:
            try:
                await bot.load_extension(extension)
            except Exception:
                logger.exception("載入 %s 失敗", extension)

        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
