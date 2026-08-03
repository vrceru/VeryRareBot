import tempfile
import unittest
from pathlib import Path

from services.database import Database
from services.music.base import Track


def make_track(title: str) -> Track:
    return Track(title=title, webpage_url=f"https://example.com/{title}", duration=42, requester_id=1, source="youtube")


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self._tmpdir.name) / "test.sqlite3"))
        await self.db.connect()

    async def asyncTearDown(self):
        await self.db.close()
        self._tmpdir.cleanup()

    async def test_add_and_list_warnings(self):
        await self.db.add_warning(guild_id=1, user_id=2, moderator_id=3, reason="spam")
        await self.db.add_warning(guild_id=1, user_id=2, moderator_id=3, reason="more spam")
        warnings = await self.db.list_warnings(guild_id=1, user_id=2)
        self.assertEqual(len(warnings), 2)
        self.assertEqual(warnings[0]["reason"], "more spam")

    async def test_warnings_are_scoped_per_guild(self):
        await self.db.add_warning(guild_id=1, user_id=2, moderator_id=3, reason="spam")
        other_guild = await self.db.list_warnings(guild_id=99, user_id=2)
        self.assertEqual(other_guild, [])

    async def test_clear_warnings(self):
        await self.db.add_warning(guild_id=1, user_id=2, moderator_id=3, reason="spam")
        deleted = await self.db.clear_warnings(guild_id=1, user_id=2)
        self.assertEqual(deleted, 1)
        self.assertEqual(await self.db.list_warnings(guild_id=1, user_id=2), [])

    async def test_save_and_load_playlist(self):
        tracks = [make_track("a"), make_track("b")]
        await self.db.save_playlist(guild_id=1, owner_id=2, name="chill", tracks=tracks)
        loaded = await self.db.load_playlist(guild_id=1, owner_id=2, name="chill", requester_id=5)
        self.assertEqual([t.title for t in loaded], ["a", "b"])
        self.assertTrue(all(t.requester_id == 5 for t in loaded))

    async def test_save_playlist_overwrites_existing(self):
        await self.db.save_playlist(guild_id=1, owner_id=2, name="chill", tracks=[make_track("a")])
        await self.db.save_playlist(guild_id=1, owner_id=2, name="chill", tracks=[make_track("b"), make_track("c")])
        loaded = await self.db.load_playlist(guild_id=1, owner_id=2, name="chill", requester_id=5)
        self.assertEqual([t.title for t in loaded], ["b", "c"])

    async def test_load_missing_playlist_returns_none(self):
        loaded = await self.db.load_playlist(guild_id=1, owner_id=2, name="missing", requester_id=5)
        self.assertIsNone(loaded)

    async def test_list_and_delete_playlists(self):
        await self.db.save_playlist(guild_id=1, owner_id=2, name="chill", tracks=[make_track("a")])
        await self.db.save_playlist(guild_id=1, owner_id=2, name="party", tracks=[make_track("b")])
        self.assertEqual(await self.db.list_playlists(guild_id=1, owner_id=2), ["chill", "party"])
        self.assertTrue(await self.db.delete_playlist(guild_id=1, owner_id=2, name="chill"))
        self.assertEqual(await self.db.list_playlists(guild_id=1, owner_id=2), ["party"])
        self.assertFalse(await self.db.delete_playlist(guild_id=1, owner_id=2, name="chill"))


if __name__ == "__main__":
    unittest.main()
