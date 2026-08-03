# Architecture

## Layout

```
bot.py                 Entry point: builds the client, loads cogs, syncs slash commands,
                        owns the shared Database connection, global error handler.

config/settings.py      All environment variables, in one place. Nothing else reads os.environ.

core/
  checks.py             Role-tier predicates (owner_only, devops_access, admin_access, ...)
                         and moderation_target_error(), the shared member-hierarchy check.
  embed.py               make_embed() + one helper per status/module color, so every embed
                         looks consistent without cogs building discord.Embed by hand.
  logger.py              File + console logging setup.
  startup.py             Console startup/ready banners.
  version.py              Reads VERSION.

services/               Everything that isn't Discord-specific: I/O, business logic, external APIs.
  database.py            Single shared aiosqlite connection (warnings, playlists, tickets).
  jellyfin.py             Read-only Jellyfin API client.
  system.py                Host stats via psutil (for /serverinfo).
  vrms.py                  Narrow systemd wrapper, restricted to one allow-listed unit name.
  tickets.py               Ticket category registry (see "Extending" below).
  tmdb.py                    Read-only TMDB client (search + details) for media request cards.
  welcome_card.py             Pillow image compositing: a member's avatar onto assets/welcome_card.png.

assets/welcome_card.png  The "VRS" template graphic (transparent PNG); avatars are composited onto
                        a copy of this at join time, not modified in place.
  music/
    base.py                Track dataclass, MusicProviderError, MusicProvider protocol.
    queue.py                GuildQueue: loop/shuffle/volume/queue state. No Discord imports —
                            pure logic, which is why it's unit-testable without a bot instance.
    player.py               GuildPlayer: owns one guild's voice_client and playback loop.
                            MusicPlayerManager: one GuildPlayer per guild.
    ytdlp_provider.py        YouTube + SoundCloud via yt-dlp.
    veryrare_provider.py     Jellyfin-backed "VeryRare media" provider.
    registry.py               Maps a source name or a URL to the right provider.

cogs/                    Discord-facing layer: slash commands and event listeners. Each file is
                         auto-loaded by bot.py if it defines an async setup(bot) function.
  admin.py, server.py, utility.py, jellyfin.py, vrms.py, music.py, logging.py,
  notifications.py, tickets.py, media.py, welcome.py

views/media_buttons.py   A discord.ui.View (external link button) used by /jellyfin search.

tests/                   unittest, run with `python -m unittest discover -s tests`.
```

## Design choices worth knowing

**Cogs are thin; services hold the logic.** A cog validates the interaction, calls into `services/`, and turns the result into an embed. This is why `services/music/queue.py` has zero Discord imports and a full unit test suite (`tests/test_music_queue.py`) that runs without a bot, a token, or a network connection.

**One shared SQLite connection.** `bot.db` (a `services.database.Database`) is opened in `setup_hook()` before cogs load and closed in an overridden `close()`. Cogs reach it via `self.bot.db`, not their own connections — there's exactly one writer.

**Auto-loading cogs.** `VeryRareBot.load_cogs()` in `bot.py` imports every `.py` file in `cogs/` as an extension. Adding a new cog is: drop a file in `cogs/` with an `async def setup(bot)`, nothing else to wire up.

**Provider abstraction for music.** `services/music/registry.py` picks a `MusicProvider` by explicit name or by matching the query against each provider's `handles()`. `cogs/music.py` and `GuildPlayer` never know or care whether a track came from YouTube, SoundCloud, or Jellyfin — they only see `Track` objects and a `stream_url()` call. See "Adding a music provider" in [DEVELOPMENT.md](DEVELOPMENT.md).

**Registry-driven ticket categories.** Same idea: `services/tickets.py` has one dict of `TicketCategory` definitions (label, emoji, color, intro text, modal fields). `cogs/tickets.py` builds the slash command choices, the panel's select options, and the submission modal from that dict at import time — adding a category doesn't touch `cogs/tickets.py` at all.

**Persistent views survive restarts.** Ticket buttons/select (`TicketPanelView`, `TicketControlView` in `cogs/tickets.py`) use static `custom_id`s and `timeout=None`, and are registered once via `bot.add_view()` in the cog's `__init__`. On restart, Discord routes button clicks on old messages back to these same handlers — the handlers look up ticket state by `interaction.channel_id` rather than baking a ticket ID into the view, so there's nothing to re-register per ticket.

**Dynamic per-entity persistent views for media requests.** Ticket buttons are stateless (they look up ticket state by `interaction.channel_id`, since a channel holds exactly one ticket). Media request cards don't have that luxury — many cards can sit in the same review channel — so their Approve/Deny/Hold/etc. buttons use `discord.ui.DynamicItem` (`MediaActionButton` in `cogs/media.py`): the request ID is encoded directly in the button's `custom_id` (`media:<action>:<request_id>`), matched by a regex `template` the class registers once via `bot.add_dynamic_items()`. Discord routes a click on *any* matching `custom_id` — including on messages sent long before the current process started — back to `from_custom_id()`, which reconstructs the button and calls its `callback()`. No per-card view registration, no in-memory state to lose on restart.

**Fail open to "feature disabled," not to a crash.** Jellyfin, VRMS, notifications, and tickets are all no-ops (or return a clear user-facing error) when their settings are unconfigured, rather than raising on import or at startup. `config/settings.py`'s `validate()` only hard-requires `DISCORD_TOKEN`.

## Request flow (example: `/music play`)

1. `cogs/music.py: Music.play` validates the user is in a voice channel, connects if needed.
2. `services/music/registry.py: resolve_provider()` picks a provider from the `source` choice or by sniffing the query.
3. The provider's `search()` (in `ytdlp_provider.py` or `veryrare_provider.py`) returns `Track` objects — metadata only, no audio yet.
4. `GuildQueue.enqueue()` / `enqueue_many()` adds them (`services/music/queue.py`).
5. If nothing is currently playing, `GuildPlayer.play_next()` calls `provider.stream_url(track)` to lazily resolve a short-lived direct audio URL, then hands it to `discord.FFmpegPCMAudio`.
6. When ffmpeg finishes, discord.py's `after=` callback (running on a worker thread) hands control back to the event loop via `asyncio.run_coroutine_threadsafe`, which re-enters `play_next()` for the next track.

## Media requests and the VRMS integration seam

`cogs/media.py` (`/media request`, `/media queue`, `/media myrequests`, `/media cancel`) is a request/approval/queue system for the Very Rare Media Service, built ahead of VRMS having any API to integrate with. It's entirely self-contained today:

- `services/tmdb.py` supplies search, metadata, and poster art (title, year, overview, poster) — this is the only external API involved, and it's read-only.
- `services/database.py`'s `media_requests` table is the source of truth for status: `pending → approved → downloading → completed`, with `denied`/`on_hold`/`cancelled` as side branches. See `TRANSITIONS` in `cogs/media.py` for the exact allowed state graph.
- Every status change today happens because a staff member clicked a button on the request card (`apply_media_action()` in `cogs/media.py`). There is no code anywhere that talks to VRMS itself — the `downloading` and `completed` states are just labels staff set by hand once VRMS is actually fetching something.

**Where a real VRMS API plugs in later:** once VRMS exposes something the bot can call, the natural integration points are:

1. A `services/vrms.py` method (alongside the existing `service_action`/`status`/`is_active`) that asks VRMS to start a download for an approved request, called right after (or instead of) the "Mark Downloading" button handler in `apply_media_action()`.
2. A polling loop in `cogs/notifications.py` (same pattern as the existing Jellyfin/VRMS polling) or a webhook receiver, that calls `bot.db.update_media_request_status()` automatically when VRMS reports a download finished — replacing the manual "Mark Completed" click, or leaving it as a manual confirmation step alongside an automatic status hint if you'd rather keep a human in the loop.

Nothing on the Discord-facing side (the cards, the queue browser, `/media myrequests`) needs to change for that — they render whatever's in `media_requests`, however it got there.

## Extending

See [DEVELOPMENT.md](DEVELOPMENT.md) for step-by-step guides to adding a command, a music provider, and a ticket category.
