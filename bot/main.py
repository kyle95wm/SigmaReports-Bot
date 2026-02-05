import asyncio
import os
import random
from typing import Optional

import discord
from discord.ext import commands

from bot.config import load_config
from bot.db import ReportDB
from bot.views import ReportActionView

try:
    import aiohttp
except Exception:
    aiohttp = None  # type: ignore


# --- Presence pools (tweak these any time) ---

IPTV_FLAVOR = [
    "IPTV playlists",
    "Live TV",
    "EPG updates",
    "Channel scans",
    "Buffering fixes",
    "Stream health",
    "CDN routes",
    "Catch-up TV",
]

LOCAL_CHANNELS = [
    "BBC One",
    "BBC Two",
    "ITV 1",
    "Channel 4",
    "Sky Sports News",
    "Sky Sports Main Event",
    "TNT Sports 1",
    "Eurosport 1",
    "Discovery",
    "National Geographic",
]


class SigmaReportsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        # message_content intent is NOT required for slash commands
        super().__init__(command_prefix="!", intents=intents)

        self.cfg = load_config()
        self.db = ReportDB(self.cfg.db_path)

        self._tmdb_cache: list[str] = []
        self._presence_task: Optional[asyncio.Task] = None

    async def setup_hook(self) -> None:
        # Persistent view for staff buttons
        self.add_view(
            ReportActionView(
                self.db,
                self.cfg.staff_channel_id,
                self.cfg.support_channel_id,
                self.cfg.public_updates,
            )
        )

        guild_id = 1457559352717086917
        guild = discord.Object(id=guild_id)

        # ---- Optional one-time cleanup for duplicate commands ----
        # If you've ever synced globally and then guild-synced, Discord can show duplicates.
        # Set CLEAN_DUPLICATE_COMMANDS=1 in .env, deploy once, then set it back to 0.
        if os.getenv("CLEAN_DUPLICATE_COMMANDS", "0").strip() == "1":
            print("CLEAN_DUPLICATE_COMMANDS=1 -> clearing global + guild commands...")

            # Clear ALL global commands currently registered (in Discord)
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            print("Cleared global commands.")

            # Clear ALL guild commands currently registered for this guild
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"Cleared guild commands for {guild_id}.")

        # Load cogs (registers slash commands into the tree)
        await self.load_extension("bot.cogs.reports")

        # Helpful debug line
        print("Tree before sync:", [c.name for c in self.tree.get_commands()])

        # ✅ Ensure guild commands match our current tree (helps when Discord gets 'stuck')
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        print(f"Synced {len(synced)} commands to guild {guild_id}")

        # Start rotating presence
        self._presence_task = asyncio.create_task(self._presence_rotator())

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")

    # ---------------- Presence rotation (5 min) ----------------

    async def _presence_rotator(self):
        # Refresh TMDB cache on startup
        await self._refresh_tmdb_cache()

        # Then run every 5 minutes; refresh TMDB every 6 hours
        ticks = 0
        while not self.is_closed():
            try:
                await self._set_random_presence()
            except Exception:
                pass

            await asyncio.sleep(300)  # 5 minutes
            ticks += 1

            # every 6 hours (72 * 5min)
            if ticks % 72 == 0:
                try:
                    await self._refresh_tmdb_cache()
                except Exception:
                    pass

    def _build_status_pool(self) -> list[str]:
        pool: list[str] = []
        pool.extend(IPTV_FLAVOR)
        pool.extend(LOCAL_CHANNELS)
        pool.extend(self._tmdb_cache)
        return [p for p in pool if p]

    async def _set_random_presence(self):
        pool = self._build_status_pool()
        if not pool:
            return

        choice = random.choice(pool)
        activity = discord.Activity(type=discord.ActivityType.watching, name=choice)
        await self.change_presence(activity=activity)

    async def _refresh_tmdb_cache(self):
        token = getattr(self.cfg, "tmdb_bearer_token", "") or ""
        if not token or aiohttp is None:
            self._tmdb_cache = []
            return

        headers = {
            "Authorization": f"Bearer {token}",
            "accept": "application/json",
        }

        urls = [
            "https://api.themoviedb.org/3/trending/movie/day",
            "https://api.themoviedb.org/3/trending/tv/day",
        ]

        titles: list[str] = []
        async with aiohttp.ClientSession(headers=headers) as session:
            for url in urls:
                try:
                    async with session.get(url, timeout=15) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        for item in data.get("results", [])[:25]:
                            name = item.get("title") or item.get("name")
                            if name:
                                titles.append(name)
                except Exception:
                    continue

        # Dedup + cap size
        deduped: list[str] = []
        seen = set()
        for t in titles:
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(t)

        self._tmdb_cache = deduped[:50]


def main():
    bot = SigmaReportsBot()
    bot.run(bot.cfg.token)


if __name__ == "__main__":
    main()
