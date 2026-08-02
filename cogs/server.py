import discord

from discord.ext import commands
from discord import app_commands

from services import system

from core.embed import server_embed
from core.checks import devops_access


class Server(commands.Cog):
    """Server monitoring commands."""

    def __init__(self, bot):
        self.bot = bot


    @devops_access()
    @app_commands.command(
        name="serverinfo",
        description="Displays information about the host server."
    )
    async def serverinfo(
        self,
        interaction: discord.Interaction
    ):

        memory = system.memory_usage()
        disk = system.disk_usage()

        embed = server_embed(
            "Server Information"
        )

        embed.add_field(
            name="Hostname",
            value=system.hostname(),
            inline=False
        )

        embed.add_field(
            name="Operating System",
            value=system.operating_system(),
            inline=False
        )

        embed.add_field(
            name="Python",
            value=system.python_version(),
            inline=True
        )

        embed.add_field(
            name="CPU Usage",
            value=f"{system.cpu_usage()}%",
            inline=True
        )

        embed.add_field(
            name="Memory",
            value=f"{memory.percent}%",
            inline=True
        )

        embed.add_field(
            name="Disk",
            value=f"{disk.percent}%",
            inline=True
        )

        embed.add_field(
            name="Server Uptime",
            value=system.uptime(),
            inline=False
        )

        await interaction.response.send_message(
            embed=embed
        )


async def setup(bot):

    await bot.add_cog(
        Server(bot)
    )
