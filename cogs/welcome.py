"""Posts a custom welcome card for new members, replacing ProBot's welcome message."""

import logging

import discord
from discord.ext import commands

from config import settings
from services.welcome_card import generate_welcome_card

logger = logging.getLogger("VeryRareBot")


class Welcome(commands.Cog):
    """Custom join-welcome card and member-count announcement."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = self.bot.get_channel(settings.WELCOME_CHANNEL_ID) if settings.WELCOME_CHANNEL_ID else None
        if channel is None:
            return

        announcement = f"Welcome to {member.guild.name} we are now at {member.guild.member_count} Members!!!"

        try:
            file = await generate_welcome_card(member)
        except Exception:
            logger.exception("Failed to generate a welcome card for %s; falling back to text only.", member)
            try:
                await channel.send(content=f"{member.mention} {announcement}")
            except discord.HTTPException:
                logger.warning("Failed to send the fallback welcome message.")
            return

        # The mention stays in plain content so it actually notifies the member (mentions
        # inside embeds render as clickable links but don't trigger a ping); the announcement
        # line goes in the embed footer so it renders under the picture instead of above it.
        embed = discord.Embed()
        embed.set_image(url="attachment://welcome.png")
        embed.set_footer(text=announcement)

        try:
            await channel.send(content=member.mention, embed=embed, file=file)
        except discord.HTTPException:
            logger.warning("Failed to send the welcome card.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
