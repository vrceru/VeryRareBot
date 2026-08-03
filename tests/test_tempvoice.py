import tempfile
import unittest
from pathlib import Path

from services.database import Database


class TempVoiceConfigTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self._tmpdir.name) / "test.sqlite3"))
        await self.db.connect()

    async def asyncTearDown(self):
        await self.db.close()
        self._tmpdir.cleanup()

    async def test_no_config_initially(self):
        self.assertIsNone(await self.db.get_tempvoice_config(1))

    async def test_set_and_get_config(self):
        await self.db.set_tempvoice_config(guild_id=1, trigger_channel_id=100, category_id=200)
        config = await self.db.get_tempvoice_config(1)
        self.assertEqual(config["trigger_channel_id"], 100)
        self.assertEqual(config["category_id"], 200)

    async def test_set_config_upserts_rather_than_duplicating(self):
        await self.db.set_tempvoice_config(guild_id=1, trigger_channel_id=100, category_id=200)
        await self.db.set_tempvoice_config(guild_id=1, trigger_channel_id=999, category_id=None)
        config = await self.db.get_tempvoice_config(1)
        self.assertEqual(config["trigger_channel_id"], 999)
        self.assertIsNone(config["category_id"])

    async def test_config_is_scoped_per_guild(self):
        await self.db.set_tempvoice_config(guild_id=1, trigger_channel_id=100, category_id=None)
        self.assertIsNone(await self.db.get_tempvoice_config(2))

    async def test_clear_config(self):
        await self.db.set_tempvoice_config(guild_id=1, trigger_channel_id=100, category_id=None)
        self.assertTrue(await self.db.clear_tempvoice_config(1))
        self.assertIsNone(await self.db.get_tempvoice_config(1))
        self.assertFalse(await self.db.clear_tempvoice_config(1))


class TempVoiceChannelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self._tmpdir.name) / "test.sqlite3"))
        await self.db.connect()

    async def asyncTearDown(self):
        await self.db.close()
        self._tmpdir.cleanup()

    async def test_create_and_fetch(self):
        await self.db.create_tempvoice_channel(channel_id=500, guild_id=1, owner_id=2)
        row = await self.db.get_tempvoice_channel(500)
        self.assertEqual(row["owner_id"], 2)
        self.assertEqual(row["guild_id"], 1)

    async def test_unknown_channel_returns_none(self):
        self.assertIsNone(await self.db.get_tempvoice_channel(999))

    async def test_claim_changes_owner(self):
        await self.db.create_tempvoice_channel(channel_id=500, guild_id=1, owner_id=2)
        await self.db.set_tempvoice_owner(500, 3)
        row = await self.db.get_tempvoice_channel(500)
        self.assertEqual(row["owner_id"], 3)

    async def test_delete_removes_record(self):
        await self.db.create_tempvoice_channel(channel_id=500, guild_id=1, owner_id=2)
        await self.db.delete_tempvoice_channel(500)
        self.assertIsNone(await self.db.get_tempvoice_channel(500))


if __name__ == "__main__":
    unittest.main()
