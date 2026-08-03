# Configuration

VeryRareBot is configured entirely through environment variables, loaded from a `.env` file next to `bot.py` (see [config/settings.py](../../config/settings.py)). Copy [.env.example](../../.env.example) to `.env` and fill in what you need — every setting below is optional except `DISCORD_TOKEN`, and unconfigured features simply stay disabled rather than erroring.

`validate()` in `config/settings.py` is the only hard requirement check: it refuses to start the bot without `DISCORD_TOKEN`.

## Core

| Variable | Default | Notes |
|---|---|---|
| `DISCORD_TOKEN` | — | **Required.** Bot token from the Discord Developer Portal. |
| `GUILD_ID` | unset | Set during development to sync slash commands instantly to one server. Leave unset for a global sync (can take up to an hour to propagate) in production. |
| `LOG_LEVEL` | `INFO` | Python logging level for the file/console logger. |
| `DATABASE_PATH` | `./data/verrarebot.sqlite3` | SQLite file for warnings, saved playlists, and tickets. Created automatically. |

## Channels

| Variable | Used by |
|---|---|
| `ANNOUNCEMENT_CHANNEL_ID` | `/announce`, `/maintenance` |
| `LOG_CHANNEL_ID` | Logging cog (joins/leaves/edits/deletes/voice/commands) and unhandled command error reports |
| `WELCOME_CHANNEL_ID` | Welcome card posted on member join (see cogs/welcome.py) |
| `VRMS_CHANNEL_ID` | Defined but not currently read by any command or notification — VRMS output goes to wherever `/vrms *` is invoked, and outage/recovery notifications use `VRMS_NOTIFY_CHANNEL_ID` instead. Safe to leave unset. |

## Roles (permission tiers)

| Variable | Grants |
|---|---|
| `OWNER_ROLE_ID` | Everything below, plus implicit bypass of the moderation role-hierarchy check |
| `DEV_OPS_ROLE_ID` | `/serverinfo`, all `/vrms` commands |
| `ADMIN_ROLE_ID` | All moderation commands (`/warn`, `/mute`, `/kick`, `/ban`, `/slowmode`, `/lock`, `/unlock`, `/clear`, `/announce`, `/maintenance`, `/ticket panel`) |
| `STAFF_ROLE_ID` | Detected by `/whoami`; also the fallback for `TICKET_STAFF_ROLE_ID` if that's unset |
| `VRS_MEMBER_ROLE_ID` | Detected by `/whoami`; reserved for future member-only features |

An unset role ID never grants access to anyone — it doesn't fall open. See [core/checks.py](../../core/checks.py) for the exact role-tier logic and the member-targeting hierarchy check (`moderation_target_error`).

## Jellyfin

| Variable | Notes |
|---|---|
| `JELLYFIN_URL` | e.g. `http://localhost:8096` |
| `JELLYFIN_TOKEN` | An API key from Jellyfin's dashboard. Read-only usage (search, sessions, streaming) — the bot never creates or modifies Jellyfin accounts. |
| `JELLYFIN_USER_ID` | Required for library listing, search, and VeryRare-media music search. |
| `JELLYFIN_NOTIFY_CHANNEL_ID` | If set, posts new library additions here (polling; see `JELLYFIN_POLL_SECONDS`). |
| `JELLYFIN_POLL_SECONDS` | Default `300`. |

## VRMS

| Variable | Notes |
|---|---|
| `VRMS_PATH` | Default `/home/ceru/VRMS`. Path existence check only — always safe. |
| `VRMS_SERVICE_NAME` | systemd unit name. `/vrms start\|stop\|restart\|status` and outage/recovery notifications are unavailable unless this is set. Must match `^[A-Za-z0-9_.@-]+$`. |
| `VRMS_NOTIFY_CHANNEL_ID` | If set, posts service outage/recovery transitions here. |
| `VRMS_POLL_SECONDS` | Default `60`. |

The bot invokes only `systemctl {start,stop,restart,status,is-active} <VRMS_SERVICE_NAME>` — nothing else, and only that exact unit name. The OS account running the bot needs systemd permission for that unit; don't run the bot as root for this.

## Music

| Variable | Default | Notes |
|---|---|---|
| `MUSIC_MAX_QUEUE_SIZE` | `200` | Per-guild queue cap. |
| `MUSIC_DEFAULT_VOLUME` | `0.5` | 0.0–2.0 (0–200%). |
| `MUSIC_IDLE_DISCONNECT_SECONDS` | `300` | Auto-leave after this long with nothing queued. `0` disables idle disconnect. |
| `MUSIC_SEARCH_RESULTS` | `5` | Results returned by `/music search` and used when auto-picking the first `/music play` match. |
| `FFMPEG_PATH` | `ffmpeg` | Override if `ffmpeg` isn't on `PATH`. |

No API keys are needed for YouTube/SoundCloud (via `yt-dlp`); VeryRare-media playback reuses the `JELLYFIN_*` settings above.

## Tickets

| Variable | Default | Notes |
|---|---|---|
| `TICKET_CATEGORY_ID` | unset | Discord channel category new ticket channels are created under. Created at the server root if unset. |
| `TICKET_STAFF_ROLE_ID` | falls back to `STAFF_ROLE_ID` | Role given access to every ticket channel and pinged on creation; also authorized to close/delete tickets alongside Owner/DevOps/Admin. |
| `TICKET_MAX_OPEN_PER_USER` | `3` | Simultaneous open-ticket cap per member, per server. |

Ticket categories themselves (labels, form fields, colors) are defined in code at [services/tickets.py](../../services/tickets.py), not via environment variables — see [DEVELOPMENT.md](DEVELOPMENT.md) for how to add one.

## Media requests

| Variable | Default | Notes |
|---|---|---|
| `TMDB_API_KEY` | unset | Free key from [themoviedb.org](https://www.themoviedb.org/settings/api). Required for `/media request` and its title autocomplete; without it, `/media request` returns a clear "not configured" error rather than failing oddly. |
| `MEDIA_REQUEST_CHANNEL_ID` | unset | Where request cards get posted for staff review. Falls back to whatever channel `/media request` was run in if unset. |

There's no VRMS API to configure yet — `/media queue`'s downloading/completed states are set by staff clicking buttons on the request card, not synced automatically. See [ARCHITECTURE.md](ARCHITECTURE.md) for how that's expected to connect once VRMS has one.
