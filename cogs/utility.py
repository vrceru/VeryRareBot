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
from services import system

INVITE_PERMISSIONS = discord.Permissions(
    view_channel=True,
    send_messages=True,
    embed_links=True,
    attach_files=True,
    read_message_history=True,
    manage_messages=True,
    manage_channels=True,
    manage_roles=True,
    kick_members=True,
    ban_members=True,
    moderate_members=True,
    connect=True,
    speak=True,
    use_voice_activation=True,
)


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


    @app_commands.command(
        name="avatar",
        description="Shows a member's avatar."
    )
    @app_commands.describe(
        member="Member to look up. Defaults to you."
    )
    async def avatar(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None
    ):

        member = member or interaction.user

        embed = utility_embed(
            f"{member.display_name}'s Avatar"
        )

        embed.set_image(
            url=member.display_avatar.url
        )

        await interaction.response.send_message(
            embed=embed
        )


    @app_commands.command(
        name="userinfo",
        description="Shows information about a member."
    )
    @app_commands.describe(
        member="Member to look up. Defaults to you."
    )
    async def userinfo(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None
    ):

        member = member or interaction.user

        embed = utility_embed(
            f"User Info: {member.display_name}"
        )

        embed.set_thumbnail(
            url=member.display_avatar.url
        )

        embed.add_field(
            name="Username",
            value=str(member),
            inline=True
        )

        embed.add_field(
            name="ID",
            value=str(member.id),
            inline=True
        )

        embed.add_field(
            name="Bot Account",
            value="Yes" if member.bot else "No",
            inline=True
        )

        embed.add_field(
            name="Account Created",
            value=discord.utils.format_dt(member.created_at, style="R"),
            inline=True
        )

        if member.joined_at:
            embed.add_field(
                name="Joined Server",
                value=discord.utils.format_dt(member.joined_at, style="R"),
                inline=True
            )

        embed.add_field(
            name="Top Role",
            value=member.top_role.mention,
            inline=True
        )

        roles = [role.mention for role in reversed(member.roles) if role.name != "@everyone"]

        embed.add_field(
            name=f"Roles ({len(roles)})",
            value=" ".join(roles[:20]) if roles else "None",
            inline=False
        )

        await interaction.response.send_message(
            embed=embed
        )


    @app_commands.command(
        name="botstats",
        description="Shows detailed bot runtime statistics."
    )
    async def botstats(
        self,
        interaction: discord.Interaction
    ):

        seconds = int(
            time.time() - self.start_time
        )

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        member_count = sum(
            guild.member_count or 0
            for guild in self.bot.guilds
        )

        embed = utility_embed(
            "Bot Statistics"
        )

        embed.add_field(
            name="Version",
            value=get_version(),
            inline=True
        )

        embed.add_field(
            name="Latency",
            value=f"{round(self.bot.latency * 1000)} ms",
            inline=True
        )

        embed.add_field(
            name="Uptime",
            value=f"{hours}h {minutes}m {secs}s",
            inline=True
        )

        embed.add_field(
            name="Servers",
            value=str(len(self.bot.guilds)),
            inline=True
        )

        embed.add_field(
            name="Members",
            value=str(member_count),
            inline=True
        )

        embed.add_field(
            name="Commands",
            value=str(len(self.bot.tree.get_commands())),
            inline=True
        )

        embed.add_field(
            name="CPU Usage",
            value=f"{system.cpu_usage()}%",
            inline=True
        )

        embed.add_field(
            name="Memory Usage",
            value=f"{system.memory_usage().percent}%",
            inline=True
        )

        embed.add_field(
            name="discord.py",
            value=discord.__version__,
            inline=True
        )

        await interaction.response.send_message(
            embed=embed
        )


    @app_commands.command(
        name="invite",
        description="Get an invite link to add VeryRareBot to another server."
    )
    async def invite(
        self,
        interaction: discord.Interaction
    ):

        url = discord.utils.oauth_url(
            self.bot.application_id or self.bot.user.id,
            permissions=INVITE_PERMISSIONS,
            scopes=("bot", "applications.commands")
        )

        embed = info_embed(
            "Invite VeryRareBot",
            f"[Click here to add VeryRareBot to your server]({url})"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


async def setup(bot):

    await bot.add_cog(
        Utility(bot)
    )
