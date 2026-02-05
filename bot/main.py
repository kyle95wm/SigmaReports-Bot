import asyncio
from datetime import datetime, timedelta, timezone
import random

import discord
from discord.ext import commands

from bot.config import load_config
from bot.db import ReportDB
from bot.views import ReportActionView
from bot.tmdb import fetch_tmdb_titles


LOCAL_CHANNELS = [
    "BBC One",
    "BBC Two",
    "ITV1",
    "Channel 4",
    "Channel 5",
    "Sky Sports Main Event",
    "Sky Sports News",
    "TNT Sports 1",
    "ESPN",
    "FOX Sports",
    "CNN",
    "Discovery Channel",
    "National Geographic",
    "Cartoon Network",
    "Nickelodeon",
    "HBO",
]

IPTV_FLAVOR = [
    "IPTV playlists",
    "live channel guides (EPG)",
    "buffering complaints",
    "stream uptime",
    "audio sync checks",
    "subtitle reports",
    "4K test clips",
    "VOD playback retries",
    "channel logo packs",
]


def seconds_until_next_interval(minutes: int = 5) -> float:
    """
    Sleep until the next clean interval boundary.
    For minutes=5 → :00, :05, :10, :15, :20, ...
    """
    now = datetime.now(timezone.utc)

    rounded = now.replace(second=0, microsecond=0) - timedelta(
        minutes=(now.minute % minutes)
    )
    next_tick = rounded + timedelta(minutes=minutes)

    return (next_tick - now).total_seconds()


class ReportsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

        self.cfg = load_config()
        self.db = ReportDB(self.cfg.db_path)

        self._tmdb_cache: list[str] = []
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

        self._presence_task = asyncio.create_task(self._presence_rotator())

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")

    def _build_status_pool(self) -> list[str]:
        pool: list[str] = []
        pool.extend(IPTV_FLAVOR)
        pool.extend(LOCAL_CHANNELS)
        pool.extend(self._tmdb_cache)

        # Prevent runaway size
        return pool[:250] if len(pool) > 250 else pool

    async def _refresh_tmdb_cache(self):
        token = self.cfg.tmdb_bearer_token
        if not token:
            self._tmdb_cache = []
            return

        try:
            titles = await asyncio.to_thread(fetch_tmdb_titles, token, 40)
            cleaned = [t for t in titles if 1 <= len(t) <= 48]
            self._tmdb_cache = cleaned[:120]
        except Exception:
            # Keep existing cache if TMDB fails
            pass

    async def _set_random_presence(self):
        pool = self._build_status_pool()
        text = random.choice(pool) if pool else "reports"
        activity = discord.Activity(type=discord.ActivityType.watching, name=text)
        await self.change_presence(activity=activity)

    async def _presence_rotator(self):
        await self.wait_until_ready()

        # Initial refresh + immediate presence
        await self._refresh_tmdb_cache()
        try:
            await self._set_random_presence()
        except Exception:
            pass

        # Refresh TMDB every 6 hours
        tmdb_refresh_interval = 6 * 60 * 60
        next_tmdb_refresh = asyncio.get_event_loop().time() + tmdb_refresh_interval

        while not self.is_closed():
            try:
                await asyncio.sleep(seconds_until_next_interval(5))

                if asyncio.get_event_loop().time() >= next_tmdb_refresh:
                    await self._refresh_tmdb_cache()
                    next_tmdb_refresh = asyncio.get_event_loop().time() + tmdb_refresh_interval

                await self._set_random_presence()
            except asyncio.CancelledError:
                return
            except Exception:
                await asyncio.sleep(60)

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
