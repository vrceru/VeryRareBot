# VeryRareBot

VeryRareBot is the Discord assistant for the Very Rare Society. It provides server utilities, moderation, host monitoring, Jellyfin discovery, and permission-gated VRMS service controls.

## Features

- General commands: `/ping`, `/version`, `/uptime`, `/about`, and `/whoami`
- Moderation: `/announce`, `/warn`, `/mute`, and `/clear`
- Host health: `/serverinfo`
- Jellyfin: `/jellyfin status`, `/jellyfin nowplaying`, `/jellyfin libraries`, and `/jellyfin search`
- VRMS: `/vrms status`, `/vrms start`, `/vrms stop`, and `/vrms restart`

## Setup

1. Install Python 3.10 or newer.
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

## Permissions

Commands use Discord role IDs. Owner has all bot-level roles; DevOps can use host and VRMS commands; Admin can use moderation commands; Staff and VRS Member roles are used by `/whoami` and ready for future restricted features. Unset role IDs never grant access.

VRMS actions invoke only `systemctl` against the exact `VRMS_SERVICE_NAME` specified in `.env`; they are unavailable unless that name is configured. The system account running the bot must have the appropriate systemd permission.

## Docker

Copy `.env.example` to `.env`, populate it, then run:

```bash
docker compose up -d --build
```

The Docker deployment supports bot and Jellyfin features. VRMS host-service control is intentionally not included in the container by default.

## Development checks

```bash
python -m compileall bot.py cogs config core services views
python -m unittest discover -s tests
```
