"""Per-guild playback queue and loop/volume state, independent of any Discord/voice APIs."""

import random
from enum import Enum

from services.music.base import MusicProviderError, Track

MIN_VOLUME = 0.0
MAX_VOLUME = 2.0
HISTORY_LIMIT = 20


class LoopMode(Enum):
    OFF = "off"
    TRACK = "track"
    QUEUE = "queue"


class GuildQueue:
    """Tracks what a single guild is playing, queued, and its playback settings."""

    def __init__(self, max_size: int, default_volume: float):
        self.max_size = max_size
        self.volume = max(MIN_VOLUME, min(MAX_VOLUME, default_volume))
        self.loop_mode = LoopMode.OFF
        self.current: Track | None = None
        self._upcoming: list[Track] = []
        self._history: list[Track] = []

    def __len__(self) -> int:
        return len(self._upcoming)

    @property
    def upcoming(self) -> list[Track]:
        return list(self._upcoming)

    def enqueue(self, track: Track) -> None:
        if len(self._upcoming) >= self.max_size:
            raise MusicProviderError(f"Queue is full (max {self.max_size} tracks).")
        self._upcoming.append(track)

    def enqueue_many(self, tracks: list[Track]) -> int:
        added = 0
        for track in tracks:
            if len(self._upcoming) >= self.max_size:
                break
            self._upcoming.append(track)
            added += 1
        return added

    def remove(self, position: int) -> Track:
        """Remove a 1-indexed queue entry as shown by /music queue."""
        index = position - 1
        if index < 0 or index >= len(self._upcoming):
            raise IndexError(position)
        return self._upcoming.pop(index)

    def shuffle(self) -> None:
        random.shuffle(self._upcoming)

    def clear(self) -> None:
        self._upcoming.clear()
        self._history.clear()

    def set_volume(self, value: float) -> float:
        self.volume = max(MIN_VOLUME, min(MAX_VOLUME, value))
        return self.volume

    def has_previous(self) -> bool:
        return bool(self._history)

    def go_back(self) -> Track | None:
        """Move the last history entry back into `current`, pushing whatever was
        playing back onto the front of the upcoming queue."""

        if not self._history:
            return None

        if self.current is not None:
            self._upcoming.insert(0, self.current)

        self.current = self._history.pop()
        return self.current

    def advance(self, *, forced: bool = False) -> Track | None:
        """Move to the next track. `forced` is True for an explicit /skip, which
        always moves forward even during single-track loop."""

        if not forced and self.loop_mode == LoopMode.TRACK and self.current:
            return self.current

        previous = self.current
        if previous is not None:
            self._history.append(previous)
            if len(self._history) > HISTORY_LIMIT:
                self._history.pop(0)

        if self.loop_mode == LoopMode.QUEUE and previous:
            self._upcoming.append(previous)

        self.current = self._upcoming.pop(0) if self._upcoming else None
        return self.current
