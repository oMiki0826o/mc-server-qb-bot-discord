"""
cogs/qb.py

Modification():

- 指令全面改成 slash commands：`!!qb make`／`!!qb back` 改成
  `/qb make`／`/qb back`，`!!info` 改成 `/info`。原本「沒有權限就
  整個不回應」在 slash command 上行不通——Discord 規定互動一定要在
  時間內回應，不回應的話使用者只會看到「這個互動失敗了」這種更難懂
  的錯誤，所以沒有權限時一律回一則只有本人看得到的提示。
- 原本整段寫在指令函式裡的流程（取鎖 -> 關伺服器 -> 動檔案 -> 開
  伺服器 -> 記錄）搬到 core/qb/backup.py 的 run_backup()／
  run_restore()，這裡只負責：驗證權限、組出要顯示的訊息、把過程中
  收到的進度文字接到同一則訊息下面、把結果分岔成幾種 Discord 訊息。
  指令跟流程正式分開，這支檔案剩下的都是「介面」，看不到任何
  tmux／tarfile 的細節。
- 移除 RCON 整合：原本備份／回復前會先廣播提醒玩家、/info 會顯示
  RCON 查到的線上玩家，這整套判定為用不到的設計，一併移除，
  對應的 core/qb/rcon.py 也已刪除。
- 新增 `/qb schedule on|off`：開關每日自動備份，開關狀態由
  core/qb/scheduler.py 落地保存，重開 bot 也不會跑掉。開啟時會
  回報下一次預計執行的時間。
- 新增每日自動背景任務 `_daily_backup`：用 discord.ext.tasks 在
  設定的時間觸發，開關為關就直接跳過；跑完不論成功失敗都會私訊
  owner，成功的話另外呼叫 backup.rotate_auto_backups() 清掉太舊的
  自動備份，避免每天執行、長期下來塞滿硬碟。背景任務本身把所有
  例外都攔在內部，確保單次失敗不會讓之後每天都不會再觸發。
- 鎖從「make／back 共用一個」改成呼叫 core/qb/backup.py 裡各自
  的 backup_lock／restore_lock（相關保護實際上寫在 run_backup／
  run_restore 內部），這裡的鎖檢查只是為了在真正開始跑之前，先
  給使用者一個快速、非阻塞的提示。

Description():

- /qb make [檔名]：備份目前的世界存檔。
- /qb back [檔名]：回復到指定備份，不帶檔名會先列出現有備份；
  真正回復前需要按按鈕二次確認。
- /qb schedule <on|off>：開關每日自動備份。
- /info：查看伺服器狀態、每日自動備份開關與下次執行時間、最近 10
  筆備份／回復紀錄。
- _daily_backup：每天固定時間觸發的背景任務，開關開啟時才會真正
  執行備份。
"""

from __future__ import annotations

from datetime import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from core.logging.log import LogManager
from core.qb import backup, history, scheduler, server, state
from core.qb.exceptions import QBBusyError, QBError
from core.qb.state import State

logger = LogManager().get_logger("cogs.qb")

_STATE_LABELS: dict[State, str] = {
    State.IDLE: "閒置",
    State.STARTING: "啟動中",
    State.RUNNING: "線上",
    State.STOPPING: "關閉中",
    State.STOPPED: "離線",
    State.BACKING_UP: "備份中",
    State.RESTORING: "回復中",
    State.FAILED: "上次操作失敗",
}

# ── 每日自動備份的觸發時間，開機時就固定下來，改設定要重啟 bot 才會生效 ──────────────────────
_AUTO_BACKUP_TIME = time(
    hour=config.QB_AUTO_BACKUP_HOUR,
    minute=config.QB_AUTO_BACKUP_MINUTE,
    tzinfo=config.QB_AUTO_BACKUP_TZ,
)


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
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("只有原本下指令的人可以確認", ephemeral=True)
            return False
        return True

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
    qb_group = app_commands.Group(name="qb", description="Minecraft 伺服器備份與回復")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._daily_backup.start()

    def cog_unload(self) -> None:
        self._daily_backup.cancel()

    # ── 頻道與身分組雙重檢查 ──────────────────────
    @staticmethod
    def _authorized(interaction: discord.Interaction) -> bool:
        if interaction.channel_id != config.QB_CHANNEL_ID:
            return False
        if not isinstance(interaction.user, discord.Member):
            return False
        return any(role.id == config.QB_ROLE_ID for role in interaction.user.roles)

    # ── 備份：關伺服器 -> 壓縮 -> 重啟 ──────────────────────
    @qb_group.command(name="make", description="備份目前的世界存檔")
    @app_commands.describe(filename="備份檔名，不填就自動用時間戳記命名")
    async def make(self, interaction: discord.Interaction, filename: Optional[str] = None) -> None:
        if not self._authorized(interaction):
            await interaction.response.send_message("你沒有權限使用這個指令", ephemeral=True)
            return

        if state.backup_lock.locked() or state.server_lock.locked():
            await interaction.response.send_message(
                "現在有其他備份／回復作業在跑，等它跑完再試", ephemeral=True,
            )
            return

        name = backup.sanitize_filename(filename) if filename else backup.default_filename()
        operator = str(interaction.user)

        await interaction.response.send_message(f"準備備份為 `{name}`...")
        message = await interaction.original_response()
        lines = [message.content]

        async def progress(text: str) -> None:
            lines.append(text)
            await message.edit(content="\n".join(lines))

        await _notify_owner(self.bot, f"{operator} 觸發備份：{name}")

        try:
            outcome = await backup.run_backup(name, operator=operator, progress=progress)
        except QBBusyError as exc:
            await progress(str(exc))
        except QBError as exc:
            logger.error("備份失敗：%s（操作者：%s）", exc, operator)
            text = f"【失敗】備份出包：{exc}"
            await progress(text)
            await _notify_owner(self.bot, text)
        else:
            logger.info("備份完成：%s（%s，操作者：%s）", name, outcome.size, operator)
            text = (
                f"【成功】備份完成，檔案大小 {outcome.size}"
                f"（flow {outcome.flow_id}，耗時 {outcome.duration:.0f} 秒）"
            )
            await progress(text)
            await _notify_owner(self.bot, text)

    # ── 回復：關伺服器 -> 換上指定備份 -> 重啟 ──────────────────────
    @qb_group.command(name="back", description="回復到指定的備份")
    @app_commands.describe(filename="要回復的備份檔名，不填則列出現有備份")
    async def back(self, interaction: discord.Interaction, filename: Optional[str] = None) -> None:
        if not self._authorized(interaction):
            await interaction.response.send_message("你沒有權限使用這個指令", ephemeral=True)
            return

        if not filename:
            files = backup.list_backups()
            if not files:
                await interaction.response.send_message("備份資料夾裡空空如也", ephemeral=True)
                return
            listing = "\n".join(f"- {p.name.removesuffix('.tar.gz')}" for p in files[:10])
            await interaction.response.send_message(f"要回復哪一份？\n{listing}", ephemeral=True)
            return

        name = backup.sanitize_filename(filename)
        if not backup.exists(name):
            await interaction.response.send_message(
                f"找不到 `{name}` 這份備份，打 `/qb back` 不帶檔名可以看現有清單", ephemeral=True,
            )
            return

        if state.restore_lock.locked() or state.server_lock.locked():
            await interaction.response.send_message(
                "現在有其他備份／回復作業在跑，等它跑完再試", ephemeral=True,
            )
            return

        view = _ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            f"確定要用 `{name}` 蓋掉現在的世界嗎？這動作沒有回頭路", view=view,
        )
        message = await interaction.original_response()
        view.message = message
        await view.wait()

        if not view.confirmed:
            return

        # 按鈕的 callback 已經把這則訊息改成「收到，開始處理...」，
        # 重新抓一次目前內容，讓進度訊息接在這句後面，而不是接在
        # view.message 那個舊物件、按鈕點下去之前的確認提示文字後面
        message = await interaction.original_response()
        operator = str(interaction.user)
        lines = [message.content]

        async def progress(text: str) -> None:
            lines.append(text)
            await message.edit(content="\n".join(lines))

        await _notify_owner(self.bot, f"{operator} 觸發回復：{name}")

        try:
            outcome = await backup.run_restore(name, operator=operator, progress=progress)
        except QBBusyError as exc:
            await progress(str(exc))
        except QBError as exc:
            logger.error("回復失敗：%s（操作者：%s）", exc, operator)
            text = f"【失敗】回復出包：{exc}"
            await progress(text)
            await _notify_owner(self.bot, text)
        else:
            logger.info("回復完成：%s（操作者：%s）", name, operator)
            text = (
                f"【成功】回復完成（回復前快照：`{outcome.snapshot}`，"
                f"flow {outcome.flow_id}，耗時 {outcome.duration:.0f} 秒）"
            )
            await progress(text)
            await _notify_owner(self.bot, text)

    # ── 開關每日自動備份 ──────────────────────
    @qb_group.command(name="schedule", description="開啟或關閉每日自動備份")
    @app_commands.describe(action="on 開啟、off 關閉")
    @app_commands.choices(action=[
        app_commands.Choice(name="on", value="on"),
        app_commands.Choice(name="off", value="off"),
    ])
    async def schedule(self, interaction: discord.Interaction, action: app_commands.Choice[str]) -> None:
        if not self._authorized(interaction):
            await interaction.response.send_message("你沒有權限使用這個指令", ephemeral=True)
            return

        enabled = action.value == "on"
        scheduler.set_enabled(enabled)
        logger.info("每日自動備份設定為 %s（操作者：%s）", "開啟" if enabled else "關閉", interaction.user)

        if not enabled:
            await interaction.response.send_message("已關閉每日自動備份", ephemeral=True)
            return

        next_run = self._daily_backup.next_iteration
        when = ""
        if next_run is not None:
            when = f"，下次執行時間約為 {next_run.astimezone(config.QB_AUTO_BACKUP_TZ):%Y-%m-%d %H:%M}"
        await interaction.response.send_message(f"已開啟每日自動備份{when}", ephemeral=True)

    # ── 查看伺服器狀態與最近操作紀錄 ──────────────────────
    @app_commands.command(name="info", description="查看伺服器狀態與最近的備份／回復紀錄")
    async def info(self, interaction: discord.Interaction) -> None:
        if not self._authorized(interaction):
            await interaction.response.send_message("你沒有權限使用這個指令", ephemeral=True)
            return

        current_state = await server.status()
        lines = [f"伺服器狀態：{_STATE_LABELS.get(current_state, current_state.value)}"]

        auto_text = "開啟" if scheduler.is_enabled() else "關閉"
        next_run = self._daily_backup.next_iteration
        if scheduler.is_enabled() and next_run is not None:
            auto_text += f"（下次執行：{next_run.astimezone(config.QB_AUTO_BACKUP_TZ):%Y-%m-%d %H:%M}）"
        lines.append(f"每日自動備份：{auto_text}")
        lines.append("")

        entries = history.recent(10)
        if not entries:
            lines.append("目前還沒有任何備份／回復紀錄")
        else:
            lines.append("最近的操作：")
            for i, entry in enumerate(entries, 1):
                mark = "成功" if entry.success else "失敗"
                duration_text = f"，耗時 {entry.duration:.0f} 秒" if entry.duration is not None else ""
                lines.append(f"[{i}] {entry.time}　{entry.action}　{entry.target}")
                lines.append(f"    操作者：{entry.user}　結果：【{mark}】{duration_text}　{entry.detail}")

        await interaction.response.send_message("```text\n" + "\n".join(lines) + "\n```")

    # ── 每日自動備份背景任務：所有例外都攔在這裡，單次失敗不影響隔天繼續跑 ──────────────────────
    @tasks.loop(time=_AUTO_BACKUP_TIME)
    async def _daily_backup(self) -> None:
        try:
            await self._run_daily_backup()
        except Exception:
            # 這裡刻意接住「所有」例外，不只 QBError：tasks.loop 一旦讓例外
            # 逃出這個函式，整個排程就會永久停止，之後每天都不會再觸發，
            # 必須確保無論出什麼包，明天都還會再試一次。
            logger.exception("每日自動備份發生未預期的錯誤")

    async def _run_daily_backup(self) -> None:
        if not scheduler.is_enabled():
            return

        name = backup.default_filename(config.QB_AUTO_BACKUP_PREFIX)
        logger.info("每日自動備份開始：%s", name)

        try:
            outcome = await backup.run_backup(name, operator="每日自動備份")
        except QBError as exc:
            logger.error("每日自動備份失敗：%s", exc)
            await _notify_owner(self.bot, f"【失敗】每日自動備份失敗：{exc}")
            return

        removed = backup.rotate_auto_backups(config.QB_AUTO_BACKUP_PREFIX, config.QB_AUTO_BACKUP_KEEP)
        if removed:
            logger.info("自動備份輪替：刪除 %d 份舊備份", len(removed))

        await _notify_owner(
            self.bot,
            f"【成功】每日自動備份完成，大小 {outcome.size}（耗時 {outcome.duration:.0f} 秒）",
        )

    @_daily_backup.before_loop
    async def _before_daily_backup(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(QuickBackup(bot))
