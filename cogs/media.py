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
from core.checks import has_any_role
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
    gate: str, request_id: int, candidates: list[dict] | None = None, auto_selected_id: str | None = None
) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    if gate == "release" and candidates and len(candidates) > 1:
        view.add_item(ReleaseCandidateSelect(request_id, candidates, auto_selected_id))
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


class ReleaseCandidateSelect(discord.ui.Select):
    """Lets staff pick a different release than VRMS's auto-selected one (e.g. a different
    season) right from the release-approval gate card. Unlike VRMSGateButton this isn't
    restart-persistent -- a bot restart before staff picks one just means the dropdown goes
    dead, while the Approve/Deny buttons alongside it (which keep VRMS's own auto-pick) still
    work as the reliable fallback."""

    def __init__(self, request_id: int, candidates: list[dict], auto_selected_id: str | None):
        self.request_id = request_id
        self.candidates = candidates[:25]
        options = []
        for i, candidate in enumerate(self.candidates):
            parsed = candidate.get("parsed") or {}
            bits = []
            if parsed.get("season") is not None:
                bits.append(f"S{int(parsed['season']):02d}")
            if parsed.get("resolution"):
                bits.append(parsed["resolution"])
            if candidate.get("seeders") is not None:
                bits.append(f"{candidate['seeders']} seeders")
            options.append(
                discord.SelectOption(
                    label=(candidate.get("title") or "Unknown")[:100],
                    value=str(i),
                    description=" • ".join(bits)[:100] or None,
                    default=candidate.get("id") == auto_selected_id,
                )
            )
        super().__init__(placeholder="Pick a different release…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        chosen = self.candidates[int(self.values[0])]
        await apply_vrms_gate_action(interaction, "release", "approve", self.request_id, candidate_id=chosen["id"])


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
                candidates = sorted(
                    (entry or {}).get("candidates") or [], key=lambda c: c.get("seeders") or 0, reverse=True
                )
                auto_selected_id = (entry or {}).get("autoSelectedId")
                embed = build_release_gate_embed(row["title"], _find_top_release_candidate(entry), len(candidates))
            else:
                entries = await client.list_final_approvals()
                entry = next((e for e in entries if e["id"] == row["vrms_job_id"]), None)
                embed = build_final_gate_embed(row["title"], entry or {})
        except VRMSAPIError as exc:
            logger.debug("Failed to fetch VRMS %s gate detail for request #%s: %s", gate, row["id"], exc)
            return

        try:
            message = await channel.send(
                embed=embed, view=build_gate_view(gate, row["id"], candidates, auto_selected_id)
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
            is_anime=result.is_anime,
        )
        request_row = await self.bot.db.get_media_request(request_id)

        channel = self.bot.get_channel(settings.MEDIA_REQUEST_CHANNEL_ID) if settings.MEDIA_REQUEST_CHANNEL_ID else interaction.channel
        message = await channel.send(embed=build_request_embed(request_row), view=build_status_view(request_row))
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
