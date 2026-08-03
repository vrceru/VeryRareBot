"""Shared types for music providers."""

from dataclasses import dataclass
from typing import Protocol


class MusicProviderError(RuntimeError):
    """A user-safe music provider error."""


@dataclass(slots=True)
class Track:
    title: str
    webpage_url: str
    duration: int | None
    requester_id: int
    source: str
    thumbnail: str | None = None
    artist: str | None = None


class MusicProvider(Protocol):
    """A source of playable tracks (YouTube, SoundCloud, a media server, ...)."""

    name: str

    async def search(self, query: str, requester_id: int) -> list[Track]:
        """Return candidate tracks for a free-text query."""

    async def resolve_playlist(self, url: str, requester_id: int) -> list[Track]:
        """Expand a playlist URL into its member tracks."""

    async def stream_url(self, track: Track) -> str:
        """Resolve a short-lived, directly playable audio URL for a track."""

    def handles(self, query: str) -> bool:
        """Whether this provider recognizes the query as one of its own URLs."""
