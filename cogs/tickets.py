import logging

import discord
from discord import app_commands
from discord.ext import commands

from config import settings
from core.checks import admin_access, has_any_role
from core.embed import error_embed, make_embed, success_embed
from services.tickets import TICKET_CATEGORIES, TicketCategory, channel_slug

logger = logging.getLogger("VeryRareBot")

CATEGORY_CHOICES = [
    app_commands.Choice(name=f"{category.emoji} {category.label}", value=category.key)
    for category in TICKET_CATEGORIES.values()
]

STAFF_ROLE_IDS = [
    settings.OWNER_ROLE_ID,
    settings.DEV_OPS_ROLE_ID,
    settings.ADMIN_ROLE_ID,
    settings.TICKET_STAFF_ROLE_ID,
]


def _is_staff(interaction: discord.Interaction) -> bool:
    return has_any_role(interaction, STAFF_ROLE_IDS)


def build_ticket_embed(category: TicketCategory, opener: discord.Member, answers: dict[str, str], ticket_id: int) -> discord.Embed:
    embed = make_embed(f"{category.emoji} {category.label}", category.intro, color=category.color)
    embed.add_field(name="Opened By", value=opener.mention, inline=False)
    for label, value in answers.items():
        embed.add_field(name=label, value=value or "*(not provided)*", inline=False)
    embed.set_footer(text=f"Ticket #{ticket_id}")
    return embed


async def create_ticket_channel(interaction: discord.Interaction, category: TicketCategory, answers: dict[str, str]) -> None:
    bot = interaction.client
    guild = interaction.guild

    if guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            embed=error_embed("Server Only", "Tickets can only be opened in a server."),
            ephemeral=True,
        )
        return

    open_count = await bot.db.count_open_tickets(guild.id, interaction.user.id)
    if open_count >= settings.TICKET_MAX_OPEN_PER_USER:
        await interaction.response.send_message(
            embed=error_embed(
                "Too Many Open Tickets",
                f"You already have {open_count} open ticket(s). Please close one before opening another."
            ),
            ephemeral=True,
        )
        return

    staff_role = guild.get_role(settings.TICKET_STAFF_ROLE_ID) if settings.TICKET_STAFF_ROLE_ID else None
    ticket_channel_category = guild.get_channel(settings.TICKET_CATEGORY_ID) if settings.TICKET_CATEGORY_ID else None
    if not isinstance(ticket_channel_category, discord.CategoryChannel):
        ticket_channel_category = None

    overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }
    if guild.me is not None:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True, read_message_history=True
        )
    if staff_role is not None:
        overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    try:
        channel = await guild.create_text_channel(
            name=channel_slug(category.key, interaction.user.name),
            category=ticket_channel_category,
            overwrites=overwrites,
            reason=f"Ticket opened by {interaction.user} ({interaction.user.id})",
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            embed=error_embed("Ticket Failed", "I don't have permission to create channels here."),
            ephemeral=True,
        )
        return

    ticket_id = await bot.db.create_ticket(guild.id, channel.id, interaction.user.id, category.key)

    mention = f"{interaction.user.mention} {staff_role.mention if staff_role else ''}".strip()
    await channel.send(
        content=mention,
        embed=build_ticket_embed(category, interaction.user, answers, ticket_id),
        view=TicketControlView(),
    )

    await interaction.response.send_message(
        embed=success_embed("Ticket Created", f"Your ticket is ready: {channel.mention}"),
        ephemeral=True,
    )

    logger.info("Ticket #%s (%s) opened by %s in guild %s", ticket_id, category.key, interaction.user, guild.id)


async def close_ticket(interaction: discord.Interaction) -> None:
    bot = interaction.client
    ticket = await bot.db.get_ticket_by_channel(interaction.channel_id)

    if ticket is None:
        await interaction.response.send_message(embed=error_embed("Not a Ticket", "This isn't a ticket channel."), ephemeral=True)
        return
    if ticket["status"] != "open":
        await interaction.response.send_message(embed=error_embed("Already Closed", "This ticket is already closed."), ephemeral=True)
        return
    if interaction.user.id != ticket["opener_id"] and not _is_staff(interaction):
        await interaction.response.send_message(
            embed=error_embed("Not Allowed", "Only the ticket opener or staff can close this."),
            ephemeral=True,
        )
        return

    await bot.db.close_ticket(interaction.channel_id, interaction.user.id)

    channel = interaction.channel
    opener = channel.guild.get_member(ticket["opener_id"])
    if opener is not None:
        await channel.set_permissions(
            opener,
            overwrite=discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True),
        )
    if not channel.name.startswith("closed-"):
        try:
            await channel.edit(name=f"closed-{channel.name}"[:100])
        except discord.HTTPException:
            logger.warning("Failed to rename closed ticket channel %s.", channel.id)

    await interaction.response.send_message(embed=success_embed("Ticket Closed", f"Closed by {interaction.user.mention}."))
    logger.info("Ticket #%s closed by %s", ticket["id"], interaction.user)


async def delete_ticket_channel(interaction: discord.Interaction) -> None:
    if not _is_staff(interaction):
        await interaction.response.send_message(embed=error_embed("Not Allowed", "Only staff can delete a ticket channel."), ephemeral=True)
        return

    bot = interaction.client
    ticket = await bot.db.get_ticket_by_channel(interaction.channel_id)
    if ticket is not None and ticket["status"] == "open":
        await interaction.response.send_message(embed=error_embed("Close First", "Close the ticket before deleting the channel."), ephemeral=True)
        return

    await interaction.response.send_message(embed=success_embed("Deleting Channel", "This channel will be deleted shortly."))
    logger.info("Ticket channel %s deleted by %s", interaction.channel_id, interaction.user)
    await interaction.channel.delete(reason=f"Ticket deleted by {interaction.user}")


class TicketModal(discord.ui.Modal):
    def __init__(self, category: TicketCategory):
        super().__init__(title=f"{category.label} Ticket"[:45])
        self.category = category
        self._inputs: list[discord.ui.TextInput] = []
        for field_def in category.fields:
            text_input = discord.ui.TextInput(
                label=field_def.label[:45],
                style=field_def.style,
                required=field_def.required,
                placeholder=field_def.placeholder,
                max_length=field_def.max_length,
            )
            self._inputs.append(text_input)
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction):
        answers = {field_def.label: text_input.value for field_def, text_input in zip(self.category.fields, self._inputs)}
        await create_ticket_channel(interaction, self.category, answers)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.exception("Ticket modal failed", exc_info=error)
        message = error_embed("Ticket Failed", "Something went wrong while opening your ticket.")
        if interaction.response.is_done():
            await interaction.followup.send(embed=message, ephemeral=True)
        else:
            await interaction.response.send_message(embed=message, ephemeral=True)


class TicketCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=category.label, value=category.key, emoji=category.emoji)
            for category in TICKET_CATEGORIES.values()
        ]
        super().__init__(placeholder="Choose a ticket category…", options=options, custom_id="ticket:open_select")

    async def callback(self, interaction: discord.Interaction):
        category = TICKET_CATEGORIES.get(self.values[0])
        if category is None:
            await interaction.response.send_message(embed=error_embed("Unknown Category", "That category no longer exists."), ephemeral=True)
            return
        await interaction.response.send_modal(TicketModal(category))


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect())


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await close_ticket(interaction)

    @discord.ui.button(label="Delete Channel", style=discord.ButtonStyle.grey, emoji="🗑️", custom_id="ticket:delete")
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await delete_ticket_channel(interaction)


class Tickets(commands.Cog):
    """Support ticket system: sign-ups, bug reports, password resets, appeals, and general help."""

    ticket = app_commands.Group(name="ticket", description="Open and manage support tickets.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(TicketPanelView())
        bot.add_view(TicketControlView())

    @ticket.command(name="open", description="Open a support ticket.")
    @app_commands.describe(category="What kind of ticket is this?")
    @app_commands.choices(category=CATEGORY_CHOICES)
    async def open_ticket(self, interaction: discord.Interaction, category: app_commands.Choice[str]):
        await interaction.response.send_modal(TicketModal(TICKET_CATEGORIES[category.value]))

    @ticket.command(name="close", description="Close this ticket.")
    async def close_ticket_command(self, interaction: discord.Interaction):
        await close_ticket(interaction)

    @admin_access()
    @ticket.command(name="panel", description="Post a ticket panel members can use to open tickets.")
    @app_commands.describe(message="Optional message shown above the category picker.")
    async def panel(self, interaction: discord.Interaction, message: str = "Need help? Choose a category below to open a ticket."):
        embed = make_embed("Support Tickets", message, color=discord.Color.blurple())
        embed.add_field(
            name="Categories",
            value="\n".join(f"{category.emoji} **{category.label}**" for category in TICKET_CATEGORIES.values()),
            inline=False,
        )
        await interaction.channel.send(embed=embed, view=TicketPanelView())
        await interaction.response.send_message(embed=success_embed("Panel Posted"), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
