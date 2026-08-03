# VeryRareBot commands

All commands are Discord slash commands. Command groups (`/jellyfin`, `/music`, `/music playlist`, `/vrms`, `/ticket`) aren't invoked directly — Discord shows their subcommands.

## Everyone

General:

- `/ping` — bot latency
- `/version` — installed bot version
- `/uptime` — current process uptime
- `/about` — bot summary
- `/whoami` — your detected VeryRareBot permission roles
- `/avatar [member]` — a member's avatar (defaults to you)
- `/userinfo [member]` — account/server info for a member
- `/botstats` — runtime stats: version, latency, uptime, servers, members, CPU/memory, discord.py version
- `/invite` — OAuth2 link to add the bot to another server

Jellyfin:

- `/jellyfin status` — server name, version, OS
- `/jellyfin nowplaying` — active playback sessions
- `/jellyfin libraries` — libraries visible to `JELLYFIN_USER_ID`
- `/jellyfin search <query>` — search movies, shows, episodes, and audio

Music (open to any member — no separate DJ role):

- `/music join` — connect the bot to your voice channel. **Required first step** — `/music play` and `/music playlist load` won't auto-connect; they'll tell you to run this first if the bot isn't already in your channel.
- `/music play <query> [source]` — search or queue a URL from YouTube, SoundCloud, or VeryRare media (Jellyfin); auto-detects the source from the query unless `source` is given. Requires the bot to already be connected via `/music join`.
- `/music search <query> [source]` — preview results without queueing
- `/music pause` / `/music resume` / `/music stop` / `/music skip` / `/music previous`
- `/music queue` — what's playing and what's up next
- `/music remove <position>` — remove a track from the queue by its `/music queue` position
- `/music shuffle` — shuffle the upcoming queue
- `/music loop <off|track|queue>`
- `/music volume <0-200>`
- `/music nowplaying` — posts (or re-posts) the interactive Now Playing card

Whenever something starts playing, the bot posts a **Now Playing card** with Previous/Pause-Resume/Skip/Loop buttons, and edits that same message in place as the track changes, gets paused, or loops — so most playback control doesn't need typed commands at all. It's tied to a single live player per server, not preserved across a bot restart (a restart naturally interrupts voice anyway).
- `/music leave` — disconnect and clear the queue
- `/music stay` — toggle whether the bot stays connected instead of auto-disconnecting when idle or when everyone leaves the channel. Only an explicit `/music leave` disconnects it while this is on.
- `/music playlist save <name>` — save the current queue
- `/music playlist import <url> <name>` — save a YouTube or SoundCloud playlist URL as a playlist, without queueing/playing it now
- `/music playlist load <name>` — queue a saved playlist. Also requires `/music join` first.
- `/music playlist list` — list your saved playlists
- `/music playlist delete <name>`

Saved playlists (`save`/`import`/`list`/`load`/`delete`) are private to whoever created them — every playlist is scoped to its owner's Discord user ID in the database, so other members (including staff) can't see or load someone else's playlist by name, even if they guess it.

Tickets:

- `/ticket open <category>` — open a support ticket. Choosing a category opens a form; submitting it creates a private ticket channel. Categories: VeryRare Media Sign-Up, Bug Report, Forgot Password, Moderation Appeal, Other.
- `/ticket close` — close the current ticket (usable by the ticket's opener or staff). Also available as a button in the ticket channel.

Media requests:

- `/media request <title> [notes]` — request a movie or TV show. Start typing and pick a suggestion (needs `TMDB_API_KEY`); posts a review card with a poster, overview, and Approve/Deny/Hold buttons to `MEDIA_REQUEST_CHANNEL_ID` (or the current channel if unset).
- `/media queue [status]` — browse the request queue one card at a time. Defaults to active requests (pending, on hold, approved, downloading); pass a specific status to see history too.
- `/media myrequests` — a compact list of your own requests and their status.
- `/media cancel <request_id>` — cancel your own request (or, for staff, anyone's), unless it's already completed/denied/cancelled/failed. If a VRMS job is attached, this also cancels it in VRMS.

**With `VRMS_API_URL` configured**, clicking Approve also starts the request as a VRMS job — no separate "Mark Downloading" click needed (that button only reappears as a manual fallback if VRMS isn't configured or the enqueue call fails). From there:
- A background poll picks up VRMS's status automatically: the card moves to Downloading once VRMS actually starts working, and to Completed or Failed when the job finishes — no further clicks needed for the happy path.
- If VRMS pauses at one of its own two approval gates (release selection, then a final check before it's filed into the library), a separate gate card appears with its own Approve/Deny buttons showing what VRMS found (release quality/seeders, or the matched title/poster and a storage check). Denying at a gate cancels the whole request.
- Without `VRMS_API_URL` set, nothing here changes — Approve/Mark Downloading/Mark Completed work exactly as before, fully staff-driven.

TempVoice (join-to-create voice channels, replaces the third-party TempVoice bot):

- `/voice lock` / `/voice unlock` — control whether new members can join your temp channel
- `/voice rename <name>` — rename your temp channel
- `/voice limit <0-99>` — set a user limit (0 = unlimited)
- `/voice kick <member>` — remove someone from your temp channel
- `/voice claim` — take ownership of a temp channel whose owner has left (only works if the owner isn't still in it)

All of the above are also buttons (Lock/Unlock/Rename/Limit/Claim) on a live dashboard posted automatically in each new temp channel's own chat, showing the owner, lock status, user limit, and current members — edited in place whenever any of that changes, not just posted once. The channel owner also gets Manage Channel + Move Members on their channel directly, so Discord's native channel settings work too. Joining the configured trigger voice channel creates a new temp channel under the configured category and moves you into it; it's deleted automatically once everyone leaves. Set up with `/voice setup` (Admin, below).

## Admin

- `/announce <message>` — send an embed to `ANNOUNCEMENT_CHANNEL_ID`
- `/maintenance <message> [starts_in_minutes]` — scheduled-maintenance notice to `ANNOUNCEMENT_CHANNEL_ID`
- `/warn <member> <reason>` — record a warning, post it, and attempt to DM the member
- `/warnings <member>` — view a member's warning history
- `/clearwarnings <member>` — clear a member's warning history
- `/mute <member> <minutes> <reason>` — Discord timeout, 1 minute to 28 days
- `/kick <member> [reason]`
- `/ban <member> [reason] [delete_message_days]`
- `/slowmode <seconds>` — 0 disables it, max 21600 (6 hours)
- `/lock` / `/unlock` — toggle `@everyone`'s send permission on the current channel
- `/clear <amount>` — delete 1–100 recent messages
- `/ticket panel [message]` — post a persistent category-picker panel so members can self-serve ticket creation
- `/voice setup <trigger_channel> [category]` — configure TempVoice's join-to-create trigger channel and where temp channels get created. Stored in the database, not `.env` — no restart needed, and re-running it just updates the config.
- `/voice disable` — stop creating new temp channels (existing ones are unaffected)

Moderation commands that target a member (`warn`, `mute`, `kick`, `ban`) refuse to act if the target is the server owner, the bot, yourself, or has a role at or above your own (or the bot's own) highest role.

## DevOps

- `/serverinfo` — hostname, OS, CPU, memory, disk, and uptime
- `/vrms status` — configured project path and systemd status
- `/vrms start` / `/vrms stop` / `/vrms restart` — operate `VRMS_SERVICE_NAME`

VRMS commands are unavailable until `VRMS_SERVICE_NAME` is configured. All role-restricted commands reject users when the corresponding role ID is unset — an unset role ID never grants access to anyone.

## Media request review (button-based, not a command)

The Approve / Deny / Hold / Mark Downloading / Mark Completed buttons on a request card are usable by Owner, DevOps, Admin, or Staff role holders — the same tier as `/whoami`'s Staff detection, broader than moderation's Admin-only gate, since content curation is typically a general staff duty. Anyone else clicking a button gets an ephemeral "not allowed" response; the button itself doesn't change.

## Background behavior (no command)

- **Logging** — member joins/leaves, role changes, message edits/deletes, voice channel activity, and slash command usage are logged to `LOG_CHANNEL_ID` (and the log file) when configured. Unhandled command errors are also forwarded to `LOG_CHANNEL_ID`.
- **Welcome cards** — replaces ProBot's welcome message. On member join, posts a custom image card (the member's avatar composited onto `assets/welcome_card.png`) with `"@member Welcome to <server> we are now at <count> Members!!!"` to `WELCOME_CHANNEL_ID`. Falls back to text-only if image generation fails for any reason (e.g. the member's avatar couldn't be fetched) — the announcement itself is never silently skipped.
- **Notifications** — polls Jellyfin for new library additions (`JELLYFIN_NOTIFY_CHANNEL_ID`) and VRMS service state changes (`VRMS_NOTIFY_CHANNEL_ID`). Each is disabled unless its channel ID is set. The first poll after startup only records a baseline — it doesn't replay pre-existing history.
- **Music auto-disconnect** — leaves the voice channel after `MUSIC_IDLE_DISCONNECT_SECONDS` of inactivity, or immediately once every human leaves. Disabled while `/music stay` is on.
- **Tickets** — each ticket gets a private channel under `TICKET_CATEGORY_ID`, visible to the opener, `TICKET_STAFF_ROLE_ID`, and the bot. Sign-up and forgot-password tickets are informational only: staff create the Jellyfin account or reset the password by hand. Closing a ticket revokes the opener's send access and renames the channel to `closed-...`; deleting the channel afterward is a separate, staff-only button. Users are capped at `TICKET_MAX_OPEN_PER_USER` simultaneous open tickets.

See also: [CONFIGURATION.md](CONFIGURATION.md) for every setting referenced above, and [ARCHITECTURE.md](ARCHITECTURE.md) for how the pieces fit together.
