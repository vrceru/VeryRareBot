# Installation

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

For VRMS controls, set `VRMS_SERVICE_NAME` to the unit name managed by systemd (for example, `vrms.service`). Give the bot's operating-system user only the narrowly scoped privilege required for that unit; do not run the bot as root.

## Docker deployment

```bash
cp .env.example .env
# edit .env
docker compose up -d --build
docker compose logs -f
```

The Docker service does not expose host systemd. Leave `VRMS_SERVICE_NAME` empty in a container deployment unless you explicitly design a restricted host-control solution.
