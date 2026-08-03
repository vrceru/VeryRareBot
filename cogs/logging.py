import logging

import discord
from discord.ext import commands

from config import settings
from core.embed import make_embed

logger = logging.getLogger("VeryRareBot")

LOG_COLOR = discord.Color.dark_grey()
JOIN_COLOR = discord.Color.green()
LEAVE_COLOR = discord.Color.red()


class Logging(commands.Cog):
    """Server activity logging: joins/leaves, role changes, message edits/deletes, voice, and command usage."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _log_channel(self) -> discord.abc.Messageable | None:
        return self.bot.get_channel(settings.LOG_CHANNEL_ID) if settings.LOG_CHANNEL_ID else None

    def _welcome_channel(self) -> discord.abc.Messageable | None:
        return self.bot.get_channel(settings.WELCOME_CHANNEL_ID) if settings.WELCOME_CHANNEL_ID else None

    async def _send_log(self, embed: discord.Embed) -> None:
        channel = self._log_channel()
        if channel is None:
            return
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            logger.warning("Failed to deliver a log embed to the configured log channel.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        logger.info("Member joined: %s (%s) in guild %s", member, member.id, member.guild.id)

        welcome_channel = self._welcome_channel()
        if welcome_channel is not None:
            try:
                await welcome_channel.send(f"Welcome to {member.guild.name}, {member.mention}!")
            except discord.HTTPException:
                logger.warning("Failed to send a welcome message.")

        embed = make_embed("Member Joined", f"{member.mention} ({member})", color=JOIN_COLOR)
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, style="R"), inline=True)
        embed.add_field(name="Member Count", value=str(member.guild.member_count), inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._send_log(embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        logger.info("Member left: %s (%s) in guild %s", member, member.id, member.guild.id)

        embed = make_embed("Member Left", f"{member.mention} ({member})", color=LEAVE_COLOR)
        embed.add_field(name="Member Count", value=str(member.guild.member_count), inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._send_log(embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles == after.roles:
            return

        added = [role for role in after.roles if role not in before.roles]
        removed = [role for role in before.roles if role not in after.roles]
        if not added and not removed:
            return

        logger.info("Roles updated for %s: +%s -%s", after, [r.name for r in added], [r.name for r in removed])

        embed = make_embed("Member Roles Updated", after.mention, color=LOG_COLOR)
        if added:
            embed.add_field(name="Added", value=", ".join(role.mention for role in added), inline=False)
        if removed:
            embed.add_field(name="Removed", value=", ".join(role.mention for role in removed), inline=False)
        await self._send_log(embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        logger.info("Message deleted in #%s by %s", message.channel, message.author)

        embed = make_embed("Message Deleted", None, color=LOG_COLOR)
        embed.add_field(name="Author", value=message.author.mention, inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(name="Content", value=(message.content or "*(no text content)*")[:1024], inline=False)
        await self._send_log(embed)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]):
        if not messages:
            return

        channel = messages[0].channel
        logger.info("%s messages bulk deleted in #%s", len(messages), channel)

        embed = make_embed("Messages Bulk Deleted", f"{len(messages)} messages deleted in {channel.mention}.", color=LOG_COLOR)
        await self._send_log(embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or before.guild is None or before.content == after.content:
            return

        logger.info("Message edited in #%s by %s", before.channel, before.author)

        embed = make_embed("Message Edited", None, color=LOG_COLOR)
        embed.add_field(name="Author", value=before.author.mention, inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Before", value=(before.content or "*(empty)*")[:1024], inline=False)
        embed.add_field(name="After", value=(after.content or "*(empty)*")[:1024], inline=False)
        await self._send_log(embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel == after.channel:
            return

        logger.info("Voice activity: %s moved from %s to %s", member, before.channel, after.channel)

        if before.channel is None:
            description = f"{member.mention} joined {after.channel.mention}"
        elif after.channel is None:
            description = f"{member.mention} left {before.channel.mention}"
        else:
            description = f"{member.mention} moved from {before.channel.mention} to {after.channel.mention}"

        await self._send_log(make_embed("Voice Activity", description, color=LOG_COLOR))

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        location = interaction.guild.name if interaction.guild else "a DM"
        logger.info("Command used: /%s by %s in %s", command.qualified_name, interaction.user, location)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logging(bot))
