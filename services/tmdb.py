"""Read-only client for The Movie Database (TMDB), used to search and enrich media requests."""

from dataclasses import dataclass
from typing import Any

import aiohttp

from config import settings

API_BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


class TMDBError(RuntimeError):
    """A user-safe TMDB integration error."""


@dataclass(slots=True)
class MediaResult:
    tmdb_id: int
    media_type: str  # "movie" | "tv"
    title: str
    year: str | None
    overview: str | None
    poster_url: str | None


def _to_result(item: dict[str, Any], media_type: str) -> MediaResult:
    title = item.get("title") or item.get("name") or "Unknown title"
    date = item.get("release_date") or item.get("first_air_date") or ""
    poster_path = item.get("poster_path")
    return MediaResult(
        tmdb_id=item["id"],
        media_type=media_type,
        title=title,
        year=date[:4] if date else None,
        overview=item.get("overview") or None,
        poster_url=f"{IMAGE_BASE}{poster_path}" if poster_path else None,
    )


@dataclass(slots=True)
class TMDBClient:
    api_key: str

    @classmethod
    def from_settings(cls) -> "TMDBClient":
        if not settings.TMDB_API_KEY:
            raise TMDBError("Media requests aren't configured. Set TMDB_API_KEY.")
        return cls(settings.TMDB_API_KEY)

    async def _request(self, path: str, **params: str) -> dict[str, Any]:
        query = {**params, "api_key": self.api_key}
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{API_BASE}{path}", params=query) as response:
                    if response.status == 401:
                        raise TMDBError("TMDB rejected the configured API key.")
                    if response.status >= 400:
                        raise TMDBError(f"TMDB returned HTTP {response.status}.")
                    return await response.json()
        except aiohttp.ClientError as exc:
            raise TMDBError("Could not reach TMDB.") from exc

    async def search_multi(self, query: str, limit: int = 8) -> list[MediaResult]:
        data = await self._request("/search/multi", query=query, include_adult="false")
        results: list[MediaResult] = []
        for item in data.get("results", []):
            media_type = item.get("media_type")
            if media_type not in ("movie", "tv"):
                continue
            results.append(_to_result(item, media_type))
            if len(results) >= limit:
                break
        return results

    async def get_details(self, media_type: str, tmdb_id: int) -> MediaResult:
        if media_type not in ("movie", "tv"):
            raise TMDBError("Unsupported media type.")
        data = await self._request(f"/{media_type}/{tmdb_id}")
        return _to_result(data, media_type)
