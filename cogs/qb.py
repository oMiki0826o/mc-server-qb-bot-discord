"""
cogs/qb.py

Modification():

- 原本的版本在 load() 裡呼叫 self._split_names／self._handle，
  但這兩個方法整支檔案都沒有定義，指令一用就會噴 AttributeError，
  形同虛設。整份重寫成真正能動的 Minecraft 伺服器備份／回復指令：
  !!qb make、!!qb back。
- 加上頻道與身分組雙重限制、owner 私訊通知、同一時間只能跑一個
  備份／回復（asyncio.Lock）、回復前用按鈕二次確認、回復前自動
  幫現況存一份快照，避免手滑回錯備份就再也回不去。
- 狀態訊息用同一則訊息一路 edit 下去，貼近原本手動連進終端機看到的
  「正在備份...【成功】...」那種輸出感覺。

- 新增 !!info：查看伺服器目前線上／離線，跟最近 10 次 make／back
  紀錄（誰、做了什麼、結果如何）。make／back 不管成功失敗，
  只要真的動手做了（過了鎖跟身分驗證），就會記一筆進
  core/qb/history.py，重開 bot 紀錄也還在。

- config.OWNER_ID 現在由 config.py 開機時保證一定有值（缺了直接
  拒絕啟動），_notify_owner 不用再自己檢查是否為空。

- 整合 RCON（core/qb/rcon.py）：make／back 關伺服器前會先廣播提醒玩家，
  等一段緩衝時間再真的送 stop，不會讓正在玩的人毫無預警被踢出去。
  !!info 也會在伺服器線上時，順便顯示 RCON 查到的線上玩家名單。
  RCON 沒設定的話這些都自動跳過，不影響備份／回復本身。

Description():

- !!qb make [檔名]：關閉 MC 伺服器 -> 整包壓成 tar.gz -> 重啟伺服器。
  檔名可以不給，不給就用時間戳記自動命名。有設 RCON 的話，關伺服器前
  會先廣播提醒玩家。
- !!qb back <檔名>：關閉 MC 伺服器 -> 用指定的備份整批換上 -> 重啟伺服器。
  執行前要按按鈕確認，真正回復前還會自動多存一份現況快照保底，
  一樣會先透過 RCON 廣播提醒。
- !!info：看伺服器線上狀態（有 RCON 的話含線上玩家），跟最近 10 次
  備份／回復的操作紀錄。
"""

from __future__ import annotations

import asyncio
from typing import Optional

import discord
from discord.ext import commands

import config
from core.logging.log import LogManager
from core.qb import backup, history, rcon, server

logger = LogManager().get_logger("cogs.qb")

# ── 同一時間只允許一個備份／回復作業，避免互相打架 ──────────────────────
_lock = asyncio.Lock()


# ── 頻道與身分組雙重檢查 ──────────────────────

def _authorized(ctx: commands.Context) -> bool:
    if ctx.channel.id != config.QB_CHANNEL_ID:
        return False
    if not isinstance(ctx.author, discord.Member):
        return False
    return any(role.id == config.QB_ROLE_ID for role in ctx.author.roles)


# ── 私訊 owner，失敗就記錄一下，不影響主流程 ──────────────────────

async def _notify_owner(bot: commands.Bot, text: str) -> None:
    try:
        owner = bot.get_user(config.OWNER_ID) or await bot.fetch_user(config.OWNER_ID)
        await owner.send(text)
    except discord.HTTPException:
        logger.warning("私訊 owner 失敗")


# ── 回復用的二次確認按鈕 ──────────────────────

class _ConfirmView(discord.ui.View):
    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=30)
        self.author_id = author_id
        self.confirmed: Optional[bool] = None
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    @discord.ui.button(label="確認回復", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.confirmed = True
        self.stop()
        await interaction.response.edit_message(content="收到，開始處理...", view=None)

    @discord.ui.button(label="取消", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.confirmed = False
        self.stop()
        await interaction.response.edit_message(content="取消了，世界保住了", view=None)

    async def on_timeout(self) -> None:
        self.confirmed = False
        if self.message is not None:
            try:
                await self.message.edit(content="等太久，當作取消", view=None)
            except discord.HTTPException:
                pass


# ── 備份／回復 Cog ──────────────────────

class QuickBackup(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.group(name="qb", invoke_without_command=True)
    async def qb(self, ctx: commands.Context) -> None:
        if not _authorized(ctx):
            return
        await ctx.send("指令：`!!qb make [檔名]` 備份、`!!qb back <檔名>` 回復")

    # ── 備份：關伺服器 -> 壓縮 -> 重啟 ──────────────────────
    @qb.command(name="make")
    async def make(self, ctx: commands.Context, *, filename: Optional[str] = None) -> None:
        if not _authorized(ctx):
            return

        if _lock.locked():
            await ctx.send("現在有其他備份／回復作業在跑，等它跑完再試")
            return

        name = backup.sanitize_filename(filename) if filename else backup.default_filename()

        async with _lock:
            target = backup.backup_path(name)
            status = f"正在備份 `{config.QB_SERVER_DIR}` 到 `{target}`..."
            msg = await ctx.send(status)
            await _notify_owner(self.bot, f"{ctx.author} 在頻道觸發備份：{name}")

            if rcon.configured():
                status += f" 廣播提醒玩家中（等 {config.QB_RCON_WARN_SECONDS} 秒）..."
                await msg.edit(content=status)
                await rcon.warn_and_wait(f"伺服器即將備份並重啟，{config.QB_RCON_WARN_SECONDS} 秒後關閉")
                status += "完成，"

            status += " 關閉伺服器中..."
            await msg.edit(content=status)

            if not await server.stop():
                status += "逾時，伺服器沒關乾淨，備份中止，麻煩自己上去看一下"
                await msg.edit(content=status)
                logger.error("qb make：關閉伺服器逾時（操作者：%s）", ctx.author)
                await _notify_owner(self.bot, f"備份中止：伺服器關閉逾時（{ctx.author}）")
                history.record("make", str(ctx.author), name, False, "伺服器關閉逾時")
                return
            status += "完成，"

            status += "壓縮中..."
            await msg.edit(content=status)
            ok, detail = await asyncio.to_thread(backup.create, name)

            status += " 重啟伺服器中..."
            restarted = server.start()
            status += "完成。" if restarted else "沒能正常拉起來，麻煩自己上去看一下。"

            if ok:
                status += f"【成功】備份完成！檔案大小為：{detail}"
                logger.info("備份完成：%s（%s，操作者：%s）", target, detail, ctx.author)
            else:
                status += f"【失敗】備份出包：{detail}"
                logger.error("備份失敗：%s（操作者：%s）", detail, ctx.author)

            history.record("make", str(ctx.author), name, ok, detail)
            await msg.edit(content=status)
            await _notify_owner(self.bot, status)

    # ── 回復：關伺服器 -> 換上指定備份 -> 重啟 ──────────────────────
    @qb.command(name="back")
    async def back(self, ctx: commands.Context, *, filename: Optional[str] = None) -> None:
        if not _authorized(ctx):
            return

        if not filename:
            files = backup.list_backups()
            if not files:
                await ctx.send("備份資料夾裡空空如也")
                return
            listing = "\n".join(f"- {f.name.removesuffix('.tar.gz')}" for f in files[:10])
            await ctx.send(f"要回復哪一份？\n{listing}")
            return

        name = backup.sanitize_filename(filename)
        if not backup.exists(name):
            await ctx.send(f"找不到 `{name}` 這份備份，打 `!!qb back` 看看有哪些")
            return

        if _lock.locked():
            await ctx.send("現在有其他備份／回復作業在跑，等它跑完再試")
            return

        view = _ConfirmView(ctx.author.id)
        prompt = await ctx.send(
            f"確定要用 `{name}` 蓋掉現在的世界嗎？這動作沒有回頭路",
            view=view,
        )
        view.message = prompt
        await view.wait()

        if not view.confirmed:
            return

        if _lock.locked():
            await ctx.send("剛好有別的作業開始跑了，等等再試")
            return

        async with _lock:
            await ctx.send(f"回復 `{name}` 開始")
            await _notify_owner(self.bot, f"{ctx.author} 觸發回復：{name}")

            if rcon.configured():
                await ctx.send(f"先廣播提醒玩家，等 {config.QB_RCON_WARN_SECONDS} 秒再關伺服器...")
                await rcon.warn_and_wait(f"伺服器即將回復備份並重啟，{config.QB_RCON_WARN_SECONDS} 秒後關閉")

            await ctx.send("關伺服器中...")
            if not await server.stop():
                await ctx.send("伺服器沒關乾淨，回復中止，麻煩自己上去看一下")
                logger.error("qb back：關閉伺服器逾時（操作者：%s）", ctx.author)
                await _notify_owner(self.bot, f"回復中止：伺服器關閉逾時（{ctx.author}）")
                history.record("back", str(ctx.author), name, False, "伺服器關閉逾時")
                return

            snapshot_name = backup.default_filename(config.QB_PRE_RESTORE_PREFIX)
            await ctx.send(f"關好了，先幫現況存一份快照 `{snapshot_name}`...")
            await asyncio.to_thread(backup.create, snapshot_name)

            await ctx.send("快照存好了，開始回復...")
            ok, detail = await asyncio.to_thread(backup.restore, name)

            restarted = server.start()
            restart_note = "伺服器已重啟" if restarted else "但伺服器沒能正常拉起來，麻煩自己上去看一下"

            if ok:
                result = f"【成功】回復完成，{restart_note}（回復前快照：`{snapshot_name}`）"
                logger.info("回復完成：%s（操作者：%s）", name, ctx.author)
            else:
                result = f"【失敗】回復出包：{detail}，{restart_note}"
                logger.error("回復失敗：%s（操作者：%s）", detail, ctx.author)

            history.record("back", str(ctx.author), name, ok, detail)
            await ctx.send(result)
            await _notify_owner(self.bot, result)

    # ── 查看伺服器狀態與最近操作紀錄 ──────────────────────
    @commands.command(name="info")
    async def info(self, ctx: commands.Context) -> None:
        if not _authorized(ctx):
            return

        running = server.is_running()
        status_text = "線上" if running else "離線"
        lines = [f"伺服器狀態：{status_text}"]

        if running and rcon.configured():
            players = await rcon.player_summary()
            if players:
                lines.append(f"玩家：{players}")

        lines.append("")

        entries = history.recent(10)
        if not entries:
            lines.append("目前還沒有任何備份／回復紀錄")
        else:
            lines.append("最近的操作：")
            for i, entry in enumerate(entries, 1):
                mark = "成功" if entry["success"] else "失敗"
                lines.append(f"[{i}] {entry['time']}  {entry['action']}  {entry['target']}")
                lines.append(f"    操作者：{entry['user']}　結果：【{mark}】{entry['detail']}")

        await ctx.send("```text\n" + "\n".join(lines) + "\n```")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(QuickBackup(bot))
