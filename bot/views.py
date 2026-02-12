from __future__ import annotations

import discord

from bot.db import ReportDB
from bot.utils import build_staff_embed, report_subject, try_dm


# legacy-safe (older DB rows may still have these)
CLOSED_STATUSES = {"Resolved", "Can't replicate", "Fixed"}

# Ticket category (channels will be created under here)
TICKETS_CATEGORY_ID = 1458642805437239397


def _nice_ref_label(url: str) -> str:
    u = (url or "").strip()
    low = u.lower()
    if "thetvdb" in low:
        return "TheTVDB"
    if "themoviedb" in low or "tmdb" in low:
        return "TMDB"
    if "imdb" in low:
        return "IMDb"
    return "Reference"


def _build_ticket_embed(
    report: dict,
    reporter: discord.abc.User,
    guild: discord.Guild,
) -> discord.Embed:
    """
    Ticket header embed shown in the ticket channel.
    Includes the original report details so staff don't have to go back to the staff channel.
    """
    rid = int(report["id"])
    rtype = str(report["report_type"] or "").upper()
    payload = report.get("payload") or {}
    subject = report_subject(report["report_type"], payload)

    src = guild.get_channel(int(report["source_channel_id"])) if report.get("source_channel_id") else None
    src_text = src.mention if isinstance(src, discord.TextChannel) else "Unknown"

    embed = discord.Embed(
        title=f"Ticket for Report #{rid}",
        description=(
            f"**Reporter:** {reporter.mention}\n"
            f"**Subject:** {subject}\n"
            f"**Type:** {rtype}\n"
            f"**Reported from:** {src_text}\n\n"
            f"Use the **Resolve** button below when this is finished."
        ),
    )

    # Include the actual report details
    if rtype == "TV":
        ch_name = (payload.get("channel_name") or "Unknown").strip()
        ch_cat = (payload.get("channel_category") or "Unknown").strip()
        issue = (payload.get("issue") or "—").strip()

        embed.add_field(name="Channel", value=ch_name or "Unknown", inline=True)
        embed.add_field(name="Category", value=ch_cat or "Unknown", inline=True)
        embed.add_field(name="Issue", value=issue[:1024] if issue else "—", inline=False)

    elif rtype == "VOD":
        title = (payload.get("title") or "Unknown").strip()
        quality = (payload.get("quality") or "Unknown").strip()
        issue = (payload.get("issue") or "—").strip()
        ref = (payload.get("reference_link") or "").strip()

        embed.add_field(name="Title", value=title or "Unknown", inline=False)
        embed.add_field(name="Quality", value=quality or "Unknown", inline=True)

        if ref:
            label = _nice_ref_label(ref)
            embed.add_field(name="Reference", value=f"[{label}]({ref})", inline=True)

        embed.add_field(name="Issue", value=issue[:1024] if issue else "—", inline=False)

    else:
        # Fallback: dump whatever payload keys exist (lightly)
        if isinstance(payload, dict) and payload:
            lines = []
            for k, v in payload.items():
                if v is None:
                    continue
                s = str(v).strip()
                if not s:
                    continue
                lines.append(f"**{k}:** {s}")
            if lines:
                embed.add_field(name="Details", value="\n".join(lines)[:1024], inline=False)

    return embed


class TicketResolveView(discord.ui.View):
    """
    View used inside ticket channels. Single Resolve button:
    - Marks report Resolved
    - Updates staff report message embed + disables buttons
    - Deletes the ticket channel
    """

    def __init__(
        self,
        db: ReportDB,
        staff_channel_id: int,
        support_channel_id: int,
        public_updates: bool,
        staff_role_id: int,
    ):
        super().__init__(timeout=None)
        self.db = db
        self.staff_channel_id = int(staff_channel_id or 0)
        self.support_channel_id = int(support_channel_id or 0)
        self.public_updates = bool(public_updates)
        self.staff_role_id = int(staff_role_id or 0)

    def _is_staff(self, interaction: discord.Interaction) -> bool:
        if not self.staff_role_id:
            return True
        if not isinstance(interaction.user, discord.Member):
            return False
        return any(r.id == self.staff_role_id for r in interaction.user.roles)

    def _extract_report_id(self, channel: discord.abc.GuildChannel) -> int | None:
        topic = getattr(channel, "topic", "") or ""
        if "report_id=" not in topic:
            return None
        try:
            return int(topic.split("report_id=", 1)[1].split()[0].strip())
        except Exception:
            return None

    @discord.ui.button(label="Resolve", style=discord.ButtonStyle.success, custom_id="ticket:resolve")
    async def resolve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not interaction.channel:
            return await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)

        if not self._is_staff(interaction):
            return await interaction.response.send_message("❌ Staff only.", ephemeral=True)

        report_id = self._extract_report_id(interaction.channel)
        if not report_id:
            return await interaction.response.send_message("❌ Couldn’t determine report ID for this ticket.", ephemeral=True)

        report = self.db.get_report_by_id(report_id)
        if not report:
            return await interaction.response.send_message("❌ Report not found.", ephemeral=True)

        # Mark resolved in DB
        self.db.update_status(report_id, "Resolved")

        # Try update staff message embed + disable buttons
        if self.staff_channel_id and report.get("staff_message_id"):
            try:
                staff_channel = interaction.guild.get_channel(self.staff_channel_id)
                if isinstance(staff_channel, discord.TextChannel):
                    staff_msg = await staff_channel.fetch_message(int(report["staff_message_id"]))

                    reporter = await interaction.client.fetch_user(int(report["reporter_id"]))
                    source = interaction.guild.get_channel(int(report["source_channel_id"])) or staff_channel

                    ticket_id = None
                    try:
                        ticket_id = self.db.get_ticket_channel_id(report_id)
                    except Exception:
                        ticket_id = None

                    embed = build_staff_embed(
                        report_id,
                        report["report_type"],
                        reporter,
                        source,
                        report["payload"],
                        "Resolved",
                        ticket_channel_id=ticket_id,
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

        # Notify reporter (DM best-effort)
        try:
            reporter = await interaction.client.fetch_user(int(report["reporter_id"]))
            subj = report_subject(report["report_type"], report["payload"])
            await try_dm(reporter, f"✅ Update on your report #{report_id} ({subj}): **Resolved**.")
        except Exception:
            pass

        # Clear ticket reference
        try:
            self.db.set_ticket_channel_id(report_id, None)
        except Exception:
            pass

        await interaction.response.send_message("✅ Resolved. Closing ticket…", ephemeral=True)

        # Delete the ticket channel
        try:
            await interaction.channel.delete(reason=f"Resolved ticket for report #{report_id}")
        except discord.Forbidden:
            # If cannot delete, at least rename
            try:
                await interaction.channel.edit(name=f"closed-report-{report_id}")
            except Exception:
                pass


class ReportActionView(discord.ui.View):
    """
    Staff report message actions:

    - Resolved
    - Open ticket

    Open ticket:
      - creates a private channel (under TICKETS_CATEGORY_ID if possible)
      - pings ONLY the reporter
      - posts a Resolve button inside the ticket
      - updates staff report status to "Ticket Open"
      - disables Open ticket button (Resolved stays available)

    NOTE:
      - Resolving from the staff channel does NOT post a public update (DM only).
    """

    def __init__(
        self,
        db: ReportDB,
        staff_channel_id: int,
        support_channel_id: int,
        public_updates: bool,
        staff_role_id: int,
    ):
        super().__init__(timeout=None)
        self.db = db
        self.staff_channel_id = int(staff_channel_id or 0)
        self.support_channel_id = int(support_channel_id or 0)
        self.public_updates = bool(public_updates)
        self.staff_role_id = int(staff_role_id or 0)

    def disable_all(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

    def _is_staff(self, interaction: discord.Interaction) -> bool:
        if not self.staff_role_id:
            return True
        if not isinstance(interaction.user, discord.Member):
            return False
        return any(r.id == self.staff_role_id for r in interaction.user.roles)

    async def _ensure_staff_channel(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not interaction.channel:
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return False

        if self.staff_channel_id and interaction.channel.id != self.staff_channel_id:
            await interaction.response.send_message("❌ Use this in the staff reports channel.", ephemeral=True)
            return False

        if not self._is_staff(interaction):
            await interaction.response.send_message("❌ Staff only.", ephemeral=True)
            return False

        return True

    @discord.ui.button(label="Resolved", style=discord.ButtonStyle.success, custom_id="report:resolved")
    async def resolved(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._ensure_staff_channel(interaction):
            return

        if not interaction.message:
            return await interaction.response.send_message("❌ Couldn’t read the report message.", ephemeral=True)

        report = self.db.get_by_staff_message_id(interaction.message.id)
        if not report:
            return await interaction.response.send_message("❌ Report not found.", ephemeral=True)

        self.db.update_status(report["id"], "Resolved")

        reporter = await interaction.client.fetch_user(int(report["reporter_id"]))
        source = interaction.guild.get_channel(int(report["source_channel_id"])) or interaction.channel
        subject = report_subject(report["report_type"], report["payload"])

        ticket_id = None
        try:
            ticket_id = self.db.get_ticket_channel_id(report["id"])
        except Exception:
            ticket_id = None

        embed = build_staff_embed(
            report["id"],
            report["report_type"],
            reporter,
            source,
            report["payload"],
            "Resolved",
            ticket_channel_id=ticket_id,
        )

        # Disable everything once resolved
        self.disable_all()
        await interaction.response.edit_message(embed=embed, view=self)

        # ✅ DM only (no public post)
        await try_dm(reporter, f"✅ Update on your report #{report['id']} ({subject}): **Resolved**.")

        # Clear ticket reference (if any)
        try:
            self.db.set_ticket_channel_id(report["id"], None)
        except Exception:
            pass

    @discord.ui.button(label="Open ticket", style=discord.ButtonStyle.primary, custom_id="report:ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._ensure_staff_channel(interaction):
            return

        if not interaction.message:
            return await interaction.response.send_message("❌ Couldn’t read the report message.", ephemeral=True)

        report = self.db.get_by_staff_message_id(interaction.message.id)
        if not report:
            return await interaction.response.send_message("❌ Report not found.", ephemeral=True)

        if (report.get("status") or "").strip() in CLOSED_STATUSES:
            return await interaction.response.send_message("⚠️ This report is already closed.", ephemeral=True)

        guild = interaction.guild
        reporter = await interaction.client.fetch_user(int(report["reporter_id"]))

        # Ticket already exists?
        existing_id = self.db.get_ticket_channel_id(report["id"])
        if existing_id:
            ch = guild.get_channel(int(existing_id))
            if ch:
                return await interaction.response.send_message(f"ℹ️ Ticket already exists: {ch.mention}", ephemeral=True)
            self.db.set_ticket_channel_id(report["id"], None)

        me = guild.me
        if not me:
            return await interaction.response.send_message("❌ Couldn’t read my permissions.", ephemeral=True)

        if not me.guild_permissions.manage_channels:
            return await interaction.response.send_message(
                "❌ I don’t have permission to create channels or set permissions.",
                ephemeral=True,
            )

        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            reporter: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True),
        }
        if self.staff_role_id:
            role = guild.get_role(self.staff_role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        # Put tickets in the category (if the bot can see it)
        category = guild.get_channel(TICKETS_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            category = None

        channel_name = f"report-{report['id']}"
        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket for report #{report['id']} | report_id={report['id']}",
                reason=f"Ticket opened for report #{report['id']}",
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ I don’t have permission to create channels or set permissions.",
                ephemeral=True,
            )
        except Exception as e:
            return await interaction.response.send_message(f"❌ Failed to create ticket channel: {e!r}", ephemeral=True)

        self.db.set_ticket_channel_id(report["id"], ticket_channel.id)

        # Ticket top message: ping ONLY reporter + detailed embed + Resolve button
        summary = _build_ticket_embed(report=report, reporter=reporter, guild=guild)

        resolve_view = TicketResolveView(
            db=self.db,
            staff_channel_id=self.staff_channel_id,
            support_channel_id=self.support_channel_id,
            public_updates=self.public_updates,
            staff_role_id=self.staff_role_id,
        )

        await ticket_channel.send(content=reporter.mention, embed=summary, view=resolve_view)

        # Update staff message status to Ticket Open
        self.db.update_status(report["id"], "Ticket Open")

        source = guild.get_channel(int(report["source_channel_id"])) or interaction.channel

        embed = build_staff_embed(
            report["id"],
            report["report_type"],
            reporter,
            source,
            report["payload"],
            "Ticket Open",
            ticket_channel_id=ticket_channel.id,
        )

        # Disable Open ticket only; keep Resolved active
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.custom_id == "report:ticket":
                child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(f"✅ Ticket created: {ticket_channel.mention}", ephemeral=True)
