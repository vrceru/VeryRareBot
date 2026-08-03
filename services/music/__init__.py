"""Provider-agnostic music playback services."""

from services.music.base import MusicProviderError, Track
from services.music.registry import resolve_provider

__all__ = ["MusicProviderError", "Track", "resolve_provider"]
