# VeryRareBot

VeryRareBot is the Discord assistant for the Very Rare Society. It provides server utilities, moderation, activity logging, music playback, host monitoring, Jellyfin discovery/notifications, and permission-gated VRMS service controls.

## Features

- General: `/ping`, `/version`, `/uptime`, `/about`, `/whoami`, `/avatar`, `/userinfo`, `/botstats`, `/invite`
- Moderation: `/announce`, `/maintenance`, `/warn`, `/warnings`, `/clearwarnings`, `/mute`, `/kick`, `/ban`, `/slowmode`, `/lock`, `/unlock`, `/clear`
- Logging: member joins/leaves, role changes, message edits/deletes, voice activity, and command usage, to a configured log channel
- Music: `/music play|search|pause|resume|stop|skip|queue|remove|shuffle|loop|volume|nowplaying|join|leave` plus `/music playlist save|load|list|delete`, sourced from YouTube, SoundCloud, or the Society's own Jellyfin library ("VeryRare media")
- Host health: `/serverinfo`
- Jellyfin: `/jellyfin status`, `/jellyfin nowplaying`, `/jellyfin libraries`, `/jellyfin search`, plus background notifications for new library additions
- VRMS: `/vrms status`, `/vrms start`, `/vrms stop`, `/vrms restart`, plus background outage/recovery notifications

Full command reference: [docs/current/COMMANDS.md](docs/current/COMMANDS.md).

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

Warnings and saved music playlists persist to a local SQLite database at `DATABASE_PATH` (defaults to `./data/verrarebot.sqlite3`).

## Permissions

Commands use Discord role IDs. Owner has all bot-level roles; DevOps can use host and VRMS commands; Admin can use moderation commands; Staff and VRS Member roles are used by `/whoami` and ready for future restricted features. Unset role IDs never grant access. Member-targeting moderation commands additionally refuse to act on the server owner, the bot, the invoker themselves, or anyone with a role at or above the invoker's (or the bot's own) highest role.

Music and general/utility commands are open to any server member; there is no separate DJ role.

VRMS actions invoke only `systemctl` against the exact `VRMS_SERVICE_NAME` specified in `.env`; they are unavailable unless that name is configured. The system account running the bot must have the appropriate systemd permission.

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
