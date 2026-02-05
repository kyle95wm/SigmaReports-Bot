import asyncio
from datetime import datetime, timedelta, timezone
import random

import discord
from discord.ext import commands

from bot.config import load_config
from bot.db import ReportDB
from bot.views import ReportActionView


# Edit this list whenever you want. Keep them short so they fit nicely.
WATCHING_STATUSES = [
    "IPTV playlists",
    "live channel guides (EPG)",
    "buffering complaints",
    "sports blackouts (again)",
    "the stream health dashboard",
    "channel logos load",
    "VOD playback retries",
    "4K HDR test clips",
    "audio sync checks",
    "subtitle reports",
    "Sky Sports News",
    "BBC One",
    "CNN",
    "ESPN",
    "HBO",
    "Discovery Channel",
    "National Geographic",
    "Cartoon Network",
    "Nickelodeon",
    "The Office",
    "Breaking Bad",
    "Stranger Things",
    "Game of Thrones",
    "The Mandalorian",
    "The Last of Us",
    "The Boys",
    "Inception",
    "Interstellar",
    "The Dark Knight",
    "Avengers: Endgame",
    "Spider-Man: Into the Spider-Verse",
]


def seconds_until_next_hour() -> float:
    now = datetime.now(timezone.utc)
    next_hour = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    return (next_hour - now).total_seconds()


class ReportsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

        self.cfg = load_config()
        self.db = ReportDB(self.cfg.db_path)

        self._presence_task: asyncio.Task | None = None

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

        # Start rotating presence
        self._presence_task = asyncio.create_task(self._presence_rotator())

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")

    async def _set_random_presence(self):
        text = random.choice(WATCHING_STATUSES)
        activity = discord.Activity(type=discord.ActivityType.watching, name=text)
        await self.change_presence(activity=activity)

    async def _presence_rotator(self):
        # Set immediately on startup
        try:
            await self.wait_until_ready()
            await self._set_random_presence()
        except Exception:
            # don’t crash the bot if presence update fails
            return

        # Then update every hour, on the hour (UTC)
        while not self.is_closed():
            try:
                await asyncio.sleep(seconds_until_next_hour())
                await self._set_random_presence()
            except asyncio.CancelledError:
                return
            except Exception:
                # keep looping even if Discord errors temporarily
                await asyncio.sleep(60)

    async def on_message(self, message: discord.Message):
        # Keep your existing message-lockdown behavior
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
