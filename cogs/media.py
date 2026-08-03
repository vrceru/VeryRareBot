"""Media requests: users request a title, staff approve/deny/hold it, and track its
progress toward download. This is Discord-side only -- there's no VRMS API yet, so
status moves forward only when staff click a button. Once VRMS exposes one, the
"downloading"/"completed" transitions here are the natural place to wire it in.
"""

import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from config import settings
from core.checks import has_any_role
from core.embed import error_embed, make_embed, success_embed
from services.tmdb import TMDBClient, TMDBError

logger = logging.getLogger("VeryRareBot")

STATUS_LABELS = {
    "pending": "⏳ Pending Review",
    "on_hold": "⏸️ On Hold",
    "approved": "✅ Approved",
    "downloading": "⬇️ Downloading",
    "completed": "🎉 Completed",
    "denied": "❌ Denied",
    "cancelled": "🚫 Cancelled",
}

STATUS_COLORS = {
    "pending": discord.Color.blurple(),
    "on_hold": discord.Color.orange(),
    "approved": discord.Color.green(),
    "downloading": discord.Color.gold(),
    "completed": discord.Color.dark_green(),
    "denied": discord.Color.red(),
    "cancelled": discord.Color.light_grey(),
}

ACTIVE_STATUSES = ["pending", "on_hold", "approved", "downloading"]

STATUS_FILTER_CHOICES = [app_commands.Choice(name=label, value=key) for key, label in STATUS_LABELS.items()]

STAFF_ROLE_IDS = [
    settings.OWNER_ROLE_ID,
    settings.DEV_OPS_ROLE_ID,
    settings.ADMIN_ROLE_ID,
    settings.STAFF_ROLE_ID,
]

# action -> (new status, statuses it may be applied from)
TRANSITIONS: dict[str, tuple[str, set[str]]] = {
    "approve": ("approved", {"pending", "on_hold"}),
    "deny": ("denied", {"pending", "on_hold", "approved"}),
    "hold": ("on_hold", {"pending"}),
    "downloading": ("downloading", {"approved"}),
    "completed": ("completed", {"downloading"}),
}


def _is_staff(interaction: discord.Interaction) -> bool:
    return has_any_role(interaction, STAFF_ROLE_IDS)


def build_request_embed(request) -> discord.Embed:
    title = f"{request['title']} ({request['year']})" if request["year"] else request["title"]
    color = STATUS_COLORS.get(request["status"], discord.Color.blurple())
    embed = make_embed(title, request["overview"], color=color)
    embed.add_field(name="Type", value="Movie" if request["media_type"] == "movie" else "TV Show", inline=True)
    embed.add_field(name="Status", value=STATUS_LABELS.get(request["status"], request["status"]), inline=True)
    embed.add_field(name="Requested By", value=f"<@{request['requester_id']}>", inline=True)
    if request["notes"]:
        embed.add_field(name="Notes", value=request["notes"], inline=False)
    if request["reviewer_id"]:
        embed.add_field(name="Reviewed By", value=f"<@{request['reviewer_id']}>", inline=True)
    if request["poster_url"]:
        embed.set_thumbnail(url=request["poster_url"])
    embed.set_footer(text=f"Request #{request['id']} • TMDB {request['tmdb_id']}")
    return embed


def build_status_view(request_id: int, status: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    if status == "pending":
        view.add_item(MediaActionButton("approve", request_id, label="Approve", style=discord.ButtonStyle.success, emoji="✅"))
        view.add_item(MediaActionButton("deny", request_id, label="Deny", style=discord.ButtonStyle.danger, emoji="❌"))
        view.add_item(MediaActionButton("hold", request_id, label="Hold", style=discord.ButtonStyle.secondary, emoji="⏸️"))
    elif status == "on_hold":
        view.add_item(MediaActionButton("approve", request_id, label="Approve", style=discord.ButtonStyle.success, emoji="✅"))
        view.add_item(MediaActionButton("deny", request_id, label="Deny", style=discord.ButtonStyle.danger, emoji="❌"))
    elif status == "approved":
        view.add_item(
            MediaActionButton("downloading", request_id, label="Mark Downloading", style=discord.ButtonStyle.primary, emoji="⬇️")
        )
        view.add_item(MediaActionButton("deny", request_id, label="Cancel", style=discord.ButtonStyle.danger, emoji="❌"))
    elif status == "downloading":
        view.add_item(
            MediaActionButton("completed", request_id, label="Mark Completed", style=discord.ButtonStyle.success, emoji="🎉")
        )
    return view


async def apply_media_action(interaction: discord.Interaction, action: str, request_id: int) -> None:
    bot = interaction.client
    request = await bot.db.get_media_request(request_id)

    if request is None:
        await interaction.response.send_message(embed=error_embed("Not Found", "This request no longer exists."), ephemeral=True)
        return
    if not _is_staff(interaction):
        await interaction.response.send_message(embed=error_embed("Not Allowed", "Only staff can update media requests."), ephemeral=True)
        return

    new_status, allowed_from = TRANSITIONS[action]
    if request["status"] not in allowed_from:
        await interaction.response.send_message(
            embed=error_embed("Invalid Transition", f"This request is already **{STATUS_LABELS.get(request['status'], request['status'])}**."),
            ephemeral=True,
        )
        return

    await bot.db.update_media_request_status(request_id, new_status, reviewer_id=interaction.user.id)
    updated = await bot.db.get_media_request(request_id)

    await interaction.response.edit_message(embed=build_request_embed(updated), view=build_status_view(request_id, new_status))
    logger.info("Media request #%s -> %s by %s", request_id, new_status, interaction.user)

    if new_status in {"approved", "denied", "completed"} and interaction.guild is not None:
        requester = interaction.guild.get_member(request["requester_id"])
        if requester is not None:
            try:
                await requester.send(
                    embed=make_embed(
                        f"Your request for {updated['title']} is now {STATUS_LABELS.get(new_status, new_status)}",
                        color=STATUS_COLORS.get(new_status),
                    )
                )
            except discord.HTTPException:
                pass


class MediaActionButton(discord.ui.DynamicItem[discord.ui.Button], template=r"media:(?P<action>[a-z]+):(?P<request_id>\d+)"):
    """A staff review button whose target request is encoded in its custom_id, so it
    keeps working after a restart without registering one view per request."""

    def __init__(self, action: str, request_id: int, *, label: str, style: discord.ButtonStyle, emoji: str):
        super().__init__(
            discord.ui.Button(label=label, style=style, emoji=emoji, custom_id=f"media:{action}:{request_id}")
        )
        self.action = action
        self.request_id = request_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]):
        return cls(
            action=match["action"],
            request_id=int(match["request_id"]),
            label=item.label,
            style=item.style,
            emoji=item.emoji,
        )

    async def callback(self, interaction: discord.Interaction):
        await apply_media_action(interaction, self.action, self.request_id)


class QueueBrowserView(discord.ui.View):
    """Lets the invoker flip through queued requests one card at a time."""

    def __init__(self, requests: list, index: int = 0):
        super().__init__(timeout=180)
        self.requests = requests
        self.index = index
        self._sync_buttons()

    def _sync_buttons(self):
        self.previous_button.disabled = self.index <= 0
        self.next_button.disabled = self.index >= len(self.requests) - 1

    def current_embed(self) -> discord.Embed:
        embed = build_request_embed(self.requests[self.index])
        embed.set_footer(text=f"{embed.footer.text} • {self.index + 1} of {len(self.requests)}")
        return embed

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index -= 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index += 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.current_embed(), view=self)


class Media(commands.Cog):
    """Community media requests, backed by TMDB search and a staff approval workflow."""

    media = app_commands.Group(name="media", description="Request and track media.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_dynamic_items(MediaActionButton)

    @media.command(name="request", description="Request a movie or TV show.")
    @app_commands.describe(title="Start typing a title, then pick a suggestion.", notes="Anything staff should know (optional).")
    async def request(self, interaction: discord.Interaction, title: str, notes: str | None = None):
        if interaction.guild is None:
            await interaction.response.send_message(embed=error_embed("Server Only", "Media can only be requested in a server."), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            client = TMDBClient.from_settings()
        except TMDBError as exc:
            await interaction.followup.send(embed=error_embed("Media Requests Unavailable", str(exc)))
            return

        match = re.fullmatch(r"(movie|tv):(\d+)", title)
        try:
            if match:
                result = await client.get_details(match.group(1), int(match.group(2)))
            else:
                results = await client.search_multi(title, limit=1)
                if not results:
                    await interaction.followup.send(
                        embed=error_embed("Not Found", f"No results for **{title}**. Try again and pick a suggestion as you type.")
                    )
                    return
                result = results[0]
        except TMDBError as exc:
            await interaction.followup.send(embed=error_embed("TMDB Error", str(exc)))
            return

        existing = await self.bot.db.get_active_media_request(interaction.guild_id, result.tmdb_id, result.media_type)
        if existing is not None:
            await interaction.followup.send(
                embed=error_embed(
                    "Already Requested",
                    f"**{result.title}** is already requested (status: {STATUS_LABELS.get(existing['status'], existing['status'])})."
                )
            )
            return

        request_id = await self.bot.db.create_media_request(
            interaction.guild_id,
            interaction.user.id,
            result.media_type,
            result.tmdb_id,
            result.title,
            result.year,
            result.poster_url,
            result.overview,
            notes,
        )
        request_row = await self.bot.db.get_media_request(request_id)

        channel = self.bot.get_channel(settings.MEDIA_REQUEST_CHANNEL_ID) if settings.MEDIA_REQUEST_CHANNEL_ID else interaction.channel
        message = await channel.send(embed=build_request_embed(request_row), view=build_status_view(request_id, "pending"))
        await self.bot.db.set_media_request_message(request_id, channel.id, message.id)

        await interaction.followup.send(embed=success_embed("Request Submitted", f"Your request for **{result.title}** has been sent for review."))
        logger.info("Media request #%s (%s:%s) opened by %s", request_id, result.media_type, result.tmdb_id, interaction.user)

    @request.autocomplete("title")
    async def title_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if len(current) < 2 or not settings.TMDB_API_KEY:
            return []
        try:
            client = TMDBClient.from_settings()
            results = await client.search_multi(current, limit=20)
        except TMDBError:
            return []

        choices = []
        for result in results:
            label = f"{result.title} ({result.year})" if result.year else result.title
            label = f"{label} · {'Movie' if result.media_type == 'movie' else 'TV'}"
            choices.append(app_commands.Choice(name=label[:100], value=f"{result.media_type}:{result.tmdb_id}"))
        return choices[:25]

    @media.command(name="queue", description="Browse the media request queue.")
    @app_commands.describe(status="Filter by status. Defaults to active requests.")
    @app_commands.choices(status=STATUS_FILTER_CHOICES)
    async def queue(self, interaction: discord.Interaction, status: app_commands.Choice[str] | None = None):
        statuses = [status.value] if status else ACTIVE_STATUSES
        requests = await self.bot.db.list_media_requests(interaction.guild_id, statuses, limit=50)
        if not requests:
            await interaction.response.send_message(embed=error_embed("Queue Empty", "No requests match that filter."), ephemeral=True)
            return

        view = QueueBrowserView(requests)
        await interaction.response.send_message(embed=view.current_embed(), view=view, ephemeral=True)

    @media.command(name="myrequests", description="List your media requests.")
    async def my_requests(self, interaction: discord.Interaction):
        rows = await self.bot.db.list_user_media_requests(interaction.guild_id, interaction.user.id)
        if not rows:
            await interaction.response.send_message(embed=error_embed("No Requests", "You haven't requested anything yet."), ephemeral=True)
            return

        embed = make_embed("Your Media Requests")
        for row in rows[:15]:
            label = f"{row['title']} ({row['year']})" if row["year"] else row["title"]
            embed.add_field(name=f"#{row['id']} {label}", value=STATUS_LABELS.get(row["status"], row["status"]), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @media.command(name="cancel", description="Cancel a media request.")
    @app_commands.describe(request_id="The request # shown on its card or in /media myrequests.")
    async def cancel(self, interaction: discord.Interaction, request_id: int):
        request = await self.bot.db.get_media_request(request_id)
        if request is None:
            await interaction.response.send_message(embed=error_embed("Not Found", "That request doesn't exist."), ephemeral=True)
            return
        if request["requester_id"] != interaction.user.id and not _is_staff(interaction):
            await interaction.response.send_message(
                embed=error_embed("Not Allowed", "Only the requester or staff can cancel this."), ephemeral=True
            )
            return
        if request["status"] in {"completed", "denied", "cancelled"}:
            await interaction.response.send_message(
                embed=error_embed("Already Final", f"This request is already **{STATUS_LABELS.get(request['status'])}**."), ephemeral=True
            )
            return

        await self.bot.db.update_media_request_status(request_id, "cancelled", reviewer_id=interaction.user.id)
        updated = await self.bot.db.get_media_request(request_id)

        if request["card_channel_id"] and request["card_message_id"]:
            channel = self.bot.get_channel(request["card_channel_id"])
            if channel is not None:
                try:
                    message = await channel.fetch_message(request["card_message_id"])
                    await message.edit(embed=build_request_embed(updated), view=None)
                except discord.HTTPException:
                    logger.warning("Failed to update the card for cancelled media request #%s.", request_id)

        await interaction.response.send_message(embed=success_embed("Request Cancelled"), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Media(bot))
