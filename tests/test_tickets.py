import tempfile
import unittest
from pathlib import Path

from services.database import Database
from services.tickets import TICKET_CATEGORIES, channel_slug


class ChannelSlugTests(unittest.TestCase):
    def test_sanitizes_special_characters(self):
        self.assertEqual(channel_slug("signup", "Cool User!! 123"), "ticket-signup-cool-user-123")

    def test_truncates_to_discord_limit(self):
        slug = channel_slug("bug", "x" * 200)
        self.assertLessEqual(len(slug), 100)


class TicketCategoryRegistryTests(unittest.TestCase):
    def test_expected_categories_present(self):
        self.assertEqual(set(TICKET_CATEGORIES.keys()), {"signup", "bug", "password", "appeal", "other"})

    def test_every_category_has_five_or_fewer_fields(self):
        for category in TICKET_CATEGORIES.values():
            self.assertLessEqual(len(category.fields), 5, f"{category.key} exceeds Discord's 5-field modal limit")


class TicketDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self._tmpdir.name) / "test.sqlite3"))
        await self.db.connect()

    async def asyncTearDown(self):
        await self.db.close()
        self._tmpdir.cleanup()

    async def test_create_and_fetch_ticket(self):
        ticket_id = await self.db.create_ticket(guild_id=1, channel_id=100, opener_id=2, category="bug")
        ticket = await self.db.get_ticket_by_channel(100)
        self.assertEqual(ticket["id"], ticket_id)
        self.assertEqual(ticket["status"], "open")
        self.assertEqual(ticket["category"], "bug")

    async def test_count_open_tickets_only_counts_open(self):
        await self.db.create_ticket(guild_id=1, channel_id=100, opener_id=2, category="bug")
        await self.db.create_ticket(guild_id=1, channel_id=101, opener_id=2, category="other")
        self.assertEqual(await self.db.count_open_tickets(1, 2), 2)

        await self.db.close_ticket(100, closed_by_id=2)
        self.assertEqual(await self.db.count_open_tickets(1, 2), 1)

    async def test_close_ticket_is_idempotent(self):
        await self.db.create_ticket(guild_id=1, channel_id=100, opener_id=2, category="bug")
        self.assertTrue(await self.db.close_ticket(100, closed_by_id=2))
        self.assertFalse(await self.db.close_ticket(100, closed_by_id=2))

    async def test_get_ticket_for_unknown_channel_returns_none(self):
        self.assertIsNone(await self.db.get_ticket_by_channel(999))


if __name__ == "__main__":
    unittest.main()
