"""Read-only client for MusicBrainz, used to search and enrich album requests.

Mirrors services/tmdb.py's shape but for albums. Backs /media album, which is
distinct from /music (live playback via yt-dlp) -- this is what lets an album
request be matched against a real release (with a real tracklist) and routed
through VRMS's download/organize pipeline into VeryRare Media, the same way a
movie or show request is.
"""

from dataclasses import dataclass
from typing import Any

import aiohttp

API_BASE = "https://musicbrainz.org/ws/2"
COVER_ART_BASE = "https://coverartarchive.org"
# MusicBrainz requires a descriptive User-Agent identifying the application -- matches the
# one VRMS's own MusicBrainz client uses server-side, for consistency.
USER_AGENT = "VeryRareBot/1.0 (self-hosted community bot)"


class MusicBrainzError(RuntimeError):
    """A user-safe MusicBrainz integration error."""


@dataclass(slots=True)
class AlbumResult:
    mbid: str
    title: str
    artist: str | None
    year: str | None
    poster_url: str | None


def _artist_name(item: dict[str, Any]) -> str | None:
    credits = item.get("artist-credit") or []
    return credits[0].get("name") if credits else None


def _to_result(item: dict[str, Any]) -> AlbumResult:
    date = item.get("date") or ""
    mbid = item["id"]
    return AlbumResult(
        mbid=mbid,
        title=item.get("title") or "Unknown title",
        artist=_artist_name(item),
        year=date[:4] if date else None,
        poster_url=f"{COVER_ART_BASE}/release/{mbid}/front",
    )


@dataclass(slots=True)
class MusicBrainzClient:
    async def _request(self, path: str, **params: str) -> dict[str, Any]:
        query = {**params, "fmt": "json"}
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": USER_AGENT}) as session:
                async with session.get(f"{API_BASE}{path}", params=query) as response:
                    if response.status >= 400:
                        raise MusicBrainzError(f"MusicBrainz returned HTTP {response.status}.")
                    return await response.json()
        except aiohttp.ClientError as exc:
            raise MusicBrainzError("Could not reach MusicBrainz.") from exc

    async def search_releases(self, query: str, limit: int = 8) -> list[AlbumResult]:
        data = await self._request("/release", query=query)
        return [_to_result(item) for item in (data.get("releases") or [])[:limit]]

    async def get_release(self, mbid: str) -> AlbumResult:
        data = await self._request(f"/release/{mbid}", inc="artist-credits")
        return _to_result(data)
