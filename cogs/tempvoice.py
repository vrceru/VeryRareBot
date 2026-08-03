"""Join-to-create temporary voice channels with owner controls, replacing the
third-party TempVoice bot. Configuration is per-guild and stored in the
database via /voice setup, not environment variables -- no restart needed to
change the trigger channel.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import admin_access, has_any_role
from core.embed import error_embed, success_embed, tempvoice_embed
from config import settings

logger = logging.getLogger("VeryRareBot")

STAFF_ROLE_IDS = [
    settings.OWNER_ROLE_ID,
    settings.DEV_OPS_ROLE_ID,
    settings.ADMIN_ROLE_ID,
    settings.STAFF_ROLE_ID,
]


def _is_staff(interaction: discord.Interaction) -> bool:
    return has_any_role(interaction, STAFF_ROLE_IDS)


async def _reply(interaction: discord.Interaction, embed: discord.Embed) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def _get_owned_temp_channel(bot: commands.Bot, interaction: discord.Interaction):
    """Validate the invoker is in a temp channel they own (or is staff).

    Sends an error and returns None if not; otherwise returns (row, channel).
    """

    member = interaction.user
    if not isinstance(member, discord.Member) or member.voice is None or member.voice.channel is None:
        await _reply(interaction, error_embed("Not in a Temp Channel", "Join your temporary voice channel first."))
        return None

    channel = member.voice.channel
    temp = await bot.db.get_tempvoice_channel(channel.id)
    if temp is None:
        await _reply(interaction, error_embed("Not a Temp Channel", "This isn't a temporary voice channel."))
        return None

    if temp["owner_id"] != member.id and not _is_staff(interaction):
        await _reply(interaction, error_embed("Not Your Channel", "Only the channel owner can do that."))
        return None

    return temp, channel


async def do_lock(bot: commands.Bot, interaction: discord.Interaction) -> None:
    result = await _get_owned_temp_channel(bot, interaction)
    if result is None:
        return
    _, channel = result
    overwrite = channel.overwrites_for(interaction.guild.default_role)
    overwrite.connect = False
    await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await _reply(interaction, success_embed("Channel Locked", "New members can no longer join."))


async def do_unlock(bot: commands.Bot, interaction: discord.Interaction) -> None:
    result = await _get_owned_temp_channel(bot, interaction)
    if result is None:
        return
    _, channel = result
    overwrite = channel.overwrites_for(interaction.guild.default_role)
    overwrite.connect = None
    await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await _reply(interaction, success_embed("Channel Unlocked", "Anyone can join again."))


async def do_rename(bot: commands.Bot, interaction: discord.Interaction, name: str) -> None:
    result = await _get_owned_temp_channel(bot, interaction)
    if result is None:
        return
    _, channel = result
    name = name.strip()[:100] or channel.name
    await channel.edit(name=name)
    await _reply(interaction, success_embed("Renamed", f"Channel renamed to **{name}**."))


async def do_limit(bot: commands.Bot, interaction: discord.Interaction, limit: int) -> None:
    result = await _get_owned_temp_channel(bot, interaction)
    if result is None:
        return
    _, channel = result
    await channel.edit(user_limit=limit)
    await _reply(interaction, success_embed("Limit Updated", f"User limit set to {'unlimited' if limit == 0 else limit}."))


async def do_claim(bot: commands.Bot, interaction: discord.Interaction) -> None:
    member = interaction.user
    if not isinstance(member, discord.Member) or member.voice is None or member.voice.channel is None:
        await _reply(interaction, error_embed("Not in a Voice Channel", "Join the channel you want to claim first."))
        return

    channel = member.voice.channel
    temp = await bot.db.get_tempvoice_channel(channel.id)
    if temp is None:
        await _reply(interaction, error_embed("Not a Temp Channel", "This isn't a temporary voice channel."))
        return

    if any(m.id == temp["owner_id"] for m in channel.members):
        await _reply(interaction, error_embed("Owner Present", "The current owner is still in the channel."))
        return

    await bot.db.set_tempvoice_owner(channel.id, member.id)
    overwrite = channel.overwrites_for(member)
    overwrite.manage_channels = True
    overwrite.move_members = True
    await channel.set_permissions(member, overwrite=overwrite)
    await _reply(interaction, success_embed("Ownership Claimed", f"{member.mention} is now the owner of this channel."))


class RenameModal(discord.ui.Modal, title="Rename Channel"):
    name = discord.ui.TextInput(label="New channel name", max_length=100)

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await do_rename(self.bot, interaction, self.name.value)


class LimitModal(discord.ui.Modal, title="Set User Limit"):
    limit = discord.ui.TextInput(label="Max users (0 = unlimited)", max_length=2, placeholder="0-99")

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(self.limit.value)
        except ValueError:
            await _reply(interaction, error_embed("Invalid Number", "Enter a whole number from 0 to 99."))
            return
        if not 0 <= value <= 99:
            await _reply(interaction, error_embed("Out of Range", "Must be between 0 and 99."))
            return
        await do_limit(self.bot, interaction, value)


class TempVoiceControlView(discord.ui.View):
    """Posted once in each new temp channel's chat. Stateless: every button looks up
    the invoker's current voice channel rather than baking a channel ID into itself,
    so a single registered instance covers every temp channel that ever exists."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Lock", emoji="🔒", style=discord.ButtonStyle.secondary, custom_id="tempvoice:lock")
    async def lock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await do_lock(self.bot, interaction)

    @discord.ui.button(label="Unlock", emoji="🔓", style=discord.ButtonStyle.secondary, custom_id="tempvoice:unlock")
    async def unlock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await do_unlock(self.bot, interaction)

    @discord.ui.button(label="Rename", emoji="✏️", style=discord.ButtonStyle.primary, custom_id="tempvoice:rename")
    async def rename_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RenameModal(self.bot))

    @discord.ui.button(label="Limit", emoji="🔢", style=discord.ButtonStyle.primary, custom_id="tempvoice:limit")
    async def limit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LimitModal(self.bot))

    @discord.ui.button(label="Claim", emoji="👑", style=discord.ButtonStyle.success, custom_id="tempvoice:claim")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await do_claim(self.bot, interaction)


class TempVoice(commands.Cog):
    """Join-to-create temporary voice channels."""

    voice = app_commands.Group(name="voice", description="Temporary voice channel commands.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(TempVoiceControlView(bot))

    async def _create_temp_channel(self, member: discord.Member, config) -> None:
        guild = member.guild
        category = guild.get_channel(config["category_id"]) if config["category_id"] else None
        if not isinstance(category, discord.CategoryChannel):
            category = None

        overwrites = {
            member: discord.PermissionOverwrite(
                view_channel=True, connect=True, manage_channels=True, move_members=True
            ),
        }

        try:
            channel = await guild.create_voice_channel(
                name=f"{member.display_name}'s Channel"[:100],
                category=category,
                overwrites=overwrites,
                reason=f"Temp voice channel for {member} ({member.id})",
            )
            await member.move_to(channel, reason="Joined the create-a-channel trigger.")
        except discord.HTTPException:
            logger.exception("Failed to create a temp voice channel for %s", member)
            return

        await self.bot.db.create_tempvoice_channel(channel.id, guild.id, member.id)

        embed = tempvoice_embed(
            f"{member.display_name}'s Channel",
            "This is your temporary voice channel. Use the buttons below to manage it, or right-click "
            "the channel for Discord's own settings (you have Manage Channel access here). "
            "It's deleted automatically once everyone leaves.",
        )
        try:
            await channel.send(embed=embed, view=TempVoiceControlView(self.bot))
        except discord.HTTPException:
            logger.warning("Failed to post the control panel in temp channel %s.", channel.id)

    @admin_access()
    @voice.command(name="setup", description="Configure the join-to-create trigger channel.")
    @app_commands.describe(
        trigger_channel="Voice channel that spawns a new temp channel when someone joins it.",
        category="Category new temp channels are created under. Defaults to the trigger channel's own category.",
    )
    async def setup(
        self,
        interaction: discord.Interaction,
        trigger_channel: discord.VoiceChannel,
        category: discord.CategoryChannel | None = None,
    ):
        category_id = category.id if category else trigger_channel.category_id
        await self.bot.db.set_tempvoice_config(interaction.guild_id, trigger_channel.id, category_id)

        category_obj = interaction.guild.get_channel(category_id) if category_id else None
        destination = f"under **{category_obj.name}**" if category_obj else "at the server root"
        await interaction.response.send_message(
            embed=success_embed(
                "TempVoice Configured",
                f"Joining {trigger_channel.mention} now creates a temporary voice channel {destination}.",
            ),
            ephemeral=True,
        )

    @admin_access()
    @voice.command(name="disable", description="Turn off join-to-create temp voice channels.")
    async def disable(self, interaction: discord.Interaction):
        cleared = await self.bot.db.clear_tempvoice_config(interaction.guild_id)
        if not cleared:
            await interaction.response.send_message(
                embed=error_embed("Not Configured", "TempVoice isn't set up for this server."), ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=success_embed("TempVoice Disabled", "Existing temp channels are unaffected; no new ones will be created."),
            ephemeral=True,
        )

    @voice.command(name="lock", description="Lock your temp voice channel so no one new can join.")
    async def lock(self, interaction: discord.Interaction):
        await do_lock(self.bot, interaction)

    @voice.command(name="unlock", description="Unlock your temp voice channel.")
    async def unlock(self, interaction: discord.Interaction):
        await do_unlock(self.bot, interaction)

    @voice.command(name="rename", description="Rename your temp voice channel.")
    @app_commands.describe(name="New channel name.")
    async def rename(self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 100]):
        await do_rename(self.bot, interaction, name)

    @voice.command(name="limit", description="Set a user limit for your temp voice channel.")
    @app_commands.describe(limit="Max users allowed, 0-99 (0 = unlimited).")
    async def limit(self, interaction: discord.Interaction, limit: app_commands.Range[int, 0, 99]):
        await do_limit(self.bot, interaction, limit)

    @voice.command(name="claim", description="Claim ownership of a temp voice channel whose owner has left.")
    async def claim(self, interaction: discord.Interaction):
        await do_claim(self.bot, interaction)

    @voice.command(name="kick", description="Remove someone from your temp voice channel.")
    @app_commands.describe(member="Member to remove.")
    async def kick(self, interaction: discord.Interaction, member: discord.Member):
        result = await _get_owned_temp_channel(self.bot, interaction)
        if result is None:
            return
        _, channel = result

        if member.voice is None or member.voice.channel != channel:
            await interaction.response.send_message(
                embed=error_embed("Not in Channel", f"{member.mention} isn't in this channel."), ephemeral=True
            )
            return
        if member.id == interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed("Can't Kick Yourself", "Use `/voice lock` to keep others out instead."), ephemeral=True
            )
            return

        await member.move_to(None, reason=f"Removed by channel owner {interaction.user} ({interaction.user.id})")
        await interaction.response.send_message(embed=success_embed("Member Removed", f"Removed {member.mention}."), ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        if after.channel is not None and after.channel != before.channel:
            config = await self.bot.db.get_tempvoice_config(member.guild.id)
            if config and after.channel.id == config["trigger_channel_id"]:
                await self._create_temp_channel(member, config)

        if before.channel is not None and before.channel != after.channel:
            temp = await self.bot.db.get_tempvoice_channel(before.channel.id)
            if temp is not None and not any(not m.bot for m in before.channel.members):
                try:
                    await before.channel.delete(reason="Temp voice channel is empty.")
                except discord.HTTPException:
                    logger.warning("Failed to delete empty temp voice channel %s.", before.channel.id)
                await self.bot.db.delete_tempvoice_channel(before.channel.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(TempVoice(bot))
