import discord
from discord import app_commands
from discord.ext import commands

from core.embed import error_embed, music_embed, success_embed
from services.music import MusicProviderError
from services.music.player import MusicPlayerManager
from services.music.queue import LoopMode
from services.music.registry import PROVIDERS, resolve_provider

SOURCE_CHOICES = [
    app_commands.Choice(name="Auto-detect", value="auto"),
    app_commands.Choice(name="YouTube", value="youtube"),
    app_commands.Choice(name="SoundCloud", value="soundcloud"),
    app_commands.Choice(name="VeryRare Media", value="veryrare"),
]

LOOP_CHOICES = [
    app_commands.Choice(name="Off", value="off"),
    app_commands.Choice(name="Track", value="track"),
    app_commands.Choice(name="Queue", value="queue"),
]


def format_duration(seconds: int | None) -> str:
    if not seconds:
        return "Live/unknown"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class Music(commands.Cog):
    """Multi-source music playback: YouTube, SoundCloud, and VeryRare media."""

    music = app_commands.Group(name="music", description="Music playback commands.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players = MusicPlayerManager(bot, lambda source: PROVIDERS[source])

    async def cog_unload(self) -> None:
        for guild in list(self.bot.guilds):
            player = self.players.peek(guild.id)
            if player:
                await player.disconnect()

    def _member_voice_channel(self, interaction: discord.Interaction) -> discord.VoiceChannel | None:
        user = interaction.user
        if isinstance(user, discord.Member) and user.voice:
            return user.voice.channel
        return None

    async def _ensure_voice(self, interaction: discord.Interaction) -> bool:
        """Connect the bot to the user's voice channel if needed. Returns False and
        replies with an error if that isn't possible."""

        channel = self._member_voice_channel(interaction)
        if channel is None:
            await interaction.response.send_message(
                embed=error_embed("Join a Voice Channel", "You need to be in a voice channel first."),
                ephemeral=True,
            )
            return False

        player = self.players.get(interaction.guild_id)
        if player.is_connected and player.voice_client.channel.id != channel.id:
            await interaction.response.send_message(
                embed=error_embed("Already Playing Elsewhere", f"I'm already active in {player.voice_client.channel.mention}."),
                ephemeral=True,
            )
            return False

        if not player.is_connected:
            await player.connect(channel)
        player.text_channel = interaction.channel
        return True

    def _require_player(self, interaction: discord.Interaction):
        return self.players.peek(interaction.guild_id)

    @music.command(name="join", description="Join your current voice channel.")
    async def join(self, interaction: discord.Interaction):
        if not await self._ensure_voice(interaction):
            return
        channel = self._member_voice_channel(interaction)
        await interaction.response.send_message(embed=success_embed("Joined", f"Connected to {channel.mention}."), ephemeral=True)

    @music.command(name="leave", description="Disconnect from voice and clear the queue.")
    async def leave(self, interaction: discord.Interaction):
        player = self._require_player(interaction)
        if not player or not player.is_connected:
            await interaction.response.send_message(embed=error_embed("Not Connected", "I'm not in a voice channel."), ephemeral=True)
            return
        await player.disconnect()
        await interaction.response.send_message(embed=success_embed("Disconnected", "Left the voice channel."), ephemeral=True)

    @music.command(name="play", description="Play or queue a track by search term or URL.")
    @app_commands.describe(query="Search terms or a YouTube/SoundCloud URL.", source="Where to look. Defaults to auto-detecting from the query.")
    @app_commands.choices(source=SOURCE_CHOICES)
    async def play(self, interaction: discord.Interaction, query: str, source: app_commands.Choice[str] | None = None):
        if not await self._ensure_voice(interaction):
            return

        await interaction.response.defer(thinking=True)
        source_name = None if source is None or source.value == "auto" else source.value

        try:
            provider = resolve_provider(query, source_name)
            tracks = await provider.search(query, interaction.user.id)
        except (MusicProviderError, ValueError) as exc:
            await interaction.followup.send(embed=error_embed("Music Error", str(exc)))
            return

        is_playlist = provider.handles(query)
        to_enqueue = tracks if is_playlist else tracks[:1]

        player = self._require_player(interaction)
        try:
            added = player.queue.enqueue_many(to_enqueue)
        except MusicProviderError as exc:
            await interaction.followup.send(embed=error_embed("Queue Full", str(exc)))
            return

        if not player.is_playing:
            await player.play_next()

        if added == 1:
            await interaction.followup.send(embed=success_embed("Added to Queue", f"**{to_enqueue[0].title}** from {provider.name}."))
        else:
            await interaction.followup.send(embed=success_embed("Playlist Queued", f"Added {added} tracks from {provider.name}."))

    @music.command(name="search", description="Search a source without queueing anything.")
    @app_commands.describe(query="Search terms.", source="Where to search.")
    @app_commands.choices(source=SOURCE_CHOICES)
    async def search(self, interaction: discord.Interaction, query: str, source: app_commands.Choice[str] | None = None):
        await interaction.response.defer(thinking=True, ephemeral=True)
        source_name = None if source is None or source.value == "auto" else source.value
        try:
            provider = resolve_provider(query, source_name or "youtube")
            tracks = await provider.search(query, interaction.user.id)
        except (MusicProviderError, ValueError) as exc:
            await interaction.followup.send(embed=error_embed("Music Error", str(exc)))
            return

        embed = music_embed(f"Search Results: {query}")
        for index, track in enumerate(tracks[:10], start=1):
            embed.add_field(name=f"{index}. {track.title}", value=f"{track.source} • {format_duration(track.duration)}", inline=False)
        await interaction.followup.send(embed=embed)

    @music.command(name="pause", description="Pause playback.")
    async def pause(self, interaction: discord.Interaction):
        player = self._require_player(interaction)
        if not player or not player.is_playing:
            await interaction.response.send_message(embed=error_embed("Nothing Playing", "There's nothing to pause."), ephemeral=True)
            return
        player.pause()
        await interaction.response.send_message(embed=success_embed("Paused"), ephemeral=True)

    @music.command(name="resume", description="Resume playback.")
    async def resume(self, interaction: discord.Interaction):
        player = self._require_player(interaction)
        if not player or not player.is_connected:
            await interaction.response.send_message(embed=error_embed("Not Connected", "I'm not in a voice channel."), ephemeral=True)
            return
        player.resume()
        await interaction.response.send_message(embed=success_embed("Resumed"), ephemeral=True)

    @music.command(name="stop", description="Stop playback and clear the queue.")
    async def stop(self, interaction: discord.Interaction):
        player = self._require_player(interaction)
        if not player or not player.is_connected:
            await interaction.response.send_message(embed=error_embed("Not Connected", "I'm not in a voice channel."), ephemeral=True)
            return
        await player.stop()
        await interaction.response.send_message(embed=success_embed("Stopped", "Playback stopped and queue cleared."), ephemeral=True)

    @music.command(name="skip", description="Skip the current track.")
    async def skip(self, interaction: discord.Interaction):
        player = self._require_player(interaction)
        if not player or not player.is_playing:
            await interaction.response.send_message(embed=error_embed("Nothing Playing", "There's nothing to skip."), ephemeral=True)
            return
        skipped_title = player.queue.current.title if player.queue.current else "the current track"
        await player.skip()
        await interaction.response.send_message(embed=success_embed("Skipped", f"Skipped **{skipped_title}**."), ephemeral=True)

    @music.command(name="queue", description="Show the current queue.")
    async def queue(self, interaction: discord.Interaction):
        player = self._require_player(interaction)
        if not player or (not player.queue.current and not player.queue.upcoming):
            await interaction.response.send_message(embed=error_embed("Queue Empty", "Nothing is queued."), ephemeral=True)
            return

        embed = music_embed("Music Queue")
        if player.queue.current:
            embed.add_field(name="Now Playing", value=f"{player.queue.current.title} ({format_duration(player.queue.current.duration)})", inline=False)
        upcoming = player.queue.upcoming[:15]
        if upcoming:
            lines = [f"{i}. {track.title} ({format_duration(track.duration)})" for i, track in enumerate(upcoming, start=1)]
            embed.add_field(name="Up Next", value="\n".join(lines), inline=False)
        remaining = len(player.queue) - len(upcoming)
        if remaining > 0:
            embed.add_field(name="​", value=f"…and {remaining} more.", inline=False)
        embed.add_field(name="Loop", value=player.queue.loop_mode.value.title(), inline=True)
        embed.add_field(name="Volume", value=f"{int(player.queue.volume * 100)}%", inline=True)
        await interaction.response.send_message(embed=embed)

    @music.command(name="remove", description="Remove a track from the queue by position.")
    @app_commands.describe(position="Position shown in /music queue (1 is next up).")
    async def remove(self, interaction: discord.Interaction, position: int):
        player = self._require_player(interaction)
        if not player:
            await interaction.response.send_message(embed=error_embed("Queue Empty", "Nothing is queued."), ephemeral=True)
            return
        try:
            track = player.queue.remove(position)
        except IndexError:
            await interaction.response.send_message(embed=error_embed("Invalid Position", "That queue position doesn't exist."), ephemeral=True)
            return
        await interaction.response.send_message(embed=success_embed("Removed", f"Removed **{track.title}** from the queue."), ephemeral=True)

    @music.command(name="shuffle", description="Shuffle the upcoming queue.")
    async def shuffle(self, interaction: discord.Interaction):
        player = self._require_player(interaction)
        if not player or len(player.queue) < 2:
            await interaction.response.send_message(embed=error_embed("Nothing to Shuffle", "Need at least two queued tracks."), ephemeral=True)
            return
        player.queue.shuffle()
        await interaction.response.send_message(embed=success_embed("Shuffled", "Queue order shuffled."), ephemeral=True)

    @music.command(name="loop", description="Set the loop mode.")
    @app_commands.choices(mode=LOOP_CHOICES)
    async def loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        player = self._require_player(interaction)
        if not player:
            await interaction.response.send_message(embed=error_embed("Not Connected", "I'm not in a voice channel."), ephemeral=True)
            return
        player.queue.loop_mode = LoopMode(mode.value)
        await interaction.response.send_message(embed=success_embed("Loop Updated", f"Loop mode set to **{mode.name}**."), ephemeral=True)

    @music.command(name="volume", description="Set playback volume (0-200%).")
    @app_commands.describe(percent="Volume percentage from 0 to 200.")
    async def volume(self, interaction: discord.Interaction, percent: app_commands.Range[int, 0, 200]):
        player = self._require_player(interaction)
        if not player:
            await interaction.response.send_message(embed=error_embed("Not Connected", "I'm not in a voice channel."), ephemeral=True)
            return
        new_volume = player.queue.set_volume(percent / 100)
        player.apply_volume()
        await interaction.response.send_message(embed=success_embed("Volume Updated", f"Volume set to **{int(new_volume * 100)}%**."), ephemeral=True)

    @music.command(name="nowplaying", description="Show the currently playing track.")
    async def now_playing(self, interaction: discord.Interaction):
        player = self._require_player(interaction)
        if not player or not player.queue.current:
            await interaction.response.send_message(embed=error_embed("Nothing Playing", "Nothing is currently playing."), ephemeral=True)
            return
        track = player.queue.current
        embed = music_embed("Now Playing", track.title)
        embed.add_field(name="Source", value=track.source, inline=True)
        embed.add_field(name="Duration", value=format_duration(track.duration), inline=True)
        embed.add_field(name="Requested By", value=f"<@{track.requester_id}>", inline=True)
        if track.artist:
            embed.add_field(name="Artist", value=track.artist, inline=True)
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.id == self.bot.user.id:
            return
        player = self.players.peek(member.guild.id)
        if not player or not player.is_connected:
            return
        channel = player.voice_client.channel
        if before.channel != channel and after.channel != channel:
            return
        remaining_humans = [m for m in channel.members if not m.bot]
        if not remaining_humans:
            await player.stop()
            await player.disconnect()


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
