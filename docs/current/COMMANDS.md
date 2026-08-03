# VeryRareBot commands

## Everyone

- `/ping` — bot latency
- `/version` — installed bot version
- `/uptime` — current process uptime
- `/about` — bot summary
- `/whoami` — detected VeryRareBot permission roles
- `/avatar [member]` — a member's avatar
- `/userinfo [member]` — account/server info for a member
- `/botstats` — runtime stats: latency, uptime, servers, members, CPU/memory
- `/invite` — OAuth2 link to add the bot to another server
- `/jellyfin status` — Jellyfin server name and version
- `/jellyfin nowplaying` — active playback sessions
- `/jellyfin libraries` — libraries visible to `JELLYFIN_USER_ID`
- `/jellyfin search <query>` — search movies, shows, episodes, and audio
- `/music play <query> [source]` — search or queue a URL from YouTube, SoundCloud, or VeryRare media (Jellyfin); auto-detects the source unless one is given
- `/music search <query> [source]` — preview results without queueing
- `/music pause`, `/music resume`, `/music stop`, `/music skip`
- `/music queue` — show what's playing and up next
- `/music remove <position>` — remove a queued track
- `/music shuffle` — shuffle the upcoming queue
- `/music loop <off|track|queue>`
- `/music volume <0-200>`
- `/music nowplaying`
- `/music join`, `/music leave`
- `/music playlist save <name>` / `load <name>` / `list` / `delete <name>` — personal saved playlists
- `/ticket open <category>` — open a support ticket (VeryRare Media sign-up, bug report, forgot password, moderation appeal, or other); opens a form, then creates a private ticket channel
- `/ticket close` — close the current ticket (opener or staff)

## Admin

- `/announce <message>` — send an embed to `ANNOUNCEMENT_CHANNEL_ID`
- `/maintenance <message> [starts_in_minutes]` — scheduled-maintenance notice to `ANNOUNCEMENT_CHANNEL_ID`
- `/warn <member> <reason>` — record a warning, post it, and attempt to DM the member
- `/warnings <member>` — view a member's warning history
- `/clearwarnings <member>` — clear a member's warning history
- `/mute <member> <minutes> <reason>` — Discord timeout from 1 minute to 28 days
- `/kick <member> [reason]`
- `/ban <member> [reason] [delete_message_days]`
- `/slowmode <seconds>` — 0 disables it, max 21600 (6 hours)
- `/lock`, `/unlock` — toggle `@everyone` send permission on the current channel
- `/clear <amount>` — delete 1–100 recent messages
- `/ticket panel [message]` — post a persistent category-picker panel for members to self-serve ticket creation

All moderation commands that target a member (`warn`, `mute`, `kick`, `ban`) reject the action if the target is the server owner, the bot, yourself, or has a role at or above your own (or the bot's).

## DevOps

- `/serverinfo` — hostname, OS, CPU, memory, disk, and uptime
- `/vrms status` — configured project path and systemd status
- `/vrms start`, `/vrms stop`, `/vrms restart` — operate `VRMS_SERVICE_NAME`

VRMS commands are deliberately unavailable until a service name is configured. All role-restricted commands reject users when the corresponding role IDs are unset.

## Background behavior (no command)

- **Logging** — member join/leave, role changes, message edits/deletes, voice channel activity, and command usage are logged to `LOG_CHANNEL_ID` (and the log file) when configured. Member joins also post a welcome message to `WELCOME_CHANNEL_ID`.
- **Notifications** — polls Jellyfin for new library additions (posted to `JELLYFIN_NOTIFY_CHANNEL_ID`) and VRMS service state changes (posted to `VRMS_NOTIFY_CHANNEL_ID`). Both are disabled unless their channel ID is set.
- Music auto-disconnects after `MUSIC_IDLE_DISCONNECT_SECONDS` of inactivity, or immediately if everyone leaves its voice channel.
- **Tickets** — each ticket gets its own private channel (visible to the opener, `TICKET_STAFF_ROLE_ID`, and the bot) under `TICKET_CATEGORY_ID`. Sign-up and forgot-password tickets are informational only: staff still create the Jellyfin account or reset the password by hand — the bot does not touch Jellyfin credentials for this. Closing renames the channel to `closed-...` and revokes the opener's send access; deleting the channel is a separate, staff-only step. Users are capped at `TICKET_MAX_OPEN_PER_USER` simultaneous open tickets.
