import discord
from bot.db import ReportDB
from bot.utils import build_staff_embed, report_subject, try_dm
from bot.views import ReportActionView


def build_staff_ping(ping_ids: list[int]) -> str:
    if not ping_ids:
        return ""
    return " ".join(f"<@{uid}>" for uid in ping_ids)


class TVReportModal(discord.ui.Modal, title="Report TV Issue"):
    channel_name = discord.ui.TextInput(label="Channel name", max_length=100)
    channel_category = discord.ui.TextInput(label="Channel category", max_length=100)
    issue = discord.ui.TextInput(label="What’s the issue?", style=discord.TextStyle.paragraph)

    def __init__(self, db: ReportDB, cfg):
        super().__init__()
        self.db = db
        self.cfg = cfg

    async def on_submit(self, interaction: discord.Interaction):
        payload = {
            "channel_name": str(self.channel_name),
            "channel_category": str(self.channel_category),
            "issue": str(self.issue),
        }

        report_id = self.db.create_report(
            "tv",
            interaction.user.id,
            interaction.guild.id,
            interaction.channel.id,
            payload,
        )

        staff_channel = interaction.guild.get_channel(self.cfg.staff_channel_id)
        if not isinstance(staff_channel, discord.TextChannel):
            return await interaction.response.send_message("❌ Staff channel not found.", ephemeral=True)

        embed = build_staff_embed(
            report_id,
            "tv",
            interaction.user,
            interaction.channel,
            payload,
            "Open",
        )

        view = ReportActionView(
            self.db,
            self.cfg.staff_channel_id,
            self.cfg.support_channel_id,
            self.cfg.public_updates,
            self.cfg.staff_role_id,
        )

        ping_text = ""
        if self.db.get_report_pings_enabled():
            ping_text = build_staff_ping(self.cfg.staff_ping_user_ids)

        msg = await staff_channel.send(content=ping_text, embed=embed, view=view)
        self.db.set_staff_message_id(report_id, msg.id)

        await interaction.response.send_message(
            f"✅ Submitted TV report **#{report_id}** for **{payload['channel_name']}**.",
            ephemeral=True,
        )


class VODReportModal(discord.ui.Modal, title="Report VOD Issue"):
    title_name = discord.ui.TextInput(label="Title (movie or show + S/E)", max_length=150)

    reference_link = discord.ui.TextInput(
        label="Reference link (TheTVDB / TMDB / IMDb)",
        max_length=300,
        placeholder="Paste a link that matches the exact title",
    )

    quality = discord.ui.TextInput(label="Quality (FHD or 4K)", max_length=10)
    issue = discord.ui.TextInput(label="What’s the issue?", style=discord.TextStyle.paragraph)

    def __init__(self, db: ReportDB, cfg):
        super().__init__()
        self.db = db
        self.cfg = cfg

    async def on_submit(self, interaction: discord.Interaction):
        q = str(self.quality).upper()
        if q not in ("FHD", "4K"):
            q = "Unknown"

        payload = {
            "title": str(self.title_name),
            "reference_link": str(self.reference_link),
            "quality": q,
            "issue": str(self.issue),
        }

        report_id = self.db.create_report(
            "vod",
            interaction.user.id,
            interaction.guild.id,
            interaction.channel.id,
            payload,
        )

        staff_channel = interaction.guild.get_channel(self.cfg.staff_channel_id)
        if not isinstance(staff_channel, discord.TextChannel):
            return await interaction.response.send_message("❌ Staff channel not found.", ephemeral=True)

        embed = build_staff_embed(
            report_id,
            "vod",
            interaction.user,
            interaction.channel,
            payload,
            "Open",
        )

        view = ReportActionView(
            self.db,
            self.cfg.staff_channel_id,
            self.cfg.support_channel_id,
            self.cfg.public_updates,
            self.cfg.staff_role_id,
        )

        ping_text = ""
        if self.db.get_report_pings_enabled():
            ping_text = build_staff_ping(self.cfg.staff_ping_user_ids)

        msg = await staff_channel.send(content=ping_text, embed=embed, view=view)
        self.db.set_staff_message_id(report_id, msg.id)

        await interaction.response.send_message(
            f"✅ Submitted VOD report **#{report_id}** for **{payload['title']}** ({q}).",
            ephemeral=True,
        )


class ResolveReportModal(discord.ui.Modal):
    """
    Staff-only modal shown when pressing Resolve (either from staff channel or inside a ticket).
    Optional notes are:
      - included in the DM to the reporter
      - shown on the staff embed
    """

    details = discord.ui.TextInput(
        label="Resolution details (optional)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
        placeholder="Anything you want the reporter to know (optional)",
    )

    def __init__(
        self,
        db: ReportDB,
        staff_channel_id: int,
        support_channel_id: int,
        public_updates: bool,
        staff_role_id: int,
        report_id: int,
        *,
        delete_current_channel: bool = False,
        close_ticket_channel: bool = False,
    ):
        super().__init__(title=f"Resolve Report #{int(report_id)}")
        self.db = db
        self.staff_channel_id = int(staff_channel_id or 0)
        self.support_channel_id = int(support_channel_id or 0)
        self.public_updates = bool(public_updates)
        self.staff_role_id = int(staff_role_id or 0)
        self.report_id = int(report_id)
        self.delete_current_channel = bool(delete_current_channel)
        self.close_ticket_channel = bool(close_ticket_channel)

    async def _close_ticket_channel_if_any(self, guild: discord.Guild):
        """
        Best-effort: delete an open ticket channel for this report.
        If we can't delete it, rename it so it's obviously closed.
        Always clears the DB ticket_channel_id if it was set.
        """
        ticket_id = None
        try:
            ticket_id = self.db.get_ticket_channel_id(self.report_id)
        except Exception:
            ticket_id = None

        if not ticket_id:
            return

        ch = guild.get_channel(int(ticket_id))
        if isinstance(ch, discord.TextChannel):
            try:
                await ch.delete(reason=f"Report #{self.report_id} resolved")
            except discord.Forbidden:
                try:
                    await ch.edit(name=f"closed-report-{self.report_id}")
                except Exception:
                    pass
            except Exception:
                pass

        try:
            self.db.set_ticket_channel_id(self.report_id, None)
        except Exception:
            pass

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)

        report = self.db.get_report_by_id(self.report_id)
        if not report or int(report.get("guild_id", 0)) != interaction.guild.id:
            return await interaction.response.send_message("❌ Report not found.", ephemeral=True)

        resolver_id = int(interaction.user.id)
        note = str(self.details).strip()

        # If resolving from staff channel, close any ticket channel first
        if self.close_ticket_channel:
            await self._close_ticket_channel_if_any(interaction.guild)

        # Mark resolved in DB (best-effort for your DB variants)
        if hasattr(self.db, "mark_resolved"):
            try:
                self.db.mark_resolved(self.report_id, resolver_id)  # type: ignore[attr-defined]
            except Exception:
                self.db.update_status(self.report_id, "Resolved")
        else:
            self.db.update_status(self.report_id, "Resolved")

        # Refresh report (so claimed fields, etc. are current)
        report = self.db.get_report_by_id(self.report_id) or report

        # Update staff message embed + disable buttons
        if self.staff_channel_id and report.get("staff_message_id"):
            try:
                staff_channel = interaction.guild.get_channel(self.staff_channel_id)
                if isinstance(staff_channel, discord.TextChannel):
                    staff_msg = await staff_channel.fetch_message(int(report["staff_message_id"]))

                    reporter = await interaction.client.fetch_user(int(report["reporter_id"]))
                    source = interaction.guild.get_channel(int(report["source_channel_id"])) or staff_channel

                    claimed_by = report.get("claimed_by_user_id")
                    claimed_at = report.get("claimed_at")

                    embed = build_staff_embed(
                        self.report_id,
                        report["report_type"],
                        reporter,
                        source,
                        report["payload"],
                        "Resolved",
                        ticket_channel_id=None,  # don't show dead ticket link
                        claimed_by_user_id=claimed_by,
                        claimed_at=claimed_at,
                        resolved_by_id=resolver_id,
                        resolved_note=note or None,
                    )

                    view = ReportActionView(
                        db=self.db,
                        staff_channel_id=self.staff_channel_id,
                        support_channel_id=self.support_channel_id,
                        public_updates=self.public_updates,
                        staff_role_id=self.staff_role_id,
                    )
                    view.disable_all()

                    await staff_msg.edit(embed=embed, view=view)
            except Exception:
                pass

        # DM reporter with optional note
        try:
            reporter = await interaction.client.fetch_user(int(report["reporter_id"]))
            subj = report_subject(report["report_type"], report["payload"])
            msg = f"✅ Update on your report #{self.report_id} ({subj}): **Resolved**."
            if note:
                msg += f"\n\nDetails: {note}"
            await try_dm(reporter, msg)
        except Exception:
            pass

        # Always clear ticket reference (even if we didn't/couldn't delete channel)
        try:
            self.db.set_ticket_channel_id(self.report_id, None)
        except Exception:
            pass

        await interaction.response.send_message("✅ Resolved.", ephemeral=True)

        # If this was invoked inside the ticket, delete/rename the ticket channel
        if self.delete_current_channel and interaction.channel:
            try:
                await interaction.channel.delete(reason=f"Resolved ticket for report #{self.report_id}")
            except discord.Forbidden:
                try:
                    await interaction.channel.edit(name=f"closed-report-{self.report_id}")
                except Exception:
                    pass
            except Exception:
                pass
