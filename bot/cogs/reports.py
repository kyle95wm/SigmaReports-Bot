import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from bot.modals import TVReportModal, VODReportModal
from bot.views import ReportActionView
from bot.utils import build_staff_embed

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

    # ----------------------------
    # Helpers
    # ----------------------------

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

        blocked, is_perm, expires_at, reason = self.db.is_user_blocked(
            interaction.guild.id, interaction.user.id
        )

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

    # ----------------------------
    # Report Commands
    # ----------------------------

    @app_commands.command(
        name="report-tv",
        description="Report an issue with a live TV channel.",
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
        description="Report an issue with a movie or TV show.",
    )
    async def report_vod(self, interaction: discord.Interaction):
        if not self._allowed_channel(interaction):
            return await interaction.response.send_message(
                f"Use this command in: {self._allowed_channels_hint(interaction)}."
            )

        if not await self._block_gate(interaction):
            return

        await interaction.response.send_modal(VODReportModal(self.db, self.cfg))

    # ----------------------------
    # Owner / Admin
    # ----------------------------

    @app_commands.command(
        name="reportpings",
        description="Toggle staff pings for new reports (owner only).",
    )
    async def reportpings(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        enabled = self.db.toggle_report_pings()
        state = "ON 🔔" if enabled else "OFF 🔕"
        await interaction.response.send_message(
            f"Staff pings for new reports are now: **{state}**",
            ephemeral=True,
        )

    @app_commands.command(
        name="synccommands",
        description="Force re-sync slash commands for this server (owner only).",
    )
    async def synccommands(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        if not interaction.guild:
            return await interaction.response.send_message(
                "This must be used in a server.",
                ephemeral=True,
            )

        guild = discord.Object(id=interaction.guild.id)

        await interaction.response.send_message("Syncing…", ephemeral=True)

        self.bot.tree.copy_global_to(guild=guild)
        synced = await self.bot.tree.sync(guild=guild)

        await interaction.followup.send(
            f"✅ Synced **{len(synced)}** commands.",
            ephemeral=True,
        )

    # ----------------------------
    # Reactivate
    # ----------------------------

    @app_commands.command(
        name="reportreactivate",
        description="Re-activate staff buttons for a report (reopens it to Open).",
    )
    @app_commands.describe(report_id="The numeric report ID (e.g. 123)")
    async def reportreactivate(self, interaction: discord.Interaction, report_id: int):
        if not interaction.guild:
            return await interaction.response.send_message(
                "This must be used in a server.",
                ephemeral=True,
            )

        if not self._is_staff(interaction):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        report = self.db.get_report_by_id(report_id)
        if not report or report["guild_id"] != interaction.guild.id:
            return await interaction.response.send_message("❌ Report not found.", ephemeral=True)

        staff_message_id = report.get("staff_message_id")
        if not staff_message_id:
            return await interaction.response.send_message(
                "❌ This report has no linked staff message.",
                ephemeral=True,
            )

        staff_ch = interaction.guild.get_channel(self.cfg.staff_channel_id)
        if not staff_ch:
            return await interaction.response.send_message("❌ Staff channel not found.", ephemeral=True)

        try:
            staff_msg = await staff_ch.fetch_message(int(staff_message_id))
        except Exception:
            return await interaction.response.send_message(
                "❌ Could not fetch the staff report message.",
                ephemeral=True,
            )

        # Reopen
        self.db.update_status(report_id, "Open")
        report["status"] = "Open"

        try:
            reporter = await interaction.client.fetch_user(report["reporter_id"])
        except Exception:
            reporter = interaction.client.get_user(report["reporter_id"]) or interaction.user

        source = interaction.guild.get_channel(report["source_channel_id"]) or staff_ch

        embed = build_staff_embed(
            report["id"],
            report["report_type"],
            reporter,
            source,
            report["payload"],
            "Open",
        )

        # ✅ FIXED: now includes staff_role_id
        view = ReportActionView(
            self.db,
            self.cfg.staff_channel_id,
            self.cfg.support_channel_id,
            self.cfg.public_updates,
            self.cfg.staff_role_id,
        )

        await staff_msg.edit(embed=embed, view=view)

        await interaction.response.send_message(
            f"✅ Re-activated buttons for report **#{report_id}**.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Reports(bot, bot.db, bot.cfg))
