# Development guide

See [ARCHITECTURE.md](ARCHITECTURE.md) first for how the project is laid out.

## Local setup

```bash
python -m venv .venv
. .venv/bin/activate        # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env        # fill in DISCORD_TOKEN at minimum
```

Music playback also needs `ffmpeg` on `PATH` (see [INSTALLATION.md](INSTALLATION.md)) — everything else works without it.

## Running checks

```bash
python -m compileall bot.py cogs config core services views
python -m unittest discover -s tests
```

There's no configured linter in this repo yet; `ruff check --select F,E9 .` (unused imports, undefined names, syntax errors) is a good ad hoc sanity check if you have it installed.

## Testing without a real Discord connection

Most of the interesting logic lives in `services/` and has no Discord dependency, so it's covered by plain `unittest`:

- `tests/test_music_queue.py` — queue/loop/shuffle/volume state, no network or Discord objects.
- `tests/test_database.py`, `tests/test_tickets.py` — SQLite layer against a temp file via `unittest.IsolatedAsyncioTestCase`.
- `tests/test_moderation_checks.py` — the member-hierarchy check, using lightweight fake `Role`/`Member` stand-ins (`MagicMock(spec=discord.Member)` so `isinstance` checks pass) rather than needing a live guild.

For a smoke test of the whole bot without a real token or gateway connection, cogs can be loaded directly:

```python
import asyncio
import bot as botmodule

async def main():
    b = botmodule.VeryRareBot()
    await b.db.connect()
    await b.load_cogs()
    print(sorted(c.qualified_name for c in b.tree.walk_commands()))
    await b.close()

asyncio.run(main())
```

Run with `DISCORD_TOKEN=dummy` in the environment. This exercises every cog's imports, command registration, and `services.database` wiring without contacting Discord. It can't validate anything that needs a live gateway connection — `tree.sync()`, voice playback, or actual message/interaction handling — since those only work after `bot.start()` performs a real login.

## Adding a command

1. Pick the cog it belongs in (or create a new file in `cogs/` with an `async def setup(bot): await bot.add_cog(...)` — it's auto-loaded, nothing else to register).
2. Gate it with the right role check from `core/checks.py` (`admin_access()`, `devops_access()`, etc.) if it shouldn't be open to everyone.
3. If it targets a specific member for a moderation-style action, run `core.checks.moderation_target_error(interaction, member)` first and bail out on a non-`None` result — this is what stops people from muting the owner, themselves, or someone with a higher role.
4. Build responses with the `core/embed.py` helpers (`success_embed`, `error_embed`, `<module>_embed`) rather than constructing `discord.Embed` directly, so styling stays consistent.
5. Add a test if the command wraps non-trivial logic — but prefer putting that logic in `services/` first so it's testable without mocking an `Interaction`.
6. Update [COMMANDS.md](COMMANDS.md).

## Adding a music provider

A provider only needs to satisfy the informal `MusicProvider` protocol in `services/music/base.py`: `name`, `handles(query)`, `search(query, requester_id)`, `resolve_playlist(url, requester_id)`, `stream_url(track)`.

1. Add a new class in `services/music/` (see `ytdlp_provider.py` or `veryrare_provider.py` for examples — most sources can subclass `YtDlpProvider` and just override `name`/`search_prefix`/`domains`).
2. Register it in `services/music/registry.py`'s `PROVIDERS` dict.
3. Add it to `SOURCE_CHOICES` in `cogs/music.py` so it shows up in `/music play` and `/music search`.

`GuildQueue` and `GuildPlayer` don't need to change — they only deal in `Track` objects and `stream_url()`.

## Adding a ticket category

Add one entry to `TICKET_CATEGORIES` in `services/tickets.py`:

```python
"my_category": TicketCategory(
    key="my_category",
    label="Human-Readable Label",
    emoji="🎫",
    color=discord.Color.blurple(),
    intro="Shown at the top of the created ticket channel.",
    fields=[
        TicketField("A question for the user", style=discord.TextStyle.paragraph),
    ],
),
```

That's it — `/ticket open`'s choices, `/ticket panel`'s dropdown, and the submission modal are all built from this dict at import time in `cogs/tickets.py`. Keep it to 5 fields or fewer (a Discord modal limit); `tests/test_tickets.py` asserts this for every category.

## Conventions

- No hardcoded tokens, IDs, or URLs — add a setting in `config/settings.py` and document it in [CONFIGURATION.md](CONFIGURATION.md).
- Services raise a module-specific `*Error` (`MusicProviderError`, `JellyfinError`, `VRMSError`) for user-facing failures; cogs catch those and turn them into an `error_embed`, letting genuinely unexpected exceptions propagate to the global handler in `bot.py` (which logs them and, if `LOG_CHANNEL_ID` is set, reports them there too).
- Prefer extending an existing service/cog over adding a new abstraction layer.
