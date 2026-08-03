import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cogs.media import STATUS_LABELS, TRANSITIONS, MediaActionButton, build_status_view
from services.database import Database
from services.tmdb import TMDBClient, TMDBError, _to_result


class TMDBParsingTests(unittest.TestCase):
    def test_movie_result_uses_release_date_year(self):
        result = _to_result(
            {"id": 550, "title": "Fight Club", "release_date": "1999-10-15", "overview": "x", "poster_path": "/abc.jpg"},
            "movie",
        )
        self.assertEqual(result.year, "1999")
        self.assertEqual(result.poster_url, "https://image.tmdb.org/t/p/w500/abc.jpg")

    def test_tv_result_uses_first_air_date_and_name(self):
        result = _to_result({"id": 1399, "name": "Game of Thrones", "first_air_date": "2011-04-17"}, "tv")
        self.assertEqual(result.title, "Game of Thrones")
        self.assertEqual(result.year, "2011")

    def test_missing_dates_and_poster_are_none(self):
        result = _to_result({"id": 1, "title": "Untitled"}, "movie")
        self.assertIsNone(result.year)
        self.assertIsNone(result.poster_url)

    def test_from_settings_requires_api_key(self):
        with patch("services.tmdb.settings.TMDB_API_KEY", ""):
            with self.assertRaises(TMDBError):
                TMDBClient.from_settings()


class MediaActionButtonTemplateTests(unittest.TestCase):
    def test_custom_id_matches_template(self):
        pattern = MediaActionButton.__discord_ui_compiled_template__
        match = pattern.fullmatch("media:approve:42")
        self.assertIsNotNone(match)
        self.assertEqual(match["action"], "approve")
        self.assertEqual(match["request_id"], "42")

    def test_non_media_custom_id_does_not_match(self):
        pattern = MediaActionButton.__discord_ui_compiled_template__
        self.assertIsNone(pattern.fullmatch("ticket:close"))


class StatusViewTests(unittest.TestCase):
    def test_pending_has_three_actions(self):
        view = build_status_view(1, "pending")
        self.assertEqual(len(view.children), 3)

    def test_terminal_statuses_have_no_actions(self):
        for status in ("completed", "denied", "cancelled"):
            view = build_status_view(1, status)
            self.assertEqual(len(view.children), 0)

    def test_every_transition_target_has_a_label(self):
        for action, (new_status, _) in TRANSITIONS.items():
            self.assertIn(new_status, STATUS_LABELS, f"{action} transitions to an unlabeled status")


class MediaDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self._tmpdir.name) / "test.sqlite3"))
        await self.db.connect()

    async def asyncTearDown(self):
        await self.db.close()
        self._tmpdir.cleanup()

    async def test_create_and_fetch(self):
        request_id = await self.db.create_media_request(1, 2, "movie", 550, "Fight Club", "1999", None, None, None)
        request = await self.db.get_media_request(request_id)
        self.assertEqual(request["status"], "pending")
        self.assertEqual(request["title"], "Fight Club")

    async def test_active_request_blocks_duplicate(self):
        await self.db.create_media_request(1, 2, "movie", 550, "Fight Club", "1999", None, None, None)
        existing = await self.db.get_active_media_request(1, 550, "movie")
        self.assertIsNotNone(existing)

    async def test_denied_request_is_not_active(self):
        request_id = await self.db.create_media_request(1, 2, "movie", 550, "Fight Club", "1999", None, None, None)
        await self.db.update_media_request_status(request_id, "denied", reviewer_id=9)
        self.assertIsNone(await self.db.get_active_media_request(1, 550, "movie"))

    async def test_list_media_requests_filters_by_status_and_guild(self):
        await self.db.create_media_request(1, 2, "movie", 1, "A", None, None, None, None)
        await self.db.create_media_request(1, 2, "movie", 2, "B", None, None, None, None)
        await self.db.create_media_request(99, 2, "movie", 3, "C", None, None, None, None)

        pending = await self.db.list_media_requests(1, ["pending"])
        self.assertEqual({r["title"] for r in pending}, {"A", "B"})

    async def test_update_status_preserves_reviewer_when_none_passed(self):
        request_id = await self.db.create_media_request(1, 2, "movie", 550, "Fight Club", "1999", None, None, None)
        await self.db.update_media_request_status(request_id, "approved", reviewer_id=5)
        await self.db.update_media_request_status(request_id, "downloading")
        request = await self.db.get_media_request(request_id)
        self.assertEqual(request["reviewer_id"], 5)
        self.assertEqual(request["status"], "downloading")


if __name__ == "__main__":
    unittest.main()
