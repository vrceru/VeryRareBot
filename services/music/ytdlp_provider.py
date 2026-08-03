"""YouTube and SoundCloud playback via yt-dlp.

yt-dlp only ever extracts metadata and a direct media URL here; the bot never
downloads or stores media, it streams the resolved URL straight into Discord
voice through ffmpeg.
"""

import asyncio
from typing import Any
from urllib.parse import urlparse

import yt_dlp

from config import settings
from services.music.base import MusicProviderError, Track

_YDL_BASE_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "ignoreerrors": False,
    "source_address": "0.0.0.0",
    "skip_download": True,
    "extract_flat": False,
}


class YtDlpProvider:
    """Base provider backed by yt-dlp; subclasses select the search engine and domains."""

    name = "ytdlp"
    search_prefix = "ytsearch"
    domains: tuple[str, ...] = ()

    async def _extract(self, query: str, *, flat: bool = False) -> dict[str, Any]:
        opts = {**_YDL_BASE_OPTS, "extract_flat": "in_playlist" if flat else False}
        loop = asyncio.get_running_loop()

        def run() -> dict[str, Any]:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(query, download=False)

        try:
            info = await loop.run_in_executor(None, run)
        except yt_dlp.utils.DownloadError as exc:
            raise MusicProviderError(f"Could not load that {self.name} media.") from exc

        if not info:
            raise MusicProviderError(f"No {self.name} results were found.")
        return info

    def handles(self, query: str) -> bool:
        try:
            host = urlparse(query).netloc.lower()
        except ValueError:
            return False
        return any(host == domain or host.endswith(f".{domain}") for domain in self.domains)

    def _to_track(self, entry: dict[str, Any], requester_id: int) -> Track:
        webpage_url = entry.get("webpage_url") or entry.get("url")
        if not webpage_url:
            raise MusicProviderError(f"A {self.name} result was missing a playable URL.")
        return Track(
            title=entry.get("title") or "Unknown title",
            webpage_url=webpage_url,
            duration=entry.get("duration"),
            requester_id=requester_id,
            source=self.name,
            thumbnail=entry.get("thumbnail"),
            artist=entry.get("uploader") or entry.get("artist"),
        )

    async def search(self, query: str, requester_id: int) -> list[Track]:
        if self.handles(query):
            return await self.resolve_playlist(query, requester_id)

        info = await self._extract(f"{self.search_prefix}{settings.MUSIC_SEARCH_RESULTS}:{query}")
        entries = info.get("entries") or [info]
        return [self._to_track(entry, requester_id) for entry in entries if entry]

    async def resolve_playlist(self, url: str, requester_id: int) -> list[Track]:
        info = await self._extract(url, flat=True)
        entries = info.get("entries") or [info]
        tracks = []
        for entry in entries[: settings.MUSIC_MAX_QUEUE_SIZE]:
            if not entry:
                continue
            tracks.append(self._to_track(entry, requester_id))
        if not tracks:
            raise MusicProviderError(f"No playable {self.name} tracks were found.")
        return tracks

    async def stream_url(self, track: Track) -> str:
        info = await self._extract(track.webpage_url)
        url = info.get("url")
        if url:
            return url

        formats = info.get("formats") or []
        audio_formats = [f for f in formats if f.get("acodec") not in (None, "none") and f.get("url")]
        if not audio_formats:
            raise MusicProviderError("No playable audio stream was found for that track.")
        return audio_formats[-1]["url"]


class YouTubeProvider(YtDlpProvider):
    name = "youtube"
    search_prefix = "ytsearch"
    domains = ("youtube.com", "youtu.be", "music.youtube.com")


class SoundCloudProvider(YtDlpProvider):
    name = "soundcloud"
    search_prefix = "scsearch"
    domains = ("soundcloud.com", "snd.sc")
