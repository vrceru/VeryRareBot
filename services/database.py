"""SQLite persistence for moderation warnings and saved music playlists."""

from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from services.music.base import Track

_SCHEMA = """
CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_warnings_guild_user ON warnings (guild_id, user_id);

CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (guild_id, owner_id, name)
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    webpage_url TEXT NOT NULL,
    duration INTEGER,
    source TEXT NOT NULL,
    artist TEXT
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL UNIQUE,
    opener_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    closed_at TEXT,
    closed_by_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_tickets_guild_opener ON tickets (guild_id, opener_id, status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """A single shared aiosqlite connection, owned by the bot instance."""

    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected yet.")
        return self._conn

    # ------------------------------------------------------------------
    # Warnings
    # ------------------------------------------------------------------

    async def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
        cursor = await self.conn.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, reason, _now()),
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def list_warnings(self, guild_id: int, user_id: int) -> list[aiosqlite.Row]:
        cursor = await self.conn.execute(
            "SELECT id, moderator_id, reason, created_at FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC",
            (guild_id, user_id),
        )
        return list(await cursor.fetchall())

    async def clear_warnings(self, guild_id: int, user_id: int) -> int:
        cursor = await self.conn.execute(
            "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await self.conn.commit()
        return cursor.rowcount

    # ------------------------------------------------------------------
    # Playlists
    # ------------------------------------------------------------------

    async def save_playlist(self, guild_id: int, owner_id: int, name: str, tracks: list[Track]) -> None:
        await self.conn.execute(
            "DELETE FROM playlists WHERE guild_id = ? AND owner_id = ? AND name = ?",
            (guild_id, owner_id, name),
        )
        cursor = await self.conn.execute(
            "INSERT INTO playlists (guild_id, owner_id, name, created_at) VALUES (?, ?, ?, ?)",
            (guild_id, owner_id, name, _now()),
        )
        playlist_id = cursor.lastrowid
        await self.conn.executemany(
            "INSERT INTO playlist_tracks (playlist_id, position, title, webpage_url, duration, source, artist) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (playlist_id, index, track.title, track.webpage_url, track.duration, track.source, track.artist)
                for index, track in enumerate(tracks)
            ],
        )
        await self.conn.commit()

    async def load_playlist(self, guild_id: int, owner_id: int, name: str, requester_id: int) -> list[Track] | None:
        cursor = await self.conn.execute(
            "SELECT id FROM playlists WHERE guild_id = ? AND owner_id = ? AND name = ?",
            (guild_id, owner_id, name),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        cursor = await self.conn.execute(
            "SELECT title, webpage_url, duration, source, artist FROM playlist_tracks "
            "WHERE playlist_id = ? ORDER BY position ASC",
            (row["id"],),
        )
        rows = await cursor.fetchall()
        return [
            Track(
                title=r["title"],
                webpage_url=r["webpage_url"],
                duration=r["duration"],
                requester_id=requester_id,
                source=r["source"],
                artist=r["artist"],
            )
            for r in rows
        ]

    async def list_playlists(self, guild_id: int, owner_id: int) -> list[str]:
        cursor = await self.conn.execute(
            "SELECT name FROM playlists WHERE guild_id = ? AND owner_id = ? ORDER BY name ASC",
            (guild_id, owner_id),
        )
        return [r["name"] for r in await cursor.fetchall()]

    async def delete_playlist(self, guild_id: int, owner_id: int, name: str) -> bool:
        cursor = await self.conn.execute(
            "DELETE FROM playlists WHERE guild_id = ? AND owner_id = ? AND name = ?",
            (guild_id, owner_id, name),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Tickets
    # ------------------------------------------------------------------

    async def create_ticket(self, guild_id: int, channel_id: int, opener_id: int, category: str) -> int:
        cursor = await self.conn.execute(
            "INSERT INTO tickets (guild_id, channel_id, opener_id, category, status, created_at) "
            "VALUES (?, ?, ?, ?, 'open', ?)",
            (guild_id, channel_id, opener_id, category, _now()),
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def count_open_tickets(self, guild_id: int, opener_id: int) -> int:
        cursor = await self.conn.execute(
            "SELECT COUNT(*) AS n FROM tickets WHERE guild_id = ? AND opener_id = ? AND status = 'open'",
            (guild_id, opener_id),
        )
        row = await cursor.fetchone()
        return row["n"] if row else 0

    async def get_ticket_by_channel(self, channel_id: int) -> aiosqlite.Row | None:
        cursor = await self.conn.execute(
            "SELECT * FROM tickets WHERE channel_id = ?",
            (channel_id,),
        )
        return await cursor.fetchone()

    async def close_ticket(self, channel_id: int, closed_by_id: int) -> bool:
        cursor = await self.conn.execute(
            "UPDATE tickets SET status = 'closed', closed_at = ?, closed_by_id = ? "
            "WHERE channel_id = ? AND status = 'open'",
            (_now(), closed_by_id, channel_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0
