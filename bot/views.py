import discord

from bot.utils import build_staff_embed, report_subject, try_dm


class FollowUpModal(discord.ui.Modal, title="Send follow-up"):
    message = discord.ui.TextInput(
        label="Follow-up message",
        style=discord.TextStyle.paragraph,
        max_length=900,
        required=True,
        placeholder="Type the update you want the reporter to see…",
    )

    def __init__(self, view: "ReportActionView", report: dict):
        super().__init__()
        self.view = view
        self.report = report

    async def on_submit(self, interaction: discord.Interaction):
        if not self.view.is_staff(interaction):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("This must be used in a server.", ephemeral=True)

        reporter_id = self.report["reporter_id"]
        src_ch = guild.get_channel(self.report["source_channel_id"])

        subject = report_subject(self.report["report_type"], self.report["payload"])
        user_msg = f"💬 Update on report **#{self.report['id']}** ({subject}):\n{self.message.value}"

        # DM if possible
        try:
            reporter = await interaction.client.fetch_user(reporter_id)
        except Exception:
            reporter = interaction.client.get_user(reporter_id)

        if reporter:
            await try_dm(reporter, user_msg)

        # Public ping (if enabled)
        if self.view.public_updates and src_ch:
            try:
                await src_ch.send(f"<@{reporter_id}> {user_msg}")
            except discord.Forbidden:
                pass

        await interaction.response.send_message("✅ Follow-up sent (does not close the report).", ephemeral=True)


class BlockUserModal(discord.ui.Modal, title="Block user from reports"):
    duration_minutes = discord.ui.TextInput(
        label="Duration minutes (blank = permanent)",
        required=False,
        max_length=10,
        placeholder="e.g. 60 (leave blank for permanent)",
    )
    reason = discord.ui.TextInput(
        label="Reason (optional)",
        required=False,
        max_length=200,
        placeholder="Spam / troll reports / abuse",
    )

    def __init__(self, view: "ReportActionView", report: dict):
        super().__init__()
        self.view = view
        self.report = report

    async def on_submit(self, interaction: discord.Interaction):
        if not self.view.is_staff(interaction):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("This must be used in a server.", ephemeral=True)

        raw = (self.duration_minutes.value or "").strip()
        dur = None
        if raw:
            if not raw.isdigit():
                return await interaction.response.send_message("Duration must be a number of minutes (or blank).", ephemeral=True)
            dur = int(raw)

        reason = (self.reason.value or "").strip()

        # Apply the block
        self.view.db.block_user(
            guild_id=guild.id,
            user_id=self.report["reporter_id"],
            created_by=interaction.user.id,
            duration_minutes=dur,
            reason=reason,
        )

        # Build appeal message
        support_ch = guild.get_channel(self.view.support_channel_id) if self.view.support_channel_id else None
        support_mention = support_ch.mention if support_ch else "the support channel"

        if dur is None:
            base = f"🚫 You are blocked from using the report system. To appeal, open a ticket in {support_mention}."
        else:
            base = f"🚫 You are temporarily blocked from using the report system. To appeal, open a ticket in {support_mention}."

        if reason:
            base += f"\nReason: {reason}"

        reporter_id = self.report["reporter_id"]
        src_ch = guild.get_channel(self.report["source_channel_id"])

        # DM reporter if possible
        try:
            reporter = await interaction.client.fetch_user(reporter_id)
        except Exception:
            reporter = interaction.client.get_user(reporter_id)

        if reporter:
            await try_dm(reporter, base)

        # Public ping in the source channel (so they see it if DMs closed)
        if src_ch:
            try:
                await src_ch.send(f"<@{reporter_id}> {base}")
            except discord.Forbidden:
                pass

        # Update staff embed to reflect block (best-effort, won’t break if DB lacks method)
        try:
            staff_msg = interaction.message
            updated = self.view._get_report_from_staff_message_id(staff_msg.id)
            if updated:
                embed = build_staff_embed(
                    updated["id"],
                    updated["report_type"],
                    reporter or interaction.user,
                    src_ch or interaction.channel,
                    updated["payload"],
                    updated["status"],
                )
                block_line = "Permanent" if dur is None else f"{dur} minutes"
                extra = f"**Blocked:** {block_line}\n**By:** {interaction.user.mention}"
                if reason:
                    extra += f"\n**Reason:** {reason}"
                embed.add_field(name="🚫 Report access", value=extra, inline=False)

                await staff_msg.edit(embed=embed, view=self.view)
        except Exception:
            pass

        await interaction.response.send_message("✅ Block applied.", ephemeral=True)


class ReportActionView(discord.ui.View):
    def __init__(self, db, staff_channel_id: int, support_channel_id: int, public_updates: bool, cfg=None):
        super().__init__(timeout=None)
        self.db = db
        self.staff_channel_id = staff_channel_id
        self.support_channel_id = support_channel_id
        self.public_updates = public_updates
        self.cfg = cfg  # optional; used for staff role ID if present

    def is_staff(self, interaction: discord.Interaction) -> bool:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member:
            return False

        # Prefer role-based staff gating if cfg.staff_role_id exists
        staff_role_id = getattr(self.cfg, "staff_role_id", 0) if self.cfg else 0
        if staff_role_id:
            return any(r.id == staff_role_id for r in member.roles)

        # Fallback: admin/manage guild
        perms = member.guild_permissions
        return perms.administrator or perms.manage_guild

    def _get_report_from_staff_message_id(self, staff_message_id: int):
        # Supports either db.get_by_staff_message_id or db.get_report_by_staff_message_id if you named it differently
        if hasattr(self.db, "get_by_staff_message_id"):
            return self.db.get_by_staff_message_id(staff_message_id)
        if hasattr(self.db, "get_report_by_staff_message_id"):
            return self.db.get_report_by_staff_message_id(staff_message_id)
        return None

    def _update_status(self, report_id: int, status: str):
        if hasattr(self.db, "update_status"):
            return self.db.update_status(report_id, status)
        if hasattr(self.db, "set_status"):
            return self.db.set_status(report_id, status)
        raise RuntimeError("DB has no update_status/set_status method")

    async def _notify_reporter(self, interaction: discord.Interaction, report: dict, new_status: str):
        guild = interaction.guild
        if not guild:
            return

        reporter_id = report["reporter_id"]
        src_ch = guild.get_channel(report["source_channel_id"])
        support_ch = guild.get_channel(self.support_channel_id) if self.support_channel_id else None
        support_mention = support_ch.mention if support_ch else "the support channel"

        subject = report_subject(report["report_type"], report["payload"])

        if new_status == "Fixed":
            msg = f"✅ Update on your report **#{report['id']}** ({subject}): **Fixed**."
        elif "Can't replicate" in new_status or "Cant replicate" in new_status:
            msg = (
                f"⚠️ Update on your report **#{report['id']}** ({subject}): **We are unable to replicate the issue**.\n"
                f"Please open a ticket in {support_mention} so we can assist further."
            )
        else:
            msg = f"📝 Update on your report **#{report['id']}** ({subject}): **More info required**.\nPlease re-submit your report with more details."

        # DM
        try:
            reporter = await interaction.client.fetch_user(reporter_id)
        except Exception:
            reporter = interaction.client.get_user(reporter_id)

        if reporter:
            await try_dm(reporter, msg)

        # Public ping
        if self.public_updates and src_ch:
            try:
                await src_ch.send(f"<@{reporter_id}> {msg}")
            except discord.Forbidden:
                pass

    async def _refresh_staff_embed(self, interaction: discord.Interaction, report: dict):
        guild = interaction.guild
        src_ch = guild.get_channel(report["source_channel_id"]) if guild else None

        # best effort for reporter object (embed only)
        try:
            reporter = await interaction.client.fetch_user(report["reporter_id"])
        except Exception:
            reporter = interaction.client.get_user(report["reporter_id"]) or interaction.user

        embed = build_staff_embed(
            report["id"],
            report["report_type"],
            reporter,
            src_ch or interaction.channel,
            report["payload"],
            report["status"],
        )
        await interaction.message.edit(embed=embed, view=self)

    # -------- Buttons --------

    @discord.ui.button(label="Fixed", style=discord.ButtonStyle.success, emoji="✅", custom_id="report:fixed")
    async def fixed(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_staff(interaction):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        report = self._get_report_from_staff_message_id(interaction.message.id)
        if not report:
            return await interaction.response.send_message("Could not find report for this message.", ephemeral=True)

        self._update_status(report["id"], "Fixed")
        report["status"] = "Fixed"

        await self._notify_reporter(interaction, report, "Fixed")
        await self._refresh_staff_embed(interaction, report)
        await interaction.response.send_message("✅ Marked as Fixed.", ephemeral=True)

    @discord.ui.button(label="Can't replicate", style=discord.ButtonStyle.secondary, emoji="⚠️", custom_id="report:cantrep")
    async def cantrep(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_staff(interaction):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        report = self._get_report_from_staff_message_id(interaction.message.id)
        if not report:
            return await interaction.response.send_message("Could not find report for this message.", ephemeral=True)

        self._update_status(report["id"], "Can't replicate")
        report["status"] = "Can't replicate"

        await self._notify_reporter(interaction, report, "Can't replicate")
        await self._refresh_staff_embed(interaction, report)
        await interaction.response.send_message("✅ Marked as Can't replicate.", ephemeral=True)

    @discord.ui.button(label="More info required", style=discord.ButtonStyle.primary, emoji="📝", custom_id="report:moreinfo")
    async def moreinfo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_staff(interaction):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        report = self._get_report_from_staff_message_id(interaction.message.id)
        if not report:
            return await interaction.response.send_message("Could not find report for this message.", ephemeral=True)

        self._update_status(report["id"], "More info required")
        report["status"] = "More info required"

        await self._notify_reporter(interaction, report, "More info required")
        await self._refresh_staff_embed(interaction, report)
        await interaction.response.send_message("✅ Requested more info.", ephemeral=True)

    @discord.ui.button(label="Send follow-up", style=discord.ButtonStyle.secondary, emoji="💬", custom_id="report:followup")
    async def followup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_staff(interaction):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        report = self._get_report_from_staff_message_id(interaction.message.id)
        if not report:
            return await interaction.response.send_message("Could not find report for this message.", ephemeral=True)

        await interaction.response.send_modal(FollowUpModal(self, report))

    @discord.ui.button(label="Block user", style=discord.ButtonStyle.danger, emoji="🚫", custom_id="report:blockuser")
    async def blockuser(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_staff(interaction):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        report = self._get_report_from_staff_message_id(interaction.message.id)
        if not report:
            return await interaction.response.send_message("Could not find report for this message.", ephemeral=True)

        await interaction.response.send_modal(BlockUserModal(self, report))
