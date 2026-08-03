import discord

from datetime import timedelta

from discord.ext import commands
from discord import app_commands

from config import settings

from core.embed import (
    admin_embed,
    success_embed,
    error_embed,
    warning_embed
)

from core.checks import admin_access, moderation_target_error


class Admin(commands.Cog):
    """Administrative and moderation Discord commands."""

    def __init__(self, bot):
        self.bot = bot


    @admin_access()
    @app_commands.command(
        name="announce",
        description="Send an official server announcement."
    )
    @app_commands.describe(
        message="Announcement message."
    )
    async def announce(
        self,
        interaction: discord.Interaction,
        message: str
    ):

        channel = self.bot.get_channel(
            settings.ANNOUNCEMENT_CHANNEL_ID
        )

        if channel is None:

            await interaction.response.send_message(
                embed=error_embed(
                    "Announcement Failed",
                    "Announcement channel is not configured."
                ),
                ephemeral=True
            )

            return


        embed = admin_embed(
            "Official Announcement",
            message
        )

        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url
        )


        await channel.send(
            embed=embed
        )


        await interaction.response.send_message(
            embed=success_embed(
                "Announcement Sent",
                f"Posted in {channel.mention}"
            ),
            ephemeral=True
        )


    @admin_access()
    @app_commands.command(
        name="maintenance",
        description="Announce scheduled maintenance."
    )
    @app_commands.describe(
        message="What's happening and any relevant details.",
        starts_in_minutes="Minutes until maintenance begins, if known."
    )
    async def maintenance(
        self,
        interaction: discord.Interaction,
        message: str,
        starts_in_minutes: app_commands.Range[int, 0, 43200] | None = None
    ):

        channel = self.bot.get_channel(
            settings.ANNOUNCEMENT_CHANNEL_ID
        )

        if channel is None:

            await interaction.response.send_message(
                embed=error_embed(
                    "Announcement Failed",
                    "Announcement channel is not configured."
                ),
                ephemeral=True
            )

            return


        embed = warning_embed(
            "Scheduled Maintenance",
            message
        )

        if starts_in_minutes is not None:
            start_time = discord.utils.utcnow() + timedelta(minutes=starts_in_minutes)
            embed.add_field(
                name="Starts",
                value=discord.utils.format_dt(start_time, style="R"),
                inline=False
            )

        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url
        )


        await channel.send(
            embed=embed
        )


        await interaction.response.send_message(
            embed=success_embed(
                "Maintenance Notice Sent",
                f"Posted in {channel.mention}"
            ),
            ephemeral=True
        )


    @admin_access()
    @app_commands.command(
        name="warn",
        description="Warn a member."
    )
    @app_commands.describe(
        member="Member to warn.",
        reason="Reason for warning."
    )
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str
    ):

        target_error = moderation_target_error(interaction, member)
        if target_error:
            await interaction.response.send_message(
                embed=error_embed("Cannot Warn Member", target_error),
                ephemeral=True
            )
            return

        warning_id = await self.bot.db.add_warning(
            interaction.guild_id,
            member.id,
            interaction.user.id,
            reason
        )

        embed = admin_embed(
            "Member Warning"
        )

        embed.add_field(
            name="Member",
            value=member.mention,
            inline=False
        )

        embed.add_field(
            name="Reason",
            value=reason,
            inline=False
        )

        embed.add_field(
            name="Issued By",
            value=interaction.user.mention,
            inline=False
        )

        embed.set_footer(
            text=f"Warning #{warning_id}"
        )


        await interaction.response.send_message(
            embed=embed
        )


        try:
            await member.send(
                embed=embed
            )

        except discord.Forbidden:
            pass


    @admin_access()
    @app_commands.command(
        name="warnings",
        description="View a member's warning history."
    )
    @app_commands.describe(
        member="Member to look up."
    )
    async def warnings(
        self,
        interaction: discord.Interaction,
        member: discord.Member
    ):

        records = await self.bot.db.list_warnings(interaction.guild_id, member.id)

        embed = admin_embed(
            f"Warnings for {member.display_name}"
        )

        if not records:
            embed.description = "No warnings on record."

        for record in records[:10]:
            embed.add_field(
                name=f"#{record['id']} • {record['created_at']}",
                value=f"{record['reason']}\nIssued by <@{record['moderator_id']}>",
                inline=False
            )

        if len(records) > 10:
            embed.set_footer(text=f"Showing 10 of {len(records)} warnings.")

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


    @admin_access()
    @app_commands.command(
        name="clearwarnings",
        description="Clear a member's warning history."
    )
    @app_commands.describe(
        member="Member whose warnings should be cleared."
    )
    async def clear_warnings(
        self,
        interaction: discord.Interaction,
        member: discord.Member
    ):

        cleared = await self.bot.db.clear_warnings(interaction.guild_id, member.id)

        await interaction.response.send_message(
            embed=success_embed(
                "Warnings Cleared",
                f"Cleared {cleared} warning(s) for {member.mention}."
            ),
            ephemeral=True
        )


    @admin_access()
    @app_commands.command(
        name="mute",
        description="Timeout a member."
    )
    @app_commands.describe(
        member="Member to timeout.",
        minutes="Timeout duration in minutes.",
        reason="Reason for timeout."
    )
    async def mute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: int,
        reason: str
    ):

        target_error = moderation_target_error(interaction, member)
        if target_error:
            await interaction.response.send_message(
                embed=error_embed("Cannot Mute Member", target_error),
                ephemeral=True
            )
            return

        if not 1 <= minutes <= 40320:

            await interaction.response.send_message(
                embed=error_embed(
                    "Invalid Duration",
                "Timeout duration must be between 1 minute and 28 days."
                ),
                ephemeral=True
            )

            return


        await member.timeout(
            timedelta(
                minutes=minutes
            ),
            reason=reason
        )


        await interaction.response.send_message(
            embed=success_embed(
                "Member Muted",
                f"{member.mention} was timed out for {minutes} minutes."
            )
        )


    @admin_access()
    @app_commands.command(
        name="kick",
        description="Kick a member from the server."
    )
    @app_commands.describe(
        member="Member to kick.",
        reason="Reason for the kick."
    )
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason provided."
    ):

        target_error = moderation_target_error(interaction, member)
        if target_error:
            await interaction.response.send_message(
                embed=error_embed("Cannot Kick Member", target_error),
                ephemeral=True
            )
            return

        try:
            await member.kick(reason=f"{interaction.user} ({interaction.user.id}): {reason}")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Kick Failed", "I don't have permission to kick that member."),
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=success_embed(
                "Member Kicked",
                f"{member.mention} was kicked.\nReason: {reason}"
            )
        )


    @admin_access()
    @app_commands.command(
        name="ban",
        description="Ban a member from the server."
    )
    @app_commands.describe(
        member="Member to ban.",
        reason="Reason for the ban.",
        delete_message_days="Delete this member's messages from the last N days (0-7)."
    )
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason provided.",
        delete_message_days: app_commands.Range[int, 0, 7] = 0
    ):

        target_error = moderation_target_error(interaction, member)
        if target_error:
            await interaction.response.send_message(
                embed=error_embed("Cannot Ban Member", target_error),
                ephemeral=True
            )
            return

        try:
            await member.ban(
                reason=f"{interaction.user} ({interaction.user.id}): {reason}",
                delete_message_seconds=delete_message_days * 86400
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Ban Failed", "I don't have permission to ban that member."),
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=success_embed(
                "Member Banned",
                f"{member.mention} was banned.\nReason: {reason}"
            )
        )


    @admin_access()
    @app_commands.command(
        name="slowmode",
        description="Set slowmode on this channel."
    )
    @app_commands.describe(
        seconds="Slowmode delay in seconds (0 to disable, max 21600)."
    )
    async def slowmode(
        self,
        interaction: discord.Interaction,
        seconds: app_commands.Range[int, 0, 21600]
    ):

        channel = interaction.channel

        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed("Unsupported Channel", "Slowmode can only be set on text channels."),
                ephemeral=True
            )
            return

        await channel.edit(slowmode_delay=seconds)

        if seconds == 0:
            description = f"Slowmode disabled in {channel.mention}."
        else:
            description = f"Slowmode set to {seconds} second(s) in {channel.mention}."

        await interaction.response.send_message(
            embed=success_embed("Slowmode Updated", description),
            ephemeral=True
        )


    @admin_access()
    @app_commands.command(
        name="lock",
        description="Prevent everyone from sending messages in this channel."
    )
    @app_commands.describe(
        reason="Reason for locking the channel."
    )
    async def lock(
        self,
        interaction: discord.Interaction,
        reason: str = "No reason provided."
    ):

        channel = interaction.channel

        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed("Unsupported Channel", "Only text channels can be locked."),
                ephemeral=True
            )
            return

        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False

        await channel.set_permissions(
            interaction.guild.default_role,
            overwrite=overwrite,
            reason=reason
        )

        await interaction.response.send_message(
            embed=success_embed("Channel Locked", f"{channel.mention} is now locked.\nReason: {reason}")
        )


    @admin_access()
    @app_commands.command(
        name="unlock",
        description="Allow everyone to send messages in this channel again."
    )
    async def unlock(
        self,
        interaction: discord.Interaction
    ):

        channel = interaction.channel

        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed("Unsupported Channel", "Only text channels can be unlocked."),
                ephemeral=True
            )
            return

        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None

        await channel.set_permissions(
            interaction.guild.default_role,
            overwrite=overwrite,
            reason=f"Unlocked by {interaction.user}"
        )

        await interaction.response.send_message(
            embed=success_embed("Channel Unlocked", f"{channel.mention} is now unlocked.")
        )


    @admin_access()
    @app_commands.command(
        name="clear",
        description="Delete messages from a channel."
    )
    @app_commands.describe(
        amount="Number of messages to delete."
    )
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: int
    ):

        if not interaction.channel or not hasattr(interaction.channel, "purge"):

            await interaction.response.send_message(
                embed=error_embed(
                    "Error",
                    "Channel unavailable."
                ),
                ephemeral=True
            )

            return


        if not 1 <= amount <= 100:
            await interaction.response.send_message(
                embed=error_embed("Invalid Amount", "Choose between 1 and 100 messages."),
                ephemeral=True
            )
            return

        await interaction.response.defer(
            ephemeral=True
        )


        deleted = await interaction.channel.purge(
            limit=amount
        )


        await interaction.followup.send(
            embed=success_embed(
                "Messages Cleared",
                f"Deleted {len(deleted)} messages."
            ),
            ephemeral=True
        )



async def setup(bot):

    await bot.add_cog(
        Admin(bot)
    )
