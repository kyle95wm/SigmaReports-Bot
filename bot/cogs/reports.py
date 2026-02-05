import discord
from discord import app_commands
from discord.ext import commands

from bot.modals import TVReportModal, VODReportModal

# Owner-only for /reportpings
REPORTPINGS_OWNER_ID = 1229271933736976395


class Reports(commands.Cog):
    def __init__(self, bot, db, cfg):
        self.bot = bot
        self.db = db
        self.cfg = cfg

    # ---- helpers ----

    def _allowed_channel(self, interaction: discord.Interaction) -> bool:
        # cfg.reports_channel_ids is your comma-list env var
        return bool(interaction.channel) and interaction.channel.id in set(self.cfg.reports_channel_ids)

    def _allowed_channels_hint(self, interaction: discord.Interaction) -> str:
        if not interaction.guild:
            return "the allowed channels"

        mentions = []
        for cid in self.cfg.reports_channel_ids:
            ch = interaction.guild.get_channel(cid)
            if ch:
                mentions.append(ch.mention)

        return ", ".join(mentions) if mentions else "the allowed channels"

    # ---- slash commands ----

    @app_commands.command(
        name="report-tv",
        description="Report an issue with a live TV channel (buffering, offline, wrong content, etc.)",
    )
    async def report_tv(self, interaction: discord.Interaction):
        if not self._allowed_channel(interaction):
            return await interaction.response.send_message(
                f"Use this command in: {self._allowed_channels_hint(interaction)}."
            )

        await interaction.response.send_modal(TVReportModal(self.db, self.cfg))

    @app_commands.command(
        name="report-vod",
        description="Report an issue with a movie or TV show (playback, missing episodes, quality issues, etc.)",
    )
    async def report_vod(self, interaction: discord.Interaction):
        if not self._allowed_channel(interaction):
            return await interaction.response.send_message(
                f"Use this command in: {self._allowed_channels_hint(interaction)}."
            )

        await interaction.response.send_modal(VODReportModal(self.db, self.cfg))

    @app_commands.command(
        name="reportpings",
        description="Toggle staff pings for new reports (owner only).",
    )
    async def reportpings(self, interaction: discord.Interaction):
        if interaction.user.id != REPORTPINGS_OWNER_ID:
            return await interaction.response.send_message(
                "❌ You are not allowed to use this command.",
                ephemeral=True,
            )

        enabled = self.db.toggle_report_pings()
        state = "ON 🔔" if enabled else "OFF 🔕"
        await interaction.response.send_message(
            f"Staff pings for new reports are now: **{state}**",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Reports(bot, bot.db, bot.cfg))
