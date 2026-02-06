import discord
from bot.db import ReportDB
from bot.utils import build_staff_embed, report_subject, try_dm

from bot.modals import TVReportModal, VODReportModal


class StaffFollowUpModal(discord.ui.Modal, title="Send follow-up message"):
    message = discord.ui.TextInput(
        label="Message to send",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        placeholder="Type the follow-up you want the reporter to receive...",
    )

    def __init__(self, db: ReportDB, staff_message_id: int):
        super().__init__()
        self.db = db
        self.staff_message_id = staff_message_id

    async def on_submit(self, interaction: discord.Interaction):
        report = self.db.get_by_staff_message_id(self.staff_message_id)
        if not report:
            return await interaction.response.send_message("❌ Report not found.")

        if not interaction.guild:
            return await interaction.response.send_message("❌ This must be used in a server.")

        try:
            reporter = await interaction.client.fetch_user(report["reporter_id"])
        except Exception:
            reporter = interaction.client.get_user(report["reporter_id"])

        if not reporter:
            return await interaction.response.send_message("❌ Could not find reporter.")

        source = interaction.guild.get_channel(report["source_channel_id"]) or interaction.channel
        subject = report_subject(report["report_type"], report["payload"])

        text = (self.message.value or "").strip()
        if not text:
            return await interaction.response.send_message("❌ Follow-up message can’t be empty.")

        public_msg = f"💬 {reporter.mention} follow-up on report **#{report['id']}** (**{subject}**): {text}"
        dm_msg = f"💬 Follow-up on your report #{report['id']} ({subject}): {text}"

        try:
            if isinstance(source, discord.TextChannel):
                await source.send(public_msg)
        except discord.Forbidden:
            pass

        await try_dm(reporter, dm_msg)
        await interaction.response.send_message("✅ Follow-up sent.")


class ReportActionView(discord.ui.View):
    def __init__(self, db: ReportDB, staff_channel_id: int, support_channel_id: int, public_updates: bool):
        super().__init__(timeout=None)
        self.db = db
        self.staff_channel_id = staff_channel_id
        self.support_channel_id = support_channel_id
        self.public_updates = public_updates

    @discord.ui.button(label="Resolved", style=discord.ButtonStyle.success, custom_id="report:resolved")
    async def resolved(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_status(interaction, "Resolved")

    @discord.ui.button(label="Can't replicate", style=discord.ButtonStyle.secondary, custom_id="report:cant")
    async def cant(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_status(interaction, "Can't replicate")

    @discord.ui.button(label="More info required", style=discord.ButtonStyle.primary, custom_id="report:more_info")
    async def more_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_status(interaction, "More info required")

    @discord.ui.button(label="Send follow-up", style=discord.ButtonStyle.secondary, custom_id="report:followup")
    async def follow_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not interaction.channel:
            return await interaction.response.send_message("❌ This can only be used in a server.")

        if self.staff_channel_id and interaction.channel.id != self.staff_channel_id:
            return await interaction.response.send_message("❌ Use this in the staff reports channel.")

        if not interaction.message:
            return await interaction.response.send_message("❌ Couldn’t read the report message.")

        await interaction.response.send_modal(StaffFollowUpModal(self.db, interaction.message.id))

    async def _handle_status(self, interaction: discord.Interaction, status: str):
        if not interaction.guild or not interaction.channel:
            return await interaction.response.send_message("❌ This can only be used in a server.")

        if self.staff_channel_id and interaction.channel.id != self.staff_channel_id:
            return await interaction.response.send_message("❌ Use staff buttons in the staff reports channel.")

        if not interaction.message:
            return await interaction.response.send_message("❌ Couldn’t read the report message.")

        report = self.db.get_by_staff_message_id(interaction.message.id)
        if not report:
            return await interaction.response.send_message("❌ Report not found.")

        self.db.update_status(report["id"], status)

        try:
            reporter = await interaction.client.fetch_user(report["reporter_id"])
        except Exception:
            reporter = interaction.client.get_user(report["reporter_id"])

        if not reporter:
            return await interaction.response.send_message("❌ Could not find reporter.")

        source = interaction.guild.get_channel(report["source_channel_id"]) or interaction.channel
        subject = report_subject(report["report_type"], report["payload"])

        embed = build_staff_embed(
            report["id"],
            report["report_type"],
            reporter,
            source,
            report["payload"],
            status,
        )

        # Only disable status buttons for terminal outcomes
        if status in ("Resolved", "Can't replicate"):
            for child in self.children:
                if isinstance(child, discord.ui.Button) and child.custom_id in (
                    "report:resolved",
                    "report:cant",
                    "report:more_info",
                ):
                    child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)

        if status == "Resolved":
            emoji = "✅"
        elif status == "Can't replicate":
            emoji = "⚠️"
        elif status == "More info required":
            emoji = "📝"
        else:
            emoji = "🔔"

        public_update = f"{emoji} {reporter.mention} update on report **#{report['id']}** (**{subject}**): **{status}**."
        dm_update = f"{emoji} Update on your report #{report['id']} ({subject}): {status}."

        try:
            if isinstance(source, discord.TextChannel) and self.public_updates:
                await source.send(public_update)
        except discord.Forbidden:
            pass

        await try_dm(reporter, dm_update)

        if status == "Can't replicate":
            support = interaction.guild.get_channel(self.support_channel_id) if self.support_channel_id else None
            msg = (
                f"⚠️ We are unable to replicate the issue. Please open a ticket in {support.mention} so we can assist further."
                if support
                else "⚠️ We are unable to replicate the issue. Please open a ticket so we can assist further."
            )

            try:
                if isinstance(source, discord.TextChannel) and self.public_updates:
                    await source.send(f"{reporter.mention} {msg}")
            except discord.Forbidden:
                pass

            await try_dm(reporter, msg)

        if status == "More info required":
            msg = (
                f"📝 We need more information for **report #{report['id']}** (**{subject}**).\n"
                f"Please re-submit your report with more details, such as:\n"
                f"• what you expected vs what happened\n"
                f"• when it occurred\n"
                f"• device/app used\n"
                f"• any error messages"
            )

            try:
                if isinstance(source, discord.TextChannel) and self.public_updates:
                    await source.send(f"{reporter.mention} {msg}")
            except discord.Forbidden:
                pass

            await try_dm(reporter, msg)


class ReportPanelView(discord.ui.View):
    """
    A persistent "report panel" with two buttons that open the TV/VOD report modals.
    """
    def __init__(self, db: ReportDB, cfg):
        super().__init__(timeout=None)
        self.db = db
        self.cfg = cfg

    def _allowed_channel(self, interaction: discord.Interaction) -> bool:
        return bool(interaction.channel) and interaction.channel.id in set(self.cfg.reports_channel_ids)

    def _support_channel_mention(self, interaction: discord.Interaction) -> str:
        if not interaction.guild or not self.cfg.support_channel_id:
            return "the support channel"
        ch = interaction.guild.get_channel(self.cfg.support_channel_id)
        return ch.mention if ch else "the support channel"

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
            msg = (
                f"🚫 {interaction.user.mention} you are temporarily blocked from using the report system.\n"
                f"To appeal, please open a ticket in {support}.{reason_txt}"
            )

        await interaction.response.send_message(msg)
        return False

    @discord.ui.button(
        label="Report Live TV",
        style=discord.ButtonStyle.primary,
        emoji="📺",
        custom_id="panel:report_tv",
    )
    async def panel_report_tv(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._allowed_channel(interaction):
            return await interaction.response.send_message("Please use the report panel in the designated reports channel.")
        if not await self._block_gate(interaction):
            return
        await interaction.response.send_modal(TVReportModal(self.db, self.cfg))

    @discord.ui.button(
        label="Report Movie / TV Show",
        style=discord.ButtonStyle.secondary,
        emoji="🎬",
        custom_id="panel:report_vod",
    )
    async def panel_report_vod(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._allowed_channel(interaction):
            return await interaction.response.send_message("Please use the report panel in the designated reports channel.")
        if not await self._block_gate(interaction):
            return
        await interaction.response.send_modal(VODReportModal(self.db, self.cfg))
