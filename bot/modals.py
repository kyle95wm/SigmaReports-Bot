import discord

from bot.views import ReportActionView


def _safe_int(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    return int(value) if value.isdigit() else None


def _build_staff_embed(
    report_id: int,
    report_type: str,
    reporter: discord.abc.User,
    source_channel: discord.abc.GuildChannel | discord.abc.PrivateChannel | None,
    payload: dict,
    status: str = "Open",
) -> discord.Embed:
    """
    Local embed builder (kept simple + stable).
    Your ReportActionView may rebuild embeds elsewhere — but this is fine for initial post.
    """
    # Subject shown in title
    if report_type == "VOD":
        subject = payload.get("title", "Unknown title")
    else:
        subject = payload.get("channel_name", "Unknown channel")

    embed = discord.Embed(
        title=f"Report #{report_id} — {report_type} — {subject}",
        description="",
    )

    embed.add_field(name="Status", value=status, inline=False)
    embed.add_field(name="Reporter", value=f"{reporter.mention} ({reporter.id})", inline=False)

    if isinstance(source_channel, discord.abc.GuildChannel):
        embed.add_field(name="Reported from", value=source_channel.mention, inline=False)

    if report_type == "TV":
        embed.add_field(name="Channel", value=payload.get("channel_name", "—"), inline=False)
        embed.add_field(name="Category", value=payload.get("channel_category", "—"), inline=False)
        embed.add_field(name="Issue", value=payload.get("issue", "—"), inline=False)

    if report_type == "VOD":
        embed.add_field(name="Title", value=payload.get("title", "—"), inline=False)
        embed.add_field(name="Quality", value=payload.get("quality", "—"), inline=False)

        ref_link = payload.get("reference_link", "")
        if ref_link:
            # Nicer clickable label:
            label = "Reference link"
            if "thetvdb" in ref_link.lower():
                label = "TheTVDB"
            elif "themoviedb" in ref_link.lower() or "tmdb" in ref_link.lower():
                label = "TMDB"
            elif "imdb" in ref_link.lower():
                label = "IMDb"

            embed.add_field(name="Reference", value=f"[{label}]({ref_link})", inline=False)

        embed.add_field(name="Issue", value=payload.get("issue", "—"), inline=False)

    # Button explainer (you asked for this earlier)
    embed.add_field(
        name="Staff actions",
        value=(
            "✅ **Fixed** — Issue confirmed and resolved (closes the report)\n"
            "⚠️ **Can't replicate** — Issue could not be reproduced (closes the report)\n"
            "📝 **More info required** — Ask the user to submit a new report with more details\n"
            "💬 **Send follow-up** — Send one-way status updates **without closing the report**"
        ),
        inline=False,
    )
    embed.set_footer(text="Follow-ups are one-way updates to the reporter. Only Fixed or Can't replicate closes the report.")
    return embed


class TVReportModal(discord.ui.Modal, title="Report TV Issue"):
    channel_name = discord.ui.TextInput(
        label="Channel name",
        placeholder="e.g. Sky Sports Main Event",
        required=True,
        max_length=80,
    )
    channel_category = discord.ui.TextInput(
        label="Channel category",
        placeholder="e.g. Sports / Movies / Kids / News",
        required=True,
        max_length=80,
    )
    issue = discord.ui.TextInput(
        label="What's the issue?",
        placeholder="Describe what’s happening",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=900,
    )

    def __init__(self, db, cfg):
        super().__init__()
        self.db = db
        self.cfg = cfg

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or not interaction.channel:
            return await interaction.response.send_message("This command must be used in a server.")

        staff_ch = interaction.guild.get_channel(self.cfg.staff_channel_id)
        if not staff_ch:
            return await interaction.response.send_message("Staff channel not found. Please contact an admin.")

        payload = {
            "channel_name": self.channel_name.value.strip(),
            "channel_category": self.channel_category.value.strip(),
            "issue": self.issue.value.strip(),
        }

        report_id = self.db.create_report(
            report_type="TV",
            reporter_id=interaction.user.id,
            guild_id=interaction.guild.id,
            source_channel_id=interaction.channel.id,
            payload=payload,
        )

        view = ReportActionView(
            self.db,
            self.cfg.staff_channel_id,
            self.cfg.support_channel_id,
            self.cfg.public_updates,
            cfg=self.cfg,
        )

        embed = _build_staff_embed(
            report_id=report_id,
            report_type="TV",
            reporter=interaction.user,
            source_channel=interaction.channel,
            payload=payload,
            status="Open",
        )

        # Optional staff pings (respects /reportpings toggle)
        content = None
        try:
            if self.db.get_report_pings_enabled() and getattr(self.cfg, "staff_ping_user_ids", None):
                pings = " ".join(f"<@{uid}>" for uid in self.cfg.staff_ping_user_ids)
                content = f"{pings} New TV report received."
        except Exception:
            pass

        staff_msg = await staff_ch.send(content=content, embed=embed, view=view)

        # ✅ FIX: link the staff message back to the report so buttons can find it
        self.db.set_staff_message_id(report_id, staff_msg.id)

        # User-facing ack (non-ephemeral)
        await interaction.response.send_message(
            f"✅ {interaction.user.mention} your TV report **#{report_id}** (Channel: **{payload['channel_name']}**) was submitted."
        )


class VODReportModal(discord.ui.Modal, title="Report VOD Issue"):
    title_field = discord.ui.TextInput(
        label="Title (movie or show + S/E)",
        placeholder="e.g. The Office S02E03 or Interstellar",
        required=True,
        max_length=120,
    )
    reference_link = discord.ui.TextInput(
        label="Reference link (TheTVDB / TMDB / IMDb)",
        placeholder="Paste a link that matches the exact title",
        required=True,
        max_length=250,
    )
    quality = discord.ui.TextInput(
        label="Quality (FHD or 4K)",
        placeholder="FHD or 4K",
        required=True,
        max_length=10,
    )
    issue = discord.ui.TextInput(
        label="What's the issue?",
        placeholder="Describe what’s happening",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=900,
    )

    def __init__(self, db, cfg):
        super().__init__()
        self.db = db
        self.cfg = cfg

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or not interaction.channel:
            return await interaction.response.send_message("This command must be used in a server.")

        staff_ch = interaction.guild.get_channel(self.cfg.staff_channel_id)
        if not staff_ch:
            return await interaction.response.send_message("Staff channel not found. Please contact an admin.")

        quality = self.quality.value.strip().upper()
        if quality not in ("FHD", "4K"):
            quality = self.quality.value.strip()  # don’t hard-fail; just store what they typed

        payload = {
            "title": self.title_field.value.strip(),
            "reference_link": self.reference_link.value.strip(),
            "quality": quality,
            "issue": self.issue.value.strip(),
        }

        report_id = self.db.create_report(
            report_type="VOD",
            reporter_id=interaction.user.id,
            guild_id=interaction.guild.id,
            source_channel_id=interaction.channel.id,
            payload=payload,
        )

        view = ReportActionView(
            self.db,
            self.cfg.staff_channel_id,
            self.cfg.support_channel_id,
            self.cfg.public_updates,
            cfg=self.cfg,
        )

        embed = _build_staff_embed(
            report_id=report_id,
            report_type="VOD",
            reporter=interaction.user,
            source_channel=interaction.channel,
            payload=payload,
            status="Open",
        )

        # Optional staff pings (respects /reportpings toggle)
        content = None
        try:
            if self.db.get_report_pings_enabled() and getattr(self.cfg, "staff_ping_user_ids", None):
                pings = " ".join(f"<@{uid}>" for uid in self.cfg.staff_ping_user_ids)
                content = f"{pings} New VOD report received."
        except Exception:
            pass

        staff_msg = await staff_ch.send(content=content, embed=embed, view=view)

        # ✅ FIX: link the staff message back to the report so buttons can find it
        self.db.set_staff_message_id(report_id, staff_msg.id)

        # User-facing ack (non-ephemeral)
        await interaction.response.send_message(
            f"✅ {interaction.user.mention} your VOD report **#{report_id}** (Title: **{payload['title']}**) was submitted."
        )
