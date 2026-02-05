import discord
from bot.db import ReportDB
from bot.utils import build_staff_embed
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
        )

        ping_text = ""
        if self.db.get_report_pings_enabled():
            ping_text = build_staff_ping(self.cfg.staff_ping_user_ids)

        msg = await staff_channel.send(content=ping_text, embed=embed, view=view)
        self.db.set_staff_message_id(report_id, msg.id)

        await interaction.response.send_message(
            f"{interaction.user.mention} submitted TV report **#{report_id}** for **{payload['channel_name']}**."
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
        )

        ping_text = ""
        if self.db.get_report_pings_enabled():
            ping_text = build_staff_ping(self.cfg.staff_ping_user_ids)

        msg = await staff_channel.send(content=ping_text, embed=embed, view=view)
        self.db.set_staff_message_id(report_id, msg.id)

        await interaction.response.send_message(
            f"{interaction.user.mention} submitted VOD report **#{report_id}** for **{payload['title']}** ({q})."
        )
