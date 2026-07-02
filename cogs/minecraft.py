"""
cogs/minecraft.py

Modification():

- 從專案外的散裝檔案接進來，路徑改成照專案慣例放在 core/minecraft 下。
- 補上型別註記、統一成這個專案的檔頭／區塊註解格式。運算邏輯完全沒動，
  仍然是呼叫 core/minecraft/mc_pearl_calculator.py 的 run()。

Description():

- 提供 /pearl slash command，包一層很薄的 Discord 介面，
  實際運算全部丟給 core/minecraft/mc_pearl_calculator.py。
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.minecraft import mc_pearl_calculator, mc_pearl_config


# ── 珍珠砲計算機 Cog ──────────────────────

class Minecraft(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /pearl：算 TNT 珍珠砲落點 ──────────────────────
    @app_commands.command(name="pearl", description="珍珠炮計算機")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        px="84gt 珍珠 X 座標",
        py="84gt 珍珠 Y 座標",
        pz="84gt 珍珠 Z 座標",
        dx="目的地 X 座標",
        dz="目的地 Z 座標",
        ground_height="地面高度（預設128）",
    )
    async def pearl(
        self,
        interaction: discord.Interaction,
        px: float,
        py: float,
        pz: float,
        dx: float,
        dz: float,
        ground_height: int = 128,
    ) -> None:
        mc_pearl_config.ground_height = ground_height
        mc_pearl_config.projectedPos = [px, py, pz]
        mc_pearl_config.destination_x = dx
        mc_pearl_config.destination_z = dz

        result = mc_pearl_calculator.run()

        await interaction.response.send_message(f"```text\n{result}\n```")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Minecraft(bot))
