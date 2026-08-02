import discord

from datetime import timedelta

from discord.ext import commands
from discord import app_commands

from config import settings

from core.embed import (
    admin_embed,
    success_embed,
    error_embed
)

from core.checks import admin_access


class Admin(commands.Cog):
    """Administrative Discord commands."""

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

        if minutes > 40320:

            await interaction.response.send_message(
                embed=error_embed(
                    "Invalid Duration",
                    "Maximum timeout duration is 28 days."
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

        if not interaction.channel:

            await interaction.response.send_message(
                embed=error_embed(
                    "Error",
                    "Channel unavailable."
                ),
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
