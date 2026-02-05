import discord


class TVReportModal(discord.ui.Modal, title="Report a TV Channel Issue"):
    channel_name = discord.ui.TextInput(
        label="Channel name",
        placeholder="e.g. BBC One",
        max_length=100,
    )

    channel_category = discord.ui.TextInput(
        label="Channel category",
        placeholder="e.g. Entertainment, Sports, News",
        max_length=100,
    )

    issue = discord.ui.TextInput(
        label="What is the issue?",
        style=discord.TextStyle.paragraph,
        placeholder="Describe the problem you're experiencing",
        max_length=1000,
    )

    def __init__(self, db, cfg):
        super().__init__()
        self.db = db
        self.cfg = cfg

    async def on_submit(self, interaction: discord.Interaction):
        report_id = self.db.create_report(
            report_type="tv",
            reporter_id=interaction.user.id,
            source_channel_id=interaction.channel.id,
            payload={
                "channel_name": str(self.channel_name),
                "channel_category": str(self.channel_category),
                "issue": str(self.issue),
            },
        )

        await interaction.response.send_message(
            f"✅ Your TV report **#{report_id}** has been submitted.",
        )


class VODReportModal(discord.ui.Modal, title="Report a VOD Issue"):
    title_field = discord.ui.TextInput(
        label="Movie or TV show title",
        placeholder="e.g. Breaking Bad S02E05 or Inception",
        max_length=150,
    )

    thetvdb_link = discord.ui.TextInput(
        label="TheTVDB link",
        placeholder="https://thetvdb.com/series/...",
        max_length=300,
    )

    quality = discord.ui.TextInput(
        label="Quality affected",
        placeholder="FHD or 4K",
        max_length=10,
    )

    issue = discord.ui.TextInput(
        label="What is the issue?",
        style=discord.TextStyle.paragraph,
        placeholder="Describe the problem you're experiencing",
        max_length=1000,
    )

    def __init__(self, db, cfg):
        super().__init__()
        self.db = db
        self.cfg = cfg

    async def on_submit(self, interaction: discord.Interaction):
        report_id = self.db.create_report(
            report_type="vod",
            reporter_id=interaction.user.id,
            source_channel_id=interaction.channel.id,
            payload={
                "title": str(self.title_field),
                "thetvdb_link": str(self.thetvdb_link),
                "quality": str(self.quality),
                "issue": str(self.issue),
            },
        )

        await interaction.response.send_message(
            f"✅ Your VOD report **#{report_id}** has been submitted.",
        )
