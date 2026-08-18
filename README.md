# VeryRareBot

VeryRareBot is the Discord assistant for the Very Rare Society. It provides server utilities, moderation, activity logging, music playback, a support ticket system, host monitoring, Jellyfin discovery/notifications, and permission-gated VRMS service controls.

## Features

- General: `/ping`, `/version`, `/uptime`, `/about`, `/whoami`, `/avatar`, `/userinfo`, `/botstats`, `/invite`
- Moderation: `/announce`, `/maintenance`, `/warn`, `/warnings`, `/clearwarnings`, `/mute`, `/kick`, `/ban`, `/slowmode`, `/lock`, `/unlock`, `/clear`
- Logging: member joins/leaves, role changes, message edits/deletes, voice activity, and command usage, to a configured log channel
- Welcome cards: a custom image card (member avatar + the Society's "VRS" graphic) and member-count announcement on join, replacing ProBot's welcome message
- TempVoice: `/voice setup` configures a join-to-create trigger channel; joining it spawns a personal temp voice channel (auto-deleted when empty) with `/voice lock|unlock|rename|limit|kick|claim` plus a matching button control panel, replacing the third-party TempVoice bot
- Music: `/music play|search|pause|resume|stop|skip|previous|queue|remove|shuffle|loop|volume|nowplaying|join|leave|stay` plus `/music playlist save|import|load|list|delete` (private per-user), sourced from YouTube, SoundCloud, or the Society's own Jellyfin library ("VeryRare media"), with an interactive Now Playing card (Previous/Pause/Skip/Loop buttons)
- Tickets: `/ticket open` (VeryRare Media sign-up, bug report, forgot password, moderation appeal, other) and `/ticket panel` for a self-serve picker; each ticket gets a private channel for staff to follow up in
- Media requests: `/media request` (TMDB-backed search with poster art) for movies/shows, `/media album` (MusicBrainz-backed, matched against a real release/tracklist) for albums, `/media importplaylist` (staff-only) to bulk-import a whole YouTube playlist at once with a live progress panel, plus `/media queue`, `/media myrequests`, `/media cancel`, with staff Approve/Deny/Hold buttons on each request card. With `VRMS_API_URL` configured, Approve starts the request as a real VeryRareMediaService job and a background poll takes it the rest of the way — Downloading/Completed happen automatically, and VRMS's own two approval gates (release pick, final check before it's filed) surface as their own cards. Without VRMS configured, it's fully staff-driven by hand instead (see [VRMS_INTEGRATION.md](docs/current/VRMS_INTEGRATION.md))
- Host health: `/serverinfo`
- Jellyfin: `/jellyfin status`, `/jellyfin nowplaying`, `/jellyfin libraries`, `/jellyfin search`, plus background notifications for new library additions
- VRMS: `/vrms status`, `/vrms start`, `/vrms stop`, `/vrms restart`, plus background outage/recovery notifications

Docs: [Commands](docs/current/COMMANDS.md) · [Configuration](docs/current/CONFIGURATION.md) · [Installation](docs/current/INSTALLATION.md) · [Architecture](docs/current/ARCHITECTURE.md) · [Development guide](docs/current/DEVELOPMENT.md) · [VRMS integration](docs/current/VRMS_INTEGRATION.md)

## Setup

1. Install Python 3.10 or newer, plus `ffmpeg` (required for music playback).
2. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in `DISCORD_TOKEN` plus the IDs and integrations you use. Never commit `.env`.
4. In the Discord Developer Portal, enable the **Message Content** and **Server Members** privileged intents for the bot.
5. Run `python bot.py`.

Set `GUILD_ID` during development to make command updates appear immediately in that server. Leave it blank for global command sync in production.

Warnings, saved music playlists, and tickets persist to a local SQLite database at `DATABASE_PATH` (defaults to `./data/verrarebot.sqlite3`). Every environment variable is documented in [docs/current/CONFIGURATION.md](docs/current/CONFIGURATION.md).

## Permissions

Commands use Discord role IDs. Owner has all bot-level roles; DevOps can use host and VRMS commands; Admin can use moderation commands and post the ticket panel; Staff and VRS Member roles are used by `/whoami` and ready for future restricted features. Unset role IDs never grant access. Member-targeting moderation commands additionally refuse to act on the server owner, the bot, the invoker themselves, or anyone with a role at or above the invoker's (or the bot's own) highest role.

Music, general/utility, ticket-opening, and media-request commands are open to any server member; there is no separate DJ role. Closing/deleting a ticket is allowed for its opener (close only) or `TICKET_STAFF_ROLE_ID`/Owner/DevOps/Admin. Reviewing a media request (Approve/Deny/Hold/etc.) is allowed for Owner/DevOps/Admin/Staff.

VRMS actions invoke only `systemctl` against the exact `VRMS_SERVICE_NAME` specified in `.env`; they are unavailable unless that name is configured. The system account running the bot must have the appropriate systemd permission.

Sign-up and forgot-password tickets are informational only — the bot never creates Jellyfin accounts or resets passwords itself; staff handle that through Jellyfin directly.

## Docker

Copy `.env.example` to `.env`, populate it, then run:

```bash
docker compose up -d --build
```

The image installs `ffmpeg`/`libopus0` for music and mounts `./data` for the SQLite database alongside `./logs`. VRMS host-service control is intentionally not included in the container by default.

## Development checks

```bash
python -m compileall bot.py cogs config core services views
python -m unittest discover -s tests
```

See [docs/current/DEVELOPMENT.md](docs/current/DEVELOPMENT.md) for the project layout and guides to adding a command, a music provider, or a ticket category, and [docs/current/ARCHITECTURE.md](docs/current/ARCHITECTURE.md) for how the pieces fit together.
