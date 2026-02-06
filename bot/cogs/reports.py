import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from bot.modals import TVReportModal, VODReportModal
from bot.views import ReportPanelView

OWNER_ID = 1229271933736976395


def _iso_to_discord_ts(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ts = int(dt.timestamp())
        return f"<t:{ts}:R>"
    except Exception:
        return iso


class Reports(commands.Cog):
    def __init__(self, bot, db, cfg):
        self.bot = bot
        self.db = db
        self.cfg = cfg

    def _allowed_channel(self, interaction: discord.Interaction) -> bool:
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

    def _support_channel_mention(self, interaction: discord.Interaction) -> str:
        if not interaction.guild or not self.cfg.support_channel_id:
            return "the support channel"
        ch = interaction.guild.get_channel(self.cfg.support_channel_id)
        return ch.mention if ch else "the support channel"

    def _is_staff(self, interaction: discord.Interaction) -> bool:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member:
            return False
        return any(r.id == self.cfg.staff_role_id for r in member.roles)

    async def _block_gate(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return True

        blocked, is_perm, expires_at, reason = self.db.is_user_blocked(interaction.guild.id, interaction.user.id)
        if not blocked:
            return True

        support = self._support_channel_mention(interaction)
        reason_txt = f"\nReason: {reason}" if reason else ""

        if is_perm:
            msg = (
                f"🚫 {interaction.user.mention} you are blocked from using the report system.\n"
                f"To appeal, please open a ticket in {support}.{reason_txt}"
            )
        else:
            exp = f"\nBlock expires: {_iso_to_discord_ts(expires_at)}" if expires_at else ""
            msg = (
                f"🚫 {interaction.user.mention} you are temporarily blocked from using the report system."
                f"{exp}\nTo appeal, please open a ticket in {support}.{reason_txt}"
            )

        await interaction.response.send_message(msg)
        return False

    @app_commands.command(
        name="report-tv",
        description="Report an issue with a live TV channel (buffering, offline, wrong content, etc.)",
    )
    async def report_tv(self, interaction: discord.Interaction):
        if not self._allowed_channel(interaction):
            return await interaction.response.send_message(
                f"Use this command in: {self._allowed_channels_hint(interaction)}."
            )
        if not await self._block_gate(interaction):
            return
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
        if not await self._block_gate(interaction):
            return
        await interaction.response.send_modal(VODReportModal(self.db, self.cfg))

    @app_commands.command(
        name="reportpings",
        description="Toggle staff pings for new reports (owner only).",
    )
    async def reportpings(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        enabled = self.db.toggle_report_pings()
        state = "ON 🔔" if enabled else "OFF 🔕"
        await interaction.response.send_message(f"Staff pings for new reports are now: **{state}**", ephemeral=True)

    @app_commands.command(
        name="synccommands",
        description="Force re-sync slash commands for this server (owner only).",
    )
    @app_commands.describe(cleanup="If true, clears global + server commands first (use only if duplicates happen).")
    async def synccommands(self, interaction: discord.Interaction, cleanup: bool = False):
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message("This must be used in a server.", ephemeral=True)

        guild = discord.Object(id=interaction.guild.id)
        await interaction.response.send_message("Syncing commands…", ephemeral=True)

        if cleanup:
            self.bot.tree.clear_commands(guild=None)
            await self.bot.tree.sync()
            self.bot.tree.clear_commands(guild=guild)
            await self.bot.tree.sync(guild=guild)

        self.bot.tree.copy_global_to(guild=guild)
        synced = await self.bot.tree.sync(guild=guild)
        await interaction.followup.send(f"✅ Synced **{len(synced)}** commands.", ephemeral=True)

    @app_commands.command(
        name="reportpanel",
        description="Post a report panel embed with buttons (staff only).",
    )
    @app_commands.describe(channel="Channel to post the report panel in")
    async def reportpanel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.guild:
            return await interaction.response.send_message("This must be used in a server.", ephemeral=True)
        if not self._is_staff(interaction):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        # Nice panel embed
        embed = discord.Embed(
            title="Report an Issue",
            description=(
                "Use the buttons below to submit a report.\n\n"
                "**📺 Live TV** — buffering, offline channels, wrong content\n"
                "**🎬 Movies / TV Shows** — playback issues, missing episodes, quality problems\n\n"
                "Please include as much detail as possible so staff can investigate faster."
            ),
        )
        embed.set_footer(text="Reports are reviewed by staff — you may receive updates in this channel and/or via DM.")

        view = ReportPanelView(self.db, self.cfg)

        try:
            await channel.send(embed=embed, view=view)
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ I don’t have permission to post in that channel.",
                ephemeral=True,
            )

        await interaction.response.send_message(f"✅ Posted a report panel in {channel.mention}.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Reports(bot, bot.db, bot.cfg))
