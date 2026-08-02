import discord
from discord import app_commands
from discord.ext import commands

from core.embed import error_embed, jellyfin_embed
from services.jellyfin import JellyfinClient, JellyfinError
from views.media_buttons import MediaButtons


class Jellyfin(commands.Cog):
    """Jellyfin status and discovery commands."""

    jellyfin = app_commands.Group(name="jellyfin", description="Jellyfin media server commands.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def client_or_error(self, interaction: discord.Interaction) -> JellyfinClient | None:
        try:
            return JellyfinClient.from_settings()
        except JellyfinError as exc:
            await interaction.response.send_message(embed=error_embed("Jellyfin Unavailable", str(exc)), ephemeral=True)
            return None

    @jellyfin.command(name="status", description="Show Jellyfin server status.")
    async def status(self, interaction: discord.Interaction):
        client = await self.client_or_error(interaction)
        if not client:
            return
        try:
            info = await client.system_info()
        except JellyfinError as exc:
            await interaction.response.send_message(embed=error_embed("Jellyfin Unavailable", str(exc)), ephemeral=True)
            return
        embed = jellyfin_embed("Jellyfin Status")
        embed.add_field(name="Server", value=info.get("ServerName", "Unknown"), inline=False)
        embed.add_field(name="Version", value=info.get("Version", "Unknown"), inline=True)
        embed.add_field(name="Operating System", value=info.get("OperatingSystem", "Unknown"), inline=True)
        await interaction.response.send_message(embed=embed)

    @jellyfin.command(name="nowplaying", description="Show active Jellyfin playback sessions.")
    async def now_playing(self, interaction: discord.Interaction):
        client = await self.client_or_error(interaction)
        if not client:
            return
        try:
            sessions = await client.sessions()
        except JellyfinError as exc:
            await interaction.response.send_message(embed=error_embed("Jellyfin Unavailable", str(exc)), ephemeral=True)
            return
        playing = [session for session in sessions if session.get("NowPlayingItem")]
        embed = jellyfin_embed("Now Playing")
        if not playing:
            embed.description = "Nothing is playing right now."
        for session in playing[:10]:
            item = session["NowPlayingItem"]
            user = session.get("UserName", "Unknown user")
            title = item.get("Name", "Unknown title")
            series = item.get("SeriesName")
            embed.add_field(name=user, value=f"{series + ' — ' if series else ''}{title}", inline=False)
        await interaction.response.send_message(embed=embed)

    @jellyfin.command(name="libraries", description="List available Jellyfin libraries.")
    async def libraries(self, interaction: discord.Interaction):
        client = await self.client_or_error(interaction)
        if not client:
            return
        try:
            libraries = await client.libraries()
        except JellyfinError as exc:
            await interaction.response.send_message(embed=error_embed("Jellyfin Unavailable", str(exc)), ephemeral=True)
            return
        names = [str(library.get("Name", "Unnamed")) for library in libraries[:25]]
        description = "\n".join(f"• {name}" for name in names) or "No libraries found."
        if len(libraries) > len(names):
            description += f"\n… and {len(libraries) - len(names)} more."
        embed = jellyfin_embed("Jellyfin Libraries", description)
        await interaction.response.send_message(embed=embed)

    @jellyfin.command(name="search", description="Search Jellyfin media.")
    @app_commands.describe(query="Movie, series, episode, or music to search for.")
    async def search(self, interaction: discord.Interaction, query: str):
        client = await self.client_or_error(interaction)
        if not client:
            return
        try:
            items = await client.search(query)
        except JellyfinError as exc:
            await interaction.response.send_message(embed=error_embed("Jellyfin Unavailable", str(exc)), ephemeral=True)
            return
        if not items:
            await interaction.response.send_message(embed=jellyfin_embed("Search Results", "No matching media found."), ephemeral=True)
            return
        embed = jellyfin_embed(f"Search Results: {query}")
        for item in items:
            year = f" ({item['ProductionYear']})" if item.get("ProductionYear") else ""
            embed.add_field(name=f"{item.get('Name', 'Untitled')}{year}", value=item.get("Type", "Media"), inline=False)
        await interaction.response.send_message(embed=embed, view=MediaButtons(client.base_url))


async def setup(bot: commands.Bot):
    await bot.add_cog(Jellyfin(bot))
