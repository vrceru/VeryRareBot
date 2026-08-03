import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cogs.media import (
    STATUS_LABELS,
    TRANSITIONS,
    MediaActionButton,
    ReleaseWithinSeasonSelect,
    SeasonPickerSelect,
    VRMSGateButton,
    _find_top_release_candidate,
    _group_candidates_by_season,
    _within_season_option_text,
    build_final_gate_embed,
    build_gate_view,
    build_release_gate_embed,
    build_status_view,
)
from services.database import Database
from services.tmdb import TMDBClient, TMDBError, _to_result, _is_anime


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

    def test_search_result_flags_japanese_animation_as_anime(self):
        result = _to_result(
            {"id": 127532, "name": "Solo Leveling", "genre_ids": [16, 10759, 10765], "origin_country": ["JP"]},
            "tv",
        )
        self.assertTrue(result.is_anime)

    def test_details_result_flags_japanese_animation_as_anime(self):
        # /tv/{id} details shape: full genre objects, not bare ids.
        result = _to_result(
            {"id": 127532, "name": "Solo Leveling", "genres": [{"id": 16, "name": "Animation"}], "origin_country": ["JP"]},
            "tv",
        )
        self.assertTrue(result.is_anime)

    def test_western_animation_is_not_anime(self):
        result = _to_result({"id": 1, "name": "Rick and Morty", "genre_ids": [16], "origin_country": ["US"]}, "tv")
        self.assertFalse(result.is_anime)

    def test_non_animated_japanese_show_is_not_anime(self):
        result = _to_result({"id": 1, "name": "Terrace House", "genre_ids": [99], "origin_country": ["JP"]}, "tv")
        self.assertFalse(result.is_anime)

    def test_movies_are_never_flagged_anime_regardless_of_genre(self):
        result = _to_result(
            {"id": 1, "title": "Some Anime Movie", "genre_ids": [16], "origin_country": ["JP"]}, "movie"
        )
        self.assertFalse(result.is_anime)

    def test_is_anime_handles_missing_fields(self):
        self.assertFalse(_is_anime({"id": 1}, "tv"))


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


def make_request_row(status: str, vrms_job_id: str | None = None) -> dict:
    return {"id": 1, "status": status, "vrms_job_id": vrms_job_id}


class StatusViewTests(unittest.TestCase):
    def test_pending_has_three_actions(self):
        view = build_status_view(make_request_row("pending"))
        self.assertEqual(len(view.children), 3)

    def test_terminal_statuses_have_no_actions(self):
        for status in ("completed", "denied", "cancelled", "failed"):
            view = build_status_view(make_request_row(status))
            self.assertEqual(len(view.children), 0)

    def test_approved_without_vrms_job_shows_manual_downloading_button(self):
        view = build_status_view(make_request_row("approved"))
        actions = {child.action for child in view.children}
        self.assertIn("downloading", actions)

    def test_approved_with_vrms_job_hides_manual_downloading_button(self):
        view = build_status_view(make_request_row("approved", vrms_job_id="job-123"))
        actions = {child.action for child in view.children}
        self.assertNotIn("downloading", actions)
        self.assertIn("deny", actions)

    def test_downloading_with_vrms_job_has_no_manual_buttons(self):
        view = build_status_view(make_request_row("downloading", vrms_job_id="job-123"))
        self.assertEqual(len(view.children), 0)

    def test_every_transition_target_has_a_label(self):
        for action, (new_status, _) in TRANSITIONS.items():
            self.assertIn(new_status, STATUS_LABELS, f"{action} transitions to an unlabeled status")


class VRMSGateButtonTemplateTests(unittest.TestCase):
    def test_custom_id_matches_template(self):
        pattern = VRMSGateButton.__discord_ui_compiled_template__
        match = pattern.fullmatch("vrms_gate:release:approve:42")
        self.assertIsNotNone(match)
        self.assertEqual(match["gate"], "release")
        self.assertEqual(match["action"], "approve")
        self.assertEqual(match["request_id"], "42")

    def test_does_not_collide_with_media_action_template(self):
        pattern = VRMSGateButton.__discord_ui_compiled_template__
        self.assertIsNone(pattern.fullmatch("media:approve:42"))

    def test_gate_view_has_two_buttons(self):
        view = build_gate_view("final", 1)
        self.assertEqual(len(view.children), 2)

    def test_release_gate_view_adds_season_picker_with_multiple_seasons(self):
        candidates = [
            {"id": "a", "title": "A", "parsed": {"season": 1}},
            {"id": "b", "title": "B", "parsed": {"season": 2}},
        ]
        view = build_gate_view("release", 1, candidates, "a")
        self.assertEqual(len(view.children), 3)
        self.assertIsInstance(view.children[0], SeasonPickerSelect)

    def test_release_gate_view_skips_straight_to_release_picker_with_one_season(self):
        # Nothing to disambiguate at the season level (a single season, or a movie/season-less
        # pool) -- skip step 1 and go straight to picking a specific release.
        candidates = [
            {"id": "a", "title": "A", "parsed": {"season": 1}, "seeders": 10},
            {"id": "b", "title": "B", "parsed": {"season": 1}, "seeders": 20},
        ]
        view = build_gate_view("release", 1, candidates, "a")
        self.assertEqual(len(view.children), 3)
        self.assertIsInstance(view.children[0], ReleaseWithinSeasonSelect)

    def test_release_gate_view_skips_picker_with_one_or_no_candidates(self):
        view = build_gate_view("release", 1, [{"id": "a", "title": "A", "parsed": {}}], "a")
        self.assertEqual(len(view.children), 2)
        view = build_gate_view("release", 1, [], None)
        self.assertEqual(len(view.children), 2)


class SeasonPickerSelectTests(unittest.TestCase):
    def test_lists_each_season_with_a_release_count(self):
        groups = _group_candidates_by_season(
            [
                {"id": "a", "title": "A", "parsed": {"season": 1}},
                {"id": "b", "title": "B", "parsed": {"season": 1}},
                {"id": "c", "title": "C", "parsed": {"season": 2}},
            ]
        )
        select = SeasonPickerSelect(1, groups, None)
        labels = [opt.label for opt in select.options]
        self.assertEqual(labels, ["Season 01 (2 releases)", "Season 02 (1 release)"])

    def test_unspecified_season_listed_last(self):
        groups = _group_candidates_by_season(
            [{"id": "m", "title": "Movie", "parsed": {}}, {"id": "s", "title": "Show S01", "parsed": {"season": 1}}]
        )
        select = SeasonPickerSelect(1, groups, None)
        self.assertEqual([opt.value for opt in select.options], ["1", "none"])

    def test_callback_swaps_in_a_release_picker_scoped_to_the_chosen_season(self):
        groups = _group_candidates_by_season(
            [
                {"id": "s1", "title": "S1", "parsed": {"season": 1}, "seeders": 5},
                {"id": "s2", "title": "S2", "parsed": {"season": 2}, "seeders": 5},
            ]
        )
        select = SeasonPickerSelect(1, groups, None)
        release_picker = ReleaseWithinSeasonSelect(1, groups[2], None)
        self.assertEqual([c["id"] for c in release_picker.candidates], ["s2"])


class ReleaseWithinSeasonSelectTests(unittest.TestCase):
    def test_marks_auto_selected_default(self):
        candidates = [
            {"id": "a", "title": "[Group] Show 1080p", "parsed": {"resolution": "1080p"}, "seeders": 10},
            {"id": "b", "title": "[Group] Show 2160p", "parsed": {"resolution": "2160p"}, "seeders": 20},
        ]
        select = ReleaseWithinSeasonSelect(1, candidates, "b")
        self.assertFalse(select.options[0].default)
        self.assertTrue(select.options[1].default)

    def test_resolves_index_to_candidate_id(self):
        candidates = [{"id": "magnet:a", "title": "A", "parsed": {}}, {"id": "magnet:b", "title": "B", "parsed": {}}]
        select = ReleaseWithinSeasonSelect(1, candidates, None)
        chosen = select.candidates[int(select.options[1].value)]
        self.assertEqual(chosen["id"], "magnet:b")


class GroupCandidatesBySeasonTests(unittest.TestCase):
    def test_sorts_each_group_by_seeders_descending(self):
        groups = _group_candidates_by_season(
            [
                {"id": "low", "title": "x", "parsed": {"season": 1}, "seeders": 5},
                {"id": "high", "title": "x", "parsed": {"season": 1}, "seeders": 50},
            ]
        )
        self.assertEqual([c["id"] for c in groups[1]], ["high", "low"])


class WithinSeasonOptionTextTests(unittest.TestCase):
    def test_leads_with_quality_not_season(self):
        label, description = _within_season_option_text(
            {"title": "[Group] Show S02 1080p BluRay", "parsed": {"resolution": "1080p", "source": "bluray"}, "seeders": 20}
        )
        self.assertEqual(label, "1080p • bluray • 20 seeders")
        self.assertEqual(description, "[Group] Show S02 1080p BluRay")

    def test_falls_back_to_bare_release_label(self):
        label, _ = _within_season_option_text({"title": "x", "parsed": {}})
        self.assertEqual(label, "Release")


class VRMSGateEmbedTests(unittest.TestCase):
    def test_find_top_release_candidate_prefers_auto_selected(self):
        entry = {
            "autoSelectedId": "b",
            "candidates": [{"id": "a", "title": "Candidate A"}, {"id": "b", "title": "Candidate B"}],
        }
        candidate = _find_top_release_candidate(entry)
        self.assertEqual(candidate["id"], "b")

    def test_find_top_release_candidate_falls_back_to_first(self):
        entry = {"autoSelectedId": "missing", "candidates": [{"id": "a", "title": "Candidate A"}]}
        candidate = _find_top_release_candidate(entry)
        self.assertEqual(candidate["id"], "a")

    def test_find_top_release_candidate_handles_none_and_empty(self):
        self.assertIsNone(_find_top_release_candidate(None))
        self.assertIsNone(_find_top_release_candidate({"autoSelectedId": None, "candidates": []}))

    def test_release_gate_embed_with_no_candidate(self):
        embed = build_release_gate_embed("Sintel", None)
        self.assertTrue(any("No candidate" in (f.value or "") for f in embed.fields))

    def test_release_gate_embed_with_candidate(self):
        candidate = {"title": "Sintel.2010.1080p.BluRay", "parsed": {"resolution": "1080p", "source": "bluray"}, "seeders": 42}
        embed = build_release_gate_embed("Sintel", candidate)
        field_names = {f.name for f in embed.fields}
        self.assertIn("Resolution", field_names)
        self.assertIn("Seeders", field_names)

    def test_final_gate_embed_shows_storage_warning(self):
        entry = {"metadata": {"title": "Sintel", "year": 2010}, "storage": {"hasEnoughSpace": False}}
        embed = build_final_gate_embed("Sintel", entry)
        storage_field = next(f for f in embed.fields if f.name == "Storage")
        self.assertIn("Not enough space", storage_field.value)

    def test_final_gate_embed_handles_storage_error(self):
        entry = {"metadata": {}, "storage": {"error": "no library root configured"}}
        embed = build_final_gate_embed("Sintel", entry)
        storage_field = next(f for f in embed.fields if f.name == "Storage Check")
        self.assertIn("no library root configured", storage_field.value)


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

    async def test_vrms_job_id_starts_unset(self):
        request_id = await self.db.create_media_request(1, 2, "movie", 550, "Fight Club", "1999", None, None, None)
        request = await self.db.get_media_request(request_id)
        self.assertIsNone(request["vrms_job_id"])

    async def test_set_vrms_job_id(self):
        request_id = await self.db.create_media_request(1, 2, "movie", 550, "Fight Club", "1999", None, None, None)
        await self.db.set_media_request_vrms_job(request_id, "job-abc-123")
        request = await self.db.get_media_request(request_id)
        self.assertEqual(request["vrms_job_id"], "job-abc-123")

    async def test_list_with_vrms_job_excludes_terminal_statuses(self):
        approved_id = await self.db.create_media_request(1, 2, "movie", 1, "A", None, None, None, None)
        await self.db.set_media_request_vrms_job(approved_id, "job-1")
        await self.db.update_media_request_status(approved_id, "approved")

        completed_id = await self.db.create_media_request(1, 2, "movie", 2, "B", None, None, None, None)
        await self.db.set_media_request_vrms_job(completed_id, "job-2")
        await self.db.update_media_request_status(completed_id, "completed")

        no_job_id = await self.db.create_media_request(1, 2, "movie", 3, "C", None, None, None, None)
        await self.db.update_media_request_status(no_job_id, "approved")

        tracked = await self.db.list_media_requests_with_vrms_job()
        self.assertEqual({r["id"] for r in tracked}, {approved_id})

    async def test_gate_message_set_and_clear(self):
        request_id = await self.db.create_media_request(1, 2, "movie", 550, "Fight Club", "1999", None, None, None)
        await self.db.set_media_request_gate_message(request_id, channel_id=10, message_id=20)
        request = await self.db.get_media_request(request_id)
        self.assertEqual(request["vrms_gate_channel_id"], 10)
        self.assertEqual(request["vrms_gate_message_id"], 20)

        await self.db.clear_media_request_gate_message(request_id)
        request = await self.db.get_media_request(request_id)
        self.assertIsNone(request["vrms_gate_channel_id"])
        self.assertIsNone(request["vrms_gate_message_id"])


if __name__ == "__main__":
    unittest.main()
