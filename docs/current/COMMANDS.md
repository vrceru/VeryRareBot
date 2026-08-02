# VeryRareBot commands

## Everyone

- `/ping` — bot latency
- `/version` — installed bot version
- `/uptime` — current process uptime
- `/about` — bot summary
- `/whoami` — detected VeryRareBot permission roles
- `/jellyfin status` — Jellyfin server name and version
- `/jellyfin nowplaying` — active playback sessions
- `/jellyfin libraries` — libraries visible to `JELLYFIN_USER_ID`
- `/jellyfin search <query>` — search movies, shows, episodes, and audio

## Admin

- `/announce <message>` — send an embed to `ANNOUNCEMENT_CHANNEL_ID`
- `/warn <member> <reason>` — post and attempt to direct-message a warning
- `/mute <member> <minutes> <reason>` — Discord timeout from 1 minute to 28 days
- `/clear <amount>` — delete 1–100 recent messages

## DevOps

- `/serverinfo` — hostname, OS, CPU, memory, disk, and uptime
- `/vrms status` — configured project path and systemd status
- `/vrms start`, `/vrms stop`, `/vrms restart` — operate `VRMS_SERVICE_NAME`

VRMS commands are deliberately unavailable until a service name is configured. All role-restricted commands reject users when the corresponding role IDs are unset.
