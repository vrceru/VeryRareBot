"""Per-guild voice connection and playback loop.

Discord.py's `after=` playback callback runs on a worker thread, so it hands
control back to the bot's event loop via `asyncio.run_coroutine_threadsafe`.
"""

import asyncio
import logging
from typing import Callable

import discord

from config import settings
from services.music.base import MusicProvider, MusicProviderError, Track
from services.music.queue import GuildQueue

logger = logging.getLogger("VeryRareBot")

ProviderLookup = Callable[[str], MusicProvider]


class GuildPlayer:
    """Owns one guild's voice connection, queue, and playback state."""

    def __init__(self, bot: discord.Client, guild_id: int, provider_lookup: ProviderLookup):
        self.bot = bot
        self.guild_id = guild_id
        self.provider_lookup = provider_lookup
        self.queue = GuildQueue(settings.MUSIC_MAX_QUEUE_SIZE, settings.MUSIC_DEFAULT_VOLUME)
        self.voice_client: discord.VoiceClient | None = None
        self.text_channel: discord.abc.Messageable | None = None

        self._lock = asyncio.Lock()
        self._idle_task: asyncio.Task | None = None
        self._skip_requested = False
        self._suppress_after = False

    @property
    def is_connected(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_connected()

    @property
    def is_playing(self) -> bool:
        return bool(self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()))

    async def connect(self, channel: discord.VoiceChannel) -> None:
        self._cancel_idle_timer()
        if self.voice_client and self.voice_client.is_connected():
            await self.voice_client.move_to(channel)
        else:
            self.voice_client = await channel.connect()

    async def disconnect(self) -> None:
        self._cancel_idle_timer()
        self._suppress_after = True
        if self.voice_client:
            await self.voice_client.disconnect(force=True)
        self.voice_client = None
        self.queue.clear()
        self.queue.current = None

    def pause(self) -> None:
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()

    def resume(self) -> None:
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()

    def apply_volume(self) -> None:
        source = self.voice_client.source if self.voice_client else None
        if isinstance(source, discord.PCMVolumeTransformer):
            source.volume = self.queue.volume

    async def stop(self) -> None:
        self._cancel_idle_timer()
        self.queue.clear()
        self.queue.current = None
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self._suppress_after = True
            self.voice_client.stop()
        self._start_idle_timer()

    async def skip(self) -> bool:
        if not self.voice_client or not (self.voice_client.is_playing() or self.voice_client.is_paused()):
            return False
        self._skip_requested = True
        self.voice_client.stop()
        return True

    async def play_next(self) -> None:
        async with self._lock:
            if not self.voice_client or not self.voice_client.is_connected():
                return

            forced = self._skip_requested
            self._skip_requested = False

            track: Track | None = None
            while True:
                track = self.queue.advance(forced=forced)
                forced = False
                if track is None:
                    break
                try:
                    stream_url = await self.provider_lookup(track.source).stream_url(track)
                except MusicProviderError as exc:
                    logger.warning("Skipping unplayable track %r: %s", track.title, exc)
                    if self.text_channel:
                        await self.text_channel.send(f"Skipping **{track.title}** — {exc}")
                    continue
                break

            if track is None:
                self._start_idle_timer()
                return

            self._cancel_idle_timer()
            source = discord.FFmpegPCMAudio(
                stream_url,
                executable=settings.FFMPEG_PATH,
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn",
            )
            volume_source = discord.PCMVolumeTransformer(source, volume=self.queue.volume)
            self.voice_client.play(volume_source, after=self._make_after_callback())

    def _make_after_callback(self):
        loop = self.bot.loop

        def _after(error: Exception | None) -> None:
            if error:
                logger.error("Playback error in guild %s: %s", self.guild_id, error)
            if self._suppress_after:
                self._suppress_after = False
                return
            asyncio.run_coroutine_threadsafe(self._advance_safely(), loop)

        return _after

    async def _advance_safely(self) -> None:
        try:
            await self.play_next()
        except Exception:
            logger.exception("Failed to advance the queue in guild %s", self.guild_id)

    def _start_idle_timer(self) -> None:
        self._cancel_idle_timer()
        if settings.MUSIC_IDLE_DISCONNECT_SECONDS <= 0:
            return
        self._idle_task = asyncio.create_task(self._idle_disconnect())

    def _cancel_idle_timer(self) -> None:
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = None

    async def _idle_disconnect(self) -> None:
        try:
            await asyncio.sleep(settings.MUSIC_IDLE_DISCONNECT_SECONDS)
        except asyncio.CancelledError:
            return
        if self.text_channel:
            await self.text_channel.send("Leaving the voice channel after being idle.")
        await self.disconnect()


class MusicPlayerManager:
    """Holds one GuildPlayer per guild."""

    def __init__(self, bot: discord.Client, provider_lookup: ProviderLookup):
        self.bot = bot
        self.provider_lookup = provider_lookup
        self._players: dict[int, GuildPlayer] = {}

    def get(self, guild_id: int) -> GuildPlayer:
        player = self._players.get(guild_id)
        if player is None:
            player = GuildPlayer(self.bot, guild_id, self.provider_lookup)
            self._players[guild_id] = player
        return player

    def peek(self, guild_id: int) -> GuildPlayer | None:
        return self._players.get(guild_id)

    async def remove(self, guild_id: int) -> None:
        player = self._players.pop(guild_id, None)
        if player:
            await player.disconnect()
