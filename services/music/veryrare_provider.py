"""VeryRare media provider: streams audio from the Very Rare Society's own Jellyfin library."""

from config import settings
from services.jellyfin import JellyfinClient, JellyfinError
from services.music.base import MusicProviderError, Track


def _ticks_to_seconds(ticks: int | None) -> int | None:
    return int(ticks / 10_000_000) if ticks else None


class VeryRareMediaProvider:
    """Plays audio directly from the self-hosted Jellyfin library."""

    name = "veryrare"

    def handles(self, query: str) -> bool:
        return False

    def _client(self) -> JellyfinClient:
        try:
            return JellyfinClient.from_settings()
        except JellyfinError as exc:
            raise MusicProviderError(str(exc)) from exc

    def _to_track(self, item: dict, requester_id: int) -> Track:
        artists = item.get("Artists") or []
        return Track(
            title=item.get("Name") or "Unknown title",
            webpage_url=item["Id"],
            duration=_ticks_to_seconds(item.get("RunTimeTicks")),
            requester_id=requester_id,
            source=self.name,
            artist=", ".join(artists) if artists else None,
        )

    async def search(self, query: str, requester_id: int) -> list[Track]:
        client = self._client()
        try:
            items = await client.search_audio(query, limit=settings.MUSIC_SEARCH_RESULTS)
        except JellyfinError as exc:
            raise MusicProviderError(str(exc)) from exc
        if not items:
            raise MusicProviderError("No matching VeryRare media was found.")
        return [self._to_track(item, requester_id) for item in items]

    async def resolve_playlist(self, url: str, requester_id: int) -> list[Track]:
        raise MusicProviderError("VeryRare media does not support playlist links yet; try /play search instead.")

    async def stream_url(self, track: Track) -> str:
        client = self._client()
        return client.stream_url(track.webpage_url)
