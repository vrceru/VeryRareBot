import time

import discord
from discord import app_commands
from discord.ext import commands

from core.version import get_version
from core.embed import (
    utility_embed,
    info_embed
)

from config import settings


class Utility(commands.Cog):
    """General utility commands."""

    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()


    @app_commands.command(
        name="ping",
        description="Shows the bot latency."
    )
    async def ping(
        self,
        interaction: discord.Interaction
    ):

        latency = round(
            self.bot.latency * 1000
        )

        embed = utility_embed(
            "Pong!"
        )

        embed.add_field(
            name="Latency",
            value=f"{latency} ms",
            inline=False
        )

        await interaction.response.send_message(
            embed=embed
        )


    @app_commands.command(
        name="version",
        description="Displays the current bot version."
    )
    async def version(
        self,
        interaction: discord.Interaction
    ):

        embed = info_embed(
            "VeryRareBot"
        )

        embed.add_field(
            name="Version",
            value=get_version(),
            inline=False
        )

        await interaction.response.send_message(
            embed=embed
        )


    @app_commands.command(
        name="uptime",
        description="Shows how long the bot has been running."
    )
    async def uptime(
        self,
        interaction: discord.Interaction
    ):

        seconds = int(
            time.time() - self.start_time
        )

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        embed = utility_embed(
            "Bot Uptime"
        )

        embed.add_field(
            name="Running Time",
            value=f"{hours}h {minutes}m {secs}s",
            inline=False
        )

        await interaction.response.send_message(
            embed=embed
        )


    @app_commands.command(
        name="about",
        description="Information about VeryRareBot."
    )
    async def about(
        self,
        interaction: discord.Interaction
    ):

        embed = info_embed(
            "VeryRareBot",
            "Official Discord assistant for the Very Rare Society ecosystem."
        )

        embed.add_field(
            name="Version",
            value=get_version(),
            inline=True
        )

        embed.add_field(
            name="Language",
            value="Python",
            inline=True
        )

        embed.add_field(
            name="Framework",
            value="discord.py",
            inline=True
        )

        await interaction.response.send_message(
            embed=embed
        )


    @app_commands.command(
        name="whoami",
        description="Shows your VeryRareBot permission roles."
    )
    async def whoami(
        self,
        interaction: discord.Interaction
    ):

        user_roles = [
            role.id
            for role in interaction.user.roles
        ]

        detected_roles = []


        if settings.OWNER_ROLE_ID in user_roles:
            detected_roles.append(
                "Owner"
            )


        if settings.DEV_OPS_ROLE_ID in user_roles:
            detected_roles.append(
                "Dev Ops"
            )


        if settings.ADMIN_ROLE_ID in user_roles:
            detected_roles.append(
                "Admin"
            )


        if settings.STAFF_ROLE_ID in user_roles:
            detected_roles.append(
                "Staff"
            )


        if settings.VRS_MEMBER_ROLE_ID in user_roles:
            detected_roles.append(
                "VRS Member"
            )


        if not detected_roles:
            detected_roles.append(
                "No recognized role"
            )


        embed = utility_embed(
            "Permission Check",
            "VeryRareBot role identification."
        )


        embed.add_field(
            name="User",
            value=interaction.user.mention,
            inline=False
        )


        embed.add_field(
            name="Detected Roles",
            value="\n".join(detected_roles),
            inline=False
        )


        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


async def setup(bot):

    await bot.add_cog(
        Utility(bot)
    )
