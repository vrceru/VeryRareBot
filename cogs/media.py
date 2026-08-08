"""Media requests: users request a title, staff approve/deny/hold it, and VRMS (once
configured) takes it from "approved" through download to the library, pausing at its
own two admin-approval gates along the way. See docs/current/VRMS_INTEGRATION.md for
the full design. Without VRMS_API_URL configured, this cog still works exactly as
before: staff manually mark things "downloading"/"completed" by hand.
"""

import logging
import re

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import settings
from core.checks import has_any_role, staff_access
from core.embed import error_embed, make_embed, success_embed
from services.tmdb import TMDBClient, TMDBError
from services.vrms_api import VRMSAPIClient, VRMSAPIError

logger = logging.getLogger("VeryRareBot")

STATUS_LABELS = {
    "pending": "⏳ Pending Review",
    "on_hold": "⏸️ On Hold",
    "approved": "✅ Approved",
    "downloading": "⬇️ Downloading",
    "completed": "🎉 Completed",
    "denied": "❌ Denied",
    "cancelled": "🚫 Cancelled",
    "failed": "💥 Failed",
}

STATUS_COLORS = {
    "pending": discord.Color.blurple(),
    "on_hold": discord.Color.orange(),
    "approved": discord.Color.green(),
    "downloading": discord.Color.gold(),
    "completed": discord.Color.dark_green(),
    "denied": discord.Color.red(),
    "cancelled": discord.Color.light_grey(),
    "failed": discord.Color.dark_red(),
}

ACTIVE_STATUSES = ["pending", "on_hold", "approved", "downloading"]
TERMINAL_STATUSES = {"completed", "denied", "cancelled", "failed"}
GATE_COLOR = discord.Color.gold()

# VRMS pipeline stage machine-name -> a label admins can actually read on the request card.
VRMS_STAGE_LABELS = {
    "validate_request": "Validating request",
    "search_providers": "Searching providers",
    "select_release": "Selecting release",
    "await_release_approval": "Awaiting release approval",
    "download": "Downloading",
    "verify_download": "Verifying download",
    "virus_scan": "Scanning for viruses",
    "extract_archive": "Extracting archive",
    "validate_media": "Validating media",
    "identify_media": "Identifying media type",
    "fetch_metadata": "Fetching metadata",
    "await_final_approval": "Awaiting final approval",
    "rename_files": "Renaming files",
    "organize_library": "Organizing library",
    "generate_artwork": "Generating artwork",
    "update_jellyfin": "Updating Jellyfin",
    "send_notifications": "Sending notifications",
    "log_completion": "Finishing up",
    "archive_history": "Archiving",
}


def _progress_bar(fraction: float, length: int = 14) -> str:
    fraction = max(0.0, min(1.0, fraction))
    filled = round(fraction * length)
    return "▓" * filled + "░" * (length - filled)

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
    if request["media_type"] == "movie":
        type_label = "Movie"
    elif request["is_anime"]:
        type_label = "Anime"
    else:
        type_label = "TV Show"
    embed.add_field(name="Type", value=type_label, inline=True)
    embed.add_field(name="Status", value=STATUS_LABELS.get(request["status"], request["status"]), inline=True)
    embed.add_field(name="Requested By", value=f"<@{request['requester_id']}>", inline=True)
    if request["status"] == "downloading" and request["vrms_progress"] is not None:
        pct = round(request["vrms_progress"] * 100)
        stage_label = VRMS_STAGE_LABELS.get(request["vrms_stage"], request["vrms_stage"] or "Working")
        bar = _progress_bar(request["vrms_progress"])
        embed.add_field(name="Progress", value=f"`{bar}` {pct}%\n{stage_label}", inline=False)
    if request["notes"]:
        embed.add_field(name="Notes", value=request["notes"], inline=False)
    if request["reviewer_id"]:
        embed.add_field(name="Reviewed By", value=f"<@{request['reviewer_id']}>", inline=True)
    if request["poster_url"]:
        embed.set_thumbnail(url=request["poster_url"])
    embed.set_footer(text=f"Request #{request['id']} • TMDB {request['tmdb_id']}")
    return embed


def build_status_view(request) -> discord.ui.View:
    request_id = request["id"]
    status = request["status"]
    has_vrms_job = bool(request["vrms_job_id"])

    view = discord.ui.View(timeout=None)
    if status == "pending":
        view.add_item(MediaActionButton("approve", request_id, label="Approve", style=discord.ButtonStyle.success, emoji="✅"))
        view.add_item(MediaActionButton("deny", request_id, label="Deny", style=discord.ButtonStyle.danger, emoji="❌"))
        view.add_item(MediaActionButton("hold", request_id, label="Hold", style=discord.ButtonStyle.secondary, emoji="⏸️"))
    elif status == "on_hold":
        view.add_item(MediaActionButton("approve", request_id, label="Approve", style=discord.ButtonStyle.success, emoji="✅"))
        view.add_item(MediaActionButton("deny", request_id, label="Deny", style=discord.ButtonStyle.danger, emoji="❌"))
    elif status == "approved":
        # With a VRMS job attached, the polling loop advances this automatically once VRMS
        # actually starts working -- the manual button is only needed as a fallback when VRMS
        # isn't configured, or its enqueue call failed.
        if not has_vrms_job:
            view.add_item(
                MediaActionButton("downloading", request_id, label="Mark Downloading", style=discord.ButtonStyle.primary, emoji="⬇️")
            )
        view.add_item(MediaActionButton("deny", request_id, label="Cancel", style=discord.ButtonStyle.danger, emoji="❌"))
    elif status == "downloading":
        if not has_vrms_job:
            view.add_item(
                MediaActionButton("completed", request_id, label="Mark Completed", style=discord.ButtonStyle.success, emoji="🎉")
            )
    return view


async def _apply_status(bot, request_id: int, new_status: str, reviewer_id: int | None = None):
    """Update a request's status in the DB and return the fresh row."""
    await bot.db.update_media_request_status(request_id, new_status, reviewer_id=reviewer_id)
    return await bot.db.get_media_request(request_id)


async def _notify_requester(bot, request, new_status: str) -> None:
    if new_status not in {"approved", "denied", "completed", "failed"}:
        return
    guild = bot.get_guild(request["guild_id"])
    requester = guild.get_member(request["requester_id"]) if guild else None
    if requester is None:
        return
    try:
        await requester.send(
            embed=make_embed(
                f"Your request for {request['title']} is now {STATUS_LABELS.get(new_status, new_status)}",
                color=STATUS_COLORS.get(new_status),
            )
        )
    except discord.HTTPException:
        pass


async def _refresh_request_card(bot, request) -> None:
    """Edit the main request card from outside an interaction context (the VRMS polling loop)."""
    if not (request["card_channel_id"] and request["card_message_id"]):
        return
    channel = bot.get_channel(request["card_channel_id"])
    if channel is None:
        return
    try:
        message = await channel.fetch_message(request["card_message_id"])
        await message.edit(embed=build_request_embed(request), view=build_status_view(request))
    except discord.HTTPException:
        logger.warning("Failed to refresh the card for media request #%s.", request["id"])


async def _start_vrms_job_if_configured(bot, request) -> tuple[dict, str | None]:
    """On approve, try to start the request as a VRMS job. Returns (possibly-updated request,
    an error note to show staff if the call failed). VRMS being unconfigured is not an error --
    the request just stays on the manual fallback path."""
    try:
        client = VRMSAPIClient.from_settings()
    except VRMSAPIError:
        return request, None

    if request["is_anime"]:
        media_type = "anime"
    elif request["media_type"] == "tv":
        media_type = "show"
    else:
        media_type = request["media_type"]
    try:
        job = await client.enqueue(
            request["title"],
            media_type,
            year=int(request["year"]) if request["year"] else None,
            # metadataId is a TMDB id -- only meaningful for the movie/tmdb-tv metadata
            # providers. VRMS resolves anime through AniList instead, so passing it there
            # would be a guaranteed-wrong direct lookup; let fetchMetadata fall back to an
            # AniList title/year search.
            metadata_id=None if media_type == "anime" else str(request["tmdb_id"]),
        )
    except VRMSAPIError as exc:
        logger.warning("VRMS enqueue failed for media request #%s: %s", request["id"], exc)
        return request, f"Approved locally, but starting it in VRMS failed: {exc}"

    await bot.db.set_media_request_vrms_job(request["id"], job["id"])
    updated = await bot.db.get_media_request(request["id"])
    return updated, None


async def submit_media_request(
    bot, guild_id: int, user: discord.abc.User, title: str, notes: str | None, fallback_channel: discord.abc.Messageable | None
) -> discord.Embed:
    """Resolves a title via TMDB, creates the request, and posts its card. Returns the embed to
    show the requester (success or a specific failure) -- shared by /media request and the
    panel's modal so both entry points behave identically."""
    try:
        client = TMDBClient.from_settings()
    except TMDBError as exc:
        return error_embed("Media Requests Unavailable", str(exc))

    match = re.fullmatch(r"(movie|tv):(\d+)", title)
    try:
        if match:
            result = await client.get_details(match.group(1), int(match.group(2)))
        else:
            results = await client.search_multi(title, limit=1)
            if not results:
                return error_embed("Not Found", f"No results for **{title}**. Try again and pick a suggestion as you type.")
            result = results[0]
    except TMDBError as exc:
        return error_embed("TMDB Error", str(exc))

    existing = await bot.db.get_active_media_request(guild_id, result.tmdb_id, result.media_type)
    if existing is not None:
        return error_embed(
            "Already Requested",
            f"**{result.title}** is already requested (status: {STATUS_LABELS.get(existing['status'], existing['status'])})."
        )

    request_id = await bot.db.create_media_request(
        guild_id,
        user.id,
        result.media_type,
        result.tmdb_id,
        result.title,
        result.year,
        result.poster_url,
        result.overview,
        notes,
        is_anime=result.is_anime,
    )
    request_row = await bot.db.get_media_request(request_id)

    # The staff review card (with Approve/Deny/Hold) goes to the dedicated queue channel when
    # configured -- deliberately not wherever the request came from, so a public request panel
    # and a staff-only approval queue can be different channels.
    queue_channel_id = settings.MEDIA_QUE_CHANNEL_ID or settings.MEDIA_REQUEST_CHANNEL_ID
    channel = bot.get_channel(queue_channel_id) if queue_channel_id else fallback_channel
    if channel is None:
        return error_embed("Configuration Error", "No media queue channel is configured and this channel isn't usable either.")
    message = await channel.send(embed=build_request_embed(request_row), view=build_status_view(request_row))
    await bot.db.set_media_request_message(request_id, channel.id, message.id)

    logger.info("Media request #%s (%s:%s) opened by %s", request_id, result.media_type, result.tmdb_id, user)
    return success_embed("Request Submitted", f"Your request for **{result.title}** has been sent for review.")


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

    updated = await _apply_status(bot, request_id, new_status, reviewer_id=interaction.user.id)

    vrms_note = None
    if action == "approve":
        updated, vrms_note = await _start_vrms_job_if_configured(bot, updated)

    await interaction.response.edit_message(embed=build_request_embed(updated), view=build_status_view(updated))
    logger.info("Media request #%s -> %s by %s", request_id, new_status, interaction.user)

    await _notify_requester(bot, updated, new_status)

    if vrms_note:
        await interaction.followup.send(embed=error_embed("VRMS Not Started", vrms_note), ephemeral=True)


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


def _find_top_release_candidate(release_entry: dict | None) -> dict | None:
    if not release_entry:
        return None
    candidates = release_entry.get("candidates") or []
    auto_id = release_entry.get("autoSelectedId")
    for candidate in candidates:
        if candidate.get("id") == auto_id:
            return candidate
    return candidates[0] if candidates else None


def build_release_gate_embed(title: str, candidate: dict | None, candidate_count: int = 0) -> discord.Embed:
    embed = make_embed("VRMS: Approve Release?", title, color=GATE_COLOR)
    if candidate is None:
        embed.add_field(name="Candidates", value="No candidate releases were found.", inline=False)
    else:
        parsed = candidate.get("parsed") or {}
        embed.add_field(name="Auto-Selected Release", value=(candidate.get("title") or "Unknown")[:1024], inline=False)
        if parsed.get("season") is not None:
            embed.add_field(name="Season", value=str(parsed["season"]), inline=True)
        if parsed.get("resolution"):
            embed.add_field(name="Resolution", value=parsed["resolution"], inline=True)
        if parsed.get("source"):
            embed.add_field(name="Source", value=parsed["source"], inline=True)
        if candidate.get("seeders") is not None:
            embed.add_field(name="Seeders", value=str(candidate["seeders"]), inline=True)
    if candidate_count > 1:
        embed.set_footer(text=f"{candidate_count} releases found — approve VRMS's pick, or use the dropdown below to choose a different one (e.g. another season).")
    else:
        embed.set_footer(text="Approving keeps VRMS's auto-selected release.")
    return embed


def build_final_gate_embed(title: str, entry: dict) -> discord.Embed:
    metadata = entry.get("metadata") or {}
    storage = entry.get("storage") or {}
    embed = make_embed("VRMS: Approve Final Copy?", metadata.get("overview"), color=GATE_COLOR)
    matched_title = metadata.get("title") or title
    year = metadata.get("year")
    embed.add_field(name="Matched Title", value=f"{matched_title} ({year})" if year else matched_title, inline=False)
    if metadata.get("posterUrl"):
        embed.set_thumbnail(url=metadata["posterUrl"])
    if "hasEnoughSpace" in storage:
        embed.add_field(name="Storage", value="✅ Enough space" if storage["hasEnoughSpace"] else "⚠️ Not enough space", inline=True)
    elif storage.get("error"):
        embed.add_field(name="Storage Check", value=f"⚠️ {storage['error']}", inline=True)
    embed.set_footer(text="Approving moves the file into the library and updates Jellyfin.")
    return embed


def build_gate_view(
    gate: str,
    request_id: int,
    candidates: list[dict] | None = None,
    auto_selected_id: str | None = None,
    expected_year: int | None = None,
) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    if gate == "release" and candidates and len(candidates) > 1:
        groups = _group_candidates_by_season(candidates)
        if len(groups) > 1:
            view.add_item(SeasonPickerSelect(request_id, groups, auto_selected_id, expected_year=expected_year))
        else:
            only_key = next(iter(groups))
            view.add_item(ReleaseWithinSeasonSelect(request_id, groups[only_key], auto_selected_id, expected_year))
    view.add_item(VRMSGateButton(gate, "approve", request_id, label="Approve", style=discord.ButtonStyle.success, emoji="✅"))
    view.add_item(VRMSGateButton(gate, "deny", request_id, label="Deny", style=discord.ButtonStyle.danger, emoji="❌"))
    return view


async def apply_vrms_gate_action(
    interaction: discord.Interaction, gate: str, action: str, request_id: int, candidate_id: str | None = None
) -> None:
    bot = interaction.client
    request = await bot.db.get_media_request(request_id)

    if request is None or not request["vrms_job_id"]:
        await interaction.response.send_message(embed=error_embed("Not Found", "This VRMS job no longer exists."), ephemeral=True)
        return
    if not _is_staff(interaction):
        await interaction.response.send_message(embed=error_embed("Not Allowed", "Only staff can approve VRMS gates."), ephemeral=True)
        return

    try:
        client = VRMSAPIClient.from_settings()
    except VRMSAPIError as exc:
        await interaction.response.send_message(embed=error_embed("VRMS Unavailable", str(exc)), ephemeral=True)
        return

    try:
        if gate == "release":
            if action == "approve":
                await client.approve_release(request["vrms_job_id"], candidate_id)
            else:
                await client.deny_release(request["vrms_job_id"])
        else:
            await (client.approve_final(request["vrms_job_id"]) if action == "approve" else client.deny_final(request["vrms_job_id"]))
    except VRMSAPIError as exc:
        await interaction.response.send_message(embed=error_embed("VRMS Error", str(exc)), ephemeral=True)
        return

    await bot.db.clear_media_request_gate_message(request_id)
    logger.info("VRMS %s gate %s for media request #%s by %s", gate, action, request_id, interaction.user)

    if action == "deny":
        # Denying a gate cancels the whole VRMS job -- reflect that on the main request card too.
        updated = await _apply_status(bot, request_id, "denied", reviewer_id=interaction.user.id)
        await _refresh_request_card(bot, updated)
        await _notify_requester(bot, updated, "denied")

    await interaction.response.edit_message(
        embed=make_embed(
            "Gate Resolved",
            f"{'Approved' if action == 'approve' else 'Denied'} — see the main request card for status.",
            color=discord.Color.light_grey(),
        ),
        view=None,
    )


class VRMSGateButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"vrms_gate:(?P<gate>release|final):(?P<action>approve|deny):(?P<request_id>\d+)",
):
    """Approve/Deny buttons for VRMS's two admin-approval gates. Separate custom_id template
    from MediaActionButton's so the two dynamic item types never collide."""

    def __init__(self, gate: str, action: str, request_id: int, *, label: str, style: discord.ButtonStyle, emoji: str):
        super().__init__(
            discord.ui.Button(label=label, style=style, emoji=emoji, custom_id=f"vrms_gate:{gate}:{action}:{request_id}")
        )
        self.gate = gate
        self.action = action
        self.request_id = request_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]):
        return cls(
            gate=match["gate"],
            action=match["action"],
            request_id=int(match["request_id"]),
            label=item.label,
            style=item.style,
            emoji=item.emoji,
        )

    async def callback(self, interaction: discord.Interaction):
        await apply_vrms_gate_action(interaction, self.gate, self.action, self.request_id)


def _candidate_season(candidate: dict) -> int | None:
    return (candidate.get("parsed") or {}).get("season")


def _group_candidates_by_season(candidates: list[dict]) -> dict[int | None, list[dict]]:
    """Groups candidates by parsed season, each group sorted best-seeders-first. Entries with
    no parsed season (movies, specials, unparseable titles) land under the `None` key."""
    groups: dict[int | None, list[dict]] = {}
    for candidate in candidates:
        groups.setdefault(_candidate_season(candidate), []).append(candidate)
    for group in groups.values():
        group.sort(key=lambda c: c.get("seeders") or 0, reverse=True)
    return groups


def _ordered_season_keys(groups: dict[int | None, list[dict]]) -> list[int | None]:
    keys = sorted(k for k in groups if k is not None)
    if None in groups:
        keys.append(None)
    return keys


def _season_option_label(season_key: int | None, count: int) -> str:
    name = f"Season {season_key:02d}" if season_key is not None else "Unspecified / Movie"
    return f"{name} ({count} release{'s' if count != 1 else ''})"


def _within_season_option_text(candidate: dict, expected_year: int | None = None) -> tuple[str, str]:
    """Builds (label, description) for a release *within* an already-chosen season -- leads
    with quality info since season is no longer the thing being scanned for, and pushes the raw
    (often long, noisy) release title down into the description as a secondary reference.

    Always surfaces the release's own parsed year, and flags it with a warning when it doesn't
    match what was actually requested: confirmed in production that a search for "The Maze
    Runner" (2014) can return a completely different film in the same franchise (e.g. "...The
    Death Cure" 2018) as a plausible-looking candidate, and with only quality info in the label
    that mismatch was invisible until staff already approved it."""
    parsed = candidate.get("parsed") or {}
    bits = []
    if parsed.get("year") is not None:
        bits.append(str(parsed["year"]))
    if parsed.get("resolution"):
        bits.append(parsed["resolution"])
    if parsed.get("source"):
        bits.append(parsed["source"])
    if candidate.get("seeders") is not None:
        bits.append(f"{candidate['seeders']} seeders")
    label = " • ".join(bits) if bits else "Release"

    parsed_year = parsed.get("year")
    if expected_year is not None and parsed_year is not None and int(parsed_year) != expected_year:
        label = f"⚠️ {label} (expected {expected_year})"

    description = (candidate.get("title") or "Unknown")[:100]
    return label[:100], description


class ReleaseWithinSeasonSelect(discord.ui.Select):
    """Step 2 of the release picker: choose a specific release within the season picked in step
    1 (or the only season/season-less pool, when there's nothing to disambiguate at that level).
    Unlike VRMSGateButton this isn't restart-persistent -- a bot restart before staff picks one
    just means the dropdown goes dead, while the Approve/Deny buttons alongside it (which keep
    VRMS's own auto-pick) still work as the reliable fallback."""

    def __init__(self, request_id: int, candidates: list[dict], auto_selected_id: str | None, expected_year: int | None = None):
        self.request_id = request_id
        self.candidates = candidates[:25]
        options = []
        for i, candidate in enumerate(self.candidates):
            label, description = _within_season_option_text(candidate, expected_year)
            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(i),
                    description=description,
                    default=candidate.get("id") == auto_selected_id,
                )
            )
        super().__init__(placeholder="Pick a release…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        chosen = self.candidates[int(self.values[0])]
        await apply_vrms_gate_action(interaction, "release", "approve", self.request_id, candidate_id=chosen["id"])


class SeasonPickerSelect(discord.ui.Select):
    """Step 1 of the release picker: choose a season. Picking one edits the message in place to
    add a ReleaseWithinSeasonSelect scoped to just that season, alongside this same season
    picker (so a different season can still be picked without starting over) and the existing
    Approve/Deny buttons."""

    def __init__(
        self,
        request_id: int,
        groups: dict[int | None, list[dict]],
        auto_selected_id: str | None,
        selected_key: int | None = None,
        expected_year: int | None = None,
    ):
        self.request_id = request_id
        self.groups = groups
        self.auto_selected_id = auto_selected_id
        self.expected_year = expected_year
        options = [
            discord.SelectOption(
                label=_season_option_label(key, len(groups[key])),
                value=str(key) if key is not None else "none",
                default=key == selected_key,
            )
            for key in _ordered_season_keys(groups)
        ]
        super().__init__(placeholder="Step 1: pick a season…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        chosen_key = None if self.values[0] == "none" else int(self.values[0])
        view = discord.ui.View(timeout=None)
        view.add_item(
            SeasonPickerSelect(
                self.request_id, self.groups, self.auto_selected_id, selected_key=chosen_key, expected_year=self.expected_year
            )
        )
        view.add_item(
            ReleaseWithinSeasonSelect(self.request_id, self.groups[chosen_key], self.auto_selected_id, self.expected_year)
        )
        view.add_item(
            VRMSGateButton("release", "approve", self.request_id, label="Approve", style=discord.ButtonStyle.success, emoji="✅")
        )
        view.add_item(
            VRMSGateButton("release", "deny", self.request_id, label="Deny", style=discord.ButtonStyle.danger, emoji="❌")
        )
        await interaction.response.edit_message(view=view)


class MediaRequestModal(discord.ui.Modal):
    """Free-text title entry for the panel button -- unlike the /media request slash command,
    a modal has no autocomplete, so this always goes through submit_media_request's plain-title
    search fallback (same path a slash-command user hits if they type a full title and never
    pick a suggestion)."""

    def __init__(self):
        super().__init__(title="Request Media")
        self.title_input = discord.ui.TextInput(label="Title", placeholder="e.g. The Matrix, or Attack on Titan", max_length=200)
        self.notes_input = discord.ui.TextInput(
            label="Anything staff should know?", style=discord.TextStyle.paragraph, required=False, max_length=500
        )
        self.add_item(self.title_input)
        self.add_item(self.notes_input)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(embed=error_embed("Server Only", "Media can only be requested in a server."), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        embed = await submit_media_request(
            interaction.client, interaction.guild_id, interaction.user, self.title_input.value, self.notes_input.value or None, interaction.channel
        )
        await interaction.followup.send(embed=embed)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.exception("Media request modal failed", exc_info=error)
        message = error_embed("Request Failed", "Something went wrong while submitting your request.")
        if interaction.response.is_done():
            await interaction.followup.send(embed=message, ephemeral=True)
        else:
            await interaction.response.send_message(embed=message, ephemeral=True)


class MediaPanelView(discord.ui.View):
    """Persistent panel posted by /media panel -- lets members request a title without typing
    the slash command."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request Media", style=discord.ButtonStyle.success, emoji="🎬", custom_id="media:open_panel")
    async def request_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MediaRequestModal())


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
        bot.add_dynamic_items(MediaActionButton, VRMSGateButton)
        bot.add_view(MediaPanelView())

        if settings.VRMS_API_URL:
            self.vrms_job_watch.change_interval(seconds=max(settings.VRMS_JOB_POLL_SECONDS, 15))
            self.vrms_job_watch.start()

    async def cog_unload(self) -> None:
        self.vrms_job_watch.cancel()

    @tasks.loop(seconds=30)
    async def vrms_job_watch(self):
        try:
            client = VRMSAPIClient.from_settings()
        except VRMSAPIError:
            return

        rows = await self.bot.db.list_media_requests_with_vrms_job()
        for row in rows:
            try:
                job = await client.get_job(row["vrms_job_id"])
            except VRMSAPIError as exc:
                logger.debug("VRMS job poll failed for request #%s: %s", row["id"], exc)
                continue
            try:
                await self._handle_vrms_job_update(row, job, client)
            except Exception:
                logger.exception("Failed to process a VRMS job update for request #%s", row["id"])

    @vrms_job_watch.before_loop
    async def before_vrms_job_watch(self):
        await self.bot.wait_until_ready()

    async def _handle_vrms_job_update(self, row, job: dict, client: VRMSAPIClient) -> None:
        bot = self.bot
        status = job.get("status")
        request_id = row["id"]

        if status == "completed":
            await self._clear_vrms_gate(row)
            updated = await _apply_status(bot, request_id, "completed")
            await _refresh_request_card(bot, updated)
            await _notify_requester(bot, updated, "completed")
            return

        if status in ("failed", "cancelled"):
            await self._clear_vrms_gate(row)
            updated = await _apply_status(bot, request_id, "failed")
            await _refresh_request_card(bot, updated)
            await _notify_requester(bot, updated, "failed")
            return

        if status == "awaiting_release_approval":
            await self._ensure_vrms_gate_card(row, "release", client)
            return

        if status == "awaiting_final_approval":
            await self._ensure_vrms_gate_card(row, "final", client)
            return

        # pending/running/paused: actively progressing, or waiting to retry after a transient
        # failure. Clear a leftover gate card if the job has since moved past it.
        if row["vrms_gate_message_id"]:
            await self._clear_vrms_gate(row)

        progress = job.get("progress")
        stage = job.get("stage")
        progress_changed = progress != row["vrms_progress"] or stage != row["vrms_stage"]
        if progress_changed:
            await bot.db.set_media_request_progress(request_id, progress, stage)
            row = await bot.db.get_media_request(request_id)

        if status == "running" and row["status"] == "approved":
            updated = await _apply_status(bot, request_id, "downloading")
            await _refresh_request_card(bot, updated)
        elif row["status"] == "downloading" and progress_changed:
            await _refresh_request_card(bot, row)

    async def _ensure_vrms_gate_card(self, row, gate: str, client: VRMSAPIClient) -> None:
        if row["vrms_gate_message_id"]:
            return  # already showing a card for the current gate

        channel = self.bot.get_channel(row["card_channel_id"]) if row["card_channel_id"] else None
        if channel is None:
            return

        candidates: list[dict] = []
        auto_selected_id: str | None = None
        try:
            if gate == "release":
                entries = await client.list_release_approvals()
                entry = next((e for e in entries if e["id"] == row["vrms_job_id"]), None)
                candidates = (entry or {}).get("candidates") or []
                auto_selected_id = (entry or {}).get("autoSelectedId")
                embed = build_release_gate_embed(row["title"], _find_top_release_candidate(entry), len(candidates))
            else:
                entries = await client.list_final_approvals()
                entry = next((e for e in entries if e["id"] == row["vrms_job_id"]), None)
                embed = build_final_gate_embed(row["title"], entry or {})
        except VRMSAPIError as exc:
            logger.debug("Failed to fetch VRMS %s gate detail for request #%s: %s", gate, row["id"], exc)
            return

        expected_year = int(row["year"]) if row["year"] else None
        try:
            message = await channel.send(
                embed=embed, view=build_gate_view(gate, row["id"], candidates, auto_selected_id, expected_year)
            )
        except discord.HTTPException:
            logger.warning("Failed to post the VRMS %s gate card for request #%s.", gate, row["id"])
            return
        await self.bot.db.set_media_request_gate_message(row["id"], channel.id, message.id)

    async def _clear_vrms_gate(self, row) -> None:
        if not row["vrms_gate_message_id"]:
            return
        channel = self.bot.get_channel(row["vrms_gate_channel_id"]) if row["vrms_gate_channel_id"] else None
        if channel is not None:
            try:
                message = await channel.fetch_message(row["vrms_gate_message_id"])
                await message.edit(view=None)
            except discord.HTTPException:
                pass
        await self.bot.db.clear_media_request_gate_message(row["id"])

    @media.command(name="request", description="Request a movie or TV show.")
    @app_commands.describe(title="Start typing a title, then pick a suggestion.", notes="Anything staff should know (optional).")
    async def request(self, interaction: discord.Interaction, title: str, notes: str | None = None):
        if interaction.guild is None:
            await interaction.response.send_message(embed=error_embed("Server Only", "Media can only be requested in a server."), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        embed = await submit_media_request(self.bot, interaction.guild_id, interaction.user, title, notes, interaction.channel)
        await interaction.followup.send(embed=embed)

    @staff_access()
    @media.command(name="panel", description="Post a media request panel members can use to request titles.")
    @app_commands.describe(message="Optional message shown above the button.")
    async def panel(
        self,
        interaction: discord.Interaction,
        message: str = "Want something added to VeryRare Media? Click below to request it.",
    ):
        embed = make_embed("Request Media", message, color=discord.Color.blurple())
        await interaction.channel.send(embed=embed, view=MediaPanelView())
        await interaction.response.send_message(embed=success_embed("Panel Posted"), ephemeral=True)

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
            if result.media_type == "movie":
                kind = "Movie"
            elif result.is_anime:
                kind = "Anime"
            else:
                kind = "TV"
            label = f"{label} · {kind}"
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
        if request["status"] in TERMINAL_STATUSES:
            await interaction.response.send_message(
                embed=error_embed("Already Final", f"This request is already **{STATUS_LABELS.get(request['status'])}**."), ephemeral=True
            )
            return

        if request["vrms_job_id"]:
            try:
                client = VRMSAPIClient.from_settings()
                await client.cancel_job(request["vrms_job_id"])
            except VRMSAPIError as exc:
                logger.warning("Failed to cancel VRMS job for media request #%s: %s", request_id, exc)
            await self.bot.db.clear_media_request_gate_message(request_id)

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
