"""Resolves which music provider should handle a given request."""

from services.music.base import MusicProvider
from services.music.veryrare_provider import VeryRareMediaProvider
from services.music.ytdlp_provider import SoundCloudProvider, YouTubeProvider

PROVIDERS: dict[str, MusicProvider] = {
    "youtube": YouTubeProvider(),
    "soundcloud": SoundCloudProvider(),
    "veryrare": VeryRareMediaProvider(),
}

DEFAULT_PROVIDER = "youtube"


def resolve_provider(query: str, source: str | None = None) -> MusicProvider:
    """Pick a provider by explicit name, or by sniffing the query for a known URL."""

    if source:
        provider = PROVIDERS.get(source)
        if provider is None:
            raise ValueError(f"Unknown music source: {source}")
        return provider

    for provider in PROVIDERS.values():
        if provider.handles(query):
            return provider

    return PROVIDERS[DEFAULT_PROVIDER]
