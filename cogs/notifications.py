"""Background polling that announces Jellyfin additions and VRMS service health changes."""

import logging

import discord
from discord.ext import commands, tasks

from config import settings
from core.embed import make_embed
from services import vrms
from services.jellyfin import JellyfinClient, JellyfinError

logger = logging.getLogger("VeryRareBot")

NEW_MEDIA_COLOR = discord.Color.purple()
OUTAGE_COLOR = discord.Color.red()
RECOVERY_COLOR = discord.Color.green()


class Notifications(commands.Cog):
    """Polls Jellyfin and VRMS on a timer and posts changes to configured channels."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._seen_jellyfin_ids: set[str] | None = None
        self._last_vrms_state: str | None = None

        if settings.JELLYFIN_NOTIFY_CHANNEL_ID:
            self.jellyfin_watch.change_interval(seconds=max(settings.JELLYFIN_POLL_SECONDS, 30))
            self.jellyfin_watch.start()

        if settings.VRMS_NOTIFY_CHANNEL_ID:
            self.vrms_watch.change_interval(seconds=max(settings.VRMS_POLL_SECONDS, 15))
            self.vrms_watch.start()

    async def cog_unload(self) -> None:
        self.jellyfin_watch.cancel()
        self.vrms_watch.cancel()

    @tasks.loop(seconds=300)
    async def jellyfin_watch(self):
        channel = self.bot.get_channel(settings.JELLYFIN_NOTIFY_CHANNEL_ID)
        if channel is None:
            return

        try:
            client = JellyfinClient.from_settings()
            items = await client.recently_added(limit=10)
        except JellyfinError as exc:
            logger.debug("Jellyfin notification poll skipped: %s", exc)
            return

        current_ids = {item["Id"] for item in items if item.get("Id")}

        if self._seen_jellyfin_ids is None:
            # First poll after startup: record the baseline without announcing it.
            self._seen_jellyfin_ids = current_ids
            return

        new_ids = current_ids - self._seen_jellyfin_ids
        self._seen_jellyfin_ids = current_ids

        for item in items:
            if item.get("Id") not in new_ids:
                continue
            embed = make_embed("New on Jellyfin", item.get("Name", "Unknown title"), color=NEW_MEDIA_COLOR)
            if item.get("ProductionYear"):
                embed.add_field(name="Year", value=str(item["ProductionYear"]), inline=True)
            if item.get("Type"):
                embed.add_field(name="Type", value=item["Type"], inline=True)
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                logger.warning("Failed to post a Jellyfin notification.")

    @jellyfin_watch.before_loop
    async def before_jellyfin_watch(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=60)
    async def vrms_watch(self):
        channel = self.bot.get_channel(settings.VRMS_NOTIFY_CHANNEL_ID)
        if channel is None or not settings.VRMS_SERVICE_NAME:
            return

        try:
            state = await vrms.is_active()
        except vrms.VRMSError as exc:
            logger.debug("VRMS notification poll skipped: %s", exc)
            return

        previous_state = self._last_vrms_state
        self._last_vrms_state = state

        if previous_state is None or previous_state == state:
            return

        if state == "active":
            embed = make_embed(
                "VRMS Service Recovered",
                f"**{settings.VRMS_SERVICE_NAME}** is now active.",
                color=RECOVERY_COLOR,
            )
        else:
            embed = make_embed(
                "VRMS Service Outage",
                f"**{settings.VRMS_SERVICE_NAME}** is now **{state}**.",
                color=OUTAGE_COLOR,
            )

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            logger.warning("Failed to post a VRMS notification.")

    @vrms_watch.before_loop
    async def before_vrms_watch(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Notifications(bot))
