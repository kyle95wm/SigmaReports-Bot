import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from bot.modals import TVReportModal, VODReportModal

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
        name="reportblock",
        description="Block a user from using /report commands (staff only).",
    )
    @app_commands.describe(
        user="User to block",
        duration_minutes="Minutes to block (leave empty for permanent)",
        reason="Optional reason shown to the user",
    )
    async def reportblock(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        duration_minutes: int | None = None,
        reason: str | None = None,
    ):
        if not interaction.guild:
            return await interaction.response.send_message("This must be used in a server.", ephemeral=True)
        if not self._is_staff(interaction):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        self.db.block_user(
            guild_id=interaction.guild.id,
            user_id=user.id,
            created_by=interaction.user.id,
            duration_minutes=duration_minutes,
            reason=(reason or "").strip(),
        )

        if duration_minutes is None:
            await interaction.response.send_message(f"✅ Blocked {user.mention} permanently.", ephemeral=True)
        else:
            await interaction.response.send_message(f"✅ Blocked {user.mention} for {duration_minutes} minutes.", ephemeral=True)

    @app_commands.command(
        name="reportunblock",
        description="Remove a report-system block from a user (staff only).",
    )
    @app_commands.describe(user="User to unblock")
    async def reportunblock(self, interaction: discord.Interaction, user: discord.User):
        if not interaction.guild:
            return await interaction.response.send_message("This must be used in a server.", ephemeral=True)
        if not self._is_staff(interaction):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        removed = self.db.unblock_user(interaction.guild.id, user.id)
        if removed:
            await interaction.response.send_message(f"✅ Unblocked {user.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message(f"ℹ️ {user.mention} wasn’t blocked.", ephemeral=True)

    @app_commands.command(
        name="reportblocks",
        description="List users currently blocked from using the report system (staff only).",
    )
    async def reportblocks(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("This must be used in a server.", ephemeral=True)
        if not self._is_staff(interaction):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        blocks = self.db.list_blocks(interaction.guild.id)
        if not blocks:
            return await interaction.response.send_message("No blocked users right now.", ephemeral=True)

        lines = []
        for b in blocks[:20]:
            user_id = b["user_id"]
            if b["is_permanent"]:
                status = "Permanent"
            else:
                status = f"Until {_iso_to_discord_ts(b['expires_at'])}" if b.get("expires_at") else "Temporary"
            reason = f" — {b['reason']}" if b.get("reason") else ""
            lines.append(f"<@{user_id}> (`{user_id}`) — **{status}**{reason}")

        extra = ""
        if len(blocks) > 20:
            extra = f"\n…and {len(blocks) - 20} more."

        embed = discord.Embed(
            title=f"Blocked users ({len(blocks)})",
            description="\n".join(lines) + extra,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Reports(bot, bot.db, bot.cfg))
