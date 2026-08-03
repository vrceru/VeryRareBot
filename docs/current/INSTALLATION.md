# Installation

See [CONFIGURATION.md](CONFIGURATION.md) for what every `.env` variable below actually does, and [COMMANDS.md](COMMANDS.md) for the commands each feature unlocks.

## Native Linux deployment

```bash
git clone https://github.com/vrceru/VeryRareBot.git
cd VeryRareBot
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `DISCORD_TOKEN`. Configure role and channel IDs only for features that your Discord server uses, then start the bot with:

```bash
python bot.py
```

Before starting the bot, enable the **Message Content** and **Server Members** privileged intents for your application in the [Discord Developer Portal](https://discord.com/developers/applications) (Bot page) — `bot.py` requests both, and Discord will reject the connection if they aren't turned on there.

For VRMS controls, set `VRMS_SERVICE_NAME` to the unit name managed by systemd (for example, `vrms.service`). Give the bot's operating-system user only the narrowly scoped privilege required for that unit; do not run the bot as root.

### Music playback

Music playback shells out to `ffmpeg`, so it must be installed and on `PATH` (or point `FFMPEG_PATH` at it):

```bash
sudo apt install ffmpeg libopus0   # Debian/Ubuntu
```

No API keys are required for YouTube or SoundCloud (via `yt-dlp`); VeryRare media playback reuses the existing `JELLYFIN_*` settings.

### Database

Warnings, saved playlists, and tickets are stored in a SQLite file, created automatically at `DATABASE_PATH` (defaults to `./data/verrarebot.sqlite3`). Back this file up if you care about warning or ticket history.

### Tickets

No extra installation steps — the ticket system uses the same SQLite database. Set `TICKET_CATEGORY_ID` to a channel category if you want ticket channels grouped somewhere specific, and `TICKET_STAFF_ROLE_ID` if ticket staff shouldn't just be `STAFF_ROLE_ID`. Then run `/ticket panel` once in whichever channel members should use to open tickets — it posts a persistent picker that keeps working across restarts.

## Docker deployment

```bash
cp .env.example .env
# edit .env
docker compose up -d --build
docker compose logs -f
```

The Docker service does not expose host systemd. Leave `VRMS_SERVICE_NAME` empty in a container deployment unless you explicitly design a restricted host-control solution.
