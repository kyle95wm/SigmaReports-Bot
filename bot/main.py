import discord
from discord.ext import commands

from bot.config import load_config
from bot.db import ReportDB
from bot.views import ReportActionView


class ReportsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

        self.cfg = load_config()
        self.db = ReportDB(self.cfg.db_path)

    async def setup_hook(self):
        self.add_view(
            ReportActionView(
                self.db,
                self.cfg.staff_channel_id,
                self.cfg.support_channel_id,
                self.cfg.public_updates,
            )
        )
        await self.load_extension("bot.cogs.reports")
        await self.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if (
            message.guild
            and message.channel
            and message.channel.id in set(self.cfg.reports_lockdown_channel_ids)
        ):
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound):
                return

            try:
                await message.channel.send(
                    f"{message.author.mention} please use `/report-tv` or `/report-vod` to submit a report."
                )
            except discord.Forbidden:
                pass


def main():
    bot = ReportsBot()
    bot.run(bot.cfg.token)


if __name__ == "__main__":
    main()
