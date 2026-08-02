import discord
from discord import app_commands
from discord.ext import commands

from core.checks import devops_access
from core.embed import error_embed, success_embed, vrms_embed
from services import vrms


class VRMS(commands.Cog):
    """VRMS deployment and service controls."""

    vrms_group = app_commands.Group(name="vrms", description="VRMS service commands.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @vrms_group.command(name="status", description="Show VRMS path and service status.")
    @devops_access()
    async def status(self, interaction: discord.Interaction):
        try:
            result = await vrms.status()
        except vrms.VRMSError as exc:
            await interaction.response.send_message(embed=error_embed("VRMS Unavailable", str(exc)), ephemeral=True)
            return
        embed = vrms_embed("VRMS Status")
        embed.add_field(name="Project Path", value=result.path, inline=False)
        embed.add_field(name="Path Available", value="Yes" if result.path_exists else "No", inline=True)
        embed.add_field(name="Service", value=result.service_state or "Not configured", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def run_action(self, interaction: discord.Interaction, action: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            state = await vrms.service_action(action)
        except vrms.VRMSError as exc:
            await interaction.followup.send(embed=error_embed("VRMS Action Failed", str(exc)), ephemeral=True)
            return
        await interaction.followup.send(embed=success_embed("VRMS Updated", f"Service is now **{state}**."), ephemeral=True)

    @vrms_group.command(name="start", description="Start the configured VRMS systemd service.")
    @devops_access()
    async def start(self, interaction: discord.Interaction):
        await self.run_action(interaction, "start")

    @vrms_group.command(name="stop", description="Stop the configured VRMS systemd service.")
    @devops_access()
    async def stop(self, interaction: discord.Interaction):
        await self.run_action(interaction, "stop")

    @vrms_group.command(name="restart", description="Restart the configured VRMS systemd service.")
    @devops_access()
    async def restart(self, interaction: discord.Interaction):
        await self.run_action(interaction, "restart")


async def setup(bot: commands.Bot):
    await bot.add_cog(VRMS(bot))
