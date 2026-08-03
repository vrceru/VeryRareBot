import random
import unittest

from services.music.base import MusicProviderError, Track
from services.music.queue import GuildQueue, LoopMode


def make_track(title: str) -> Track:
    return Track(title=title, webpage_url=f"https://example.com/{title}", duration=60, requester_id=1, source="youtube")


class GuildQueueTests(unittest.TestCase):
    def test_enqueue_respects_max_size(self):
        queue = GuildQueue(max_size=1, default_volume=0.5)
        queue.enqueue(make_track("a"))
        with self.assertRaises(MusicProviderError):
            queue.enqueue(make_track("b"))

    def test_enqueue_many_stops_at_capacity(self):
        queue = GuildQueue(max_size=2, default_volume=0.5)
        added = queue.enqueue_many([make_track("a"), make_track("b"), make_track("c")])
        self.assertEqual(added, 2)
        self.assertEqual(len(queue), 2)

    def test_remove_by_one_indexed_position(self):
        queue = GuildQueue(max_size=10, default_volume=0.5)
        queue.enqueue_many([make_track("a"), make_track("b"), make_track("c")])
        removed = queue.remove(2)
        self.assertEqual(removed.title, "b")
        self.assertEqual([t.title for t in queue.upcoming], ["a", "c"])

    def test_remove_out_of_range_raises(self):
        queue = GuildQueue(max_size=10, default_volume=0.5)
        queue.enqueue(make_track("a"))
        with self.assertRaises(IndexError):
            queue.remove(0)
        with self.assertRaises(IndexError):
            queue.remove(5)

    def test_shuffle_preserves_membership(self):
        queue = GuildQueue(max_size=10, default_volume=0.5)
        titles = [f"t{i}" for i in range(10)]
        queue.enqueue_many([make_track(t) for t in titles])
        random.seed(1)
        queue.shuffle()
        self.assertCountEqual([t.title for t in queue.upcoming], titles)

    def test_volume_is_clamped(self):
        queue = GuildQueue(max_size=10, default_volume=0.5)
        self.assertEqual(queue.set_volume(-1), 0.0)
        self.assertEqual(queue.set_volume(5), 2.0)
        self.assertEqual(queue.set_volume(1.25), 1.25)

    def test_advance_without_loop_moves_forward(self):
        queue = GuildQueue(max_size=10, default_volume=0.5)
        queue.enqueue_many([make_track("a"), make_track("b")])
        self.assertEqual(queue.advance().title, "a")
        self.assertEqual(queue.advance().title, "b")
        self.assertIsNone(queue.advance())

    def test_track_loop_repeats_on_natural_end_but_not_on_skip(self):
        queue = GuildQueue(max_size=10, default_volume=0.5)
        queue.enqueue_many([make_track("a"), make_track("b")])
        queue.loop_mode = LoopMode.TRACK
        self.assertEqual(queue.advance().title, "a")
        self.assertEqual(queue.advance().title, "a")
        self.assertEqual(queue.advance(forced=True).title, "b")

    def test_queue_loop_recycles_finished_tracks(self):
        queue = GuildQueue(max_size=10, default_volume=0.5)
        queue.enqueue_many([make_track("a"), make_track("b")])
        queue.loop_mode = LoopMode.QUEUE
        self.assertEqual(queue.advance().title, "a")
        self.assertEqual(queue.advance().title, "b")
        self.assertEqual(queue.advance().title, "a")
        self.assertEqual(queue.advance().title, "b")

    def test_no_previous_track_initially(self):
        queue = GuildQueue(max_size=10, default_volume=0.5)
        self.assertFalse(queue.has_previous())
        self.assertIsNone(queue.go_back())

    def test_go_back_returns_to_previous_track(self):
        queue = GuildQueue(max_size=10, default_volume=0.5)
        queue.enqueue_many([make_track("a"), make_track("b"), make_track("c")])
        queue.advance()  # -> a
        queue.advance()  # -> b
        self.assertTrue(queue.has_previous())
        self.assertEqual(queue.go_back().title, "a")
        # "b" should be back at the front of the upcoming queue.
        self.assertEqual([t.title for t in queue.upcoming], ["b", "c"])

    def test_go_back_then_advance_replays_forward_correctly(self):
        queue = GuildQueue(max_size=10, default_volume=0.5)
        queue.enqueue_many([make_track("a"), make_track("b")])
        queue.advance()  # -> a
        queue.advance()  # -> b
        queue.go_back()  # -> a, b requeued
        self.assertEqual(queue.advance().title, "b")

    def test_track_loop_does_not_record_history_on_repeat(self):
        queue = GuildQueue(max_size=10, default_volume=0.5)
        queue.enqueue_many([make_track("a"), make_track("b")])
        queue.loop_mode = LoopMode.TRACK
        queue.advance()  # -> a
        queue.advance()  # repeats a, no history entry
        self.assertFalse(queue.has_previous())

    def test_clear_resets_history(self):
        queue = GuildQueue(max_size=10, default_volume=0.5)
        queue.enqueue_many([make_track("a"), make_track("b")])
        queue.advance()
        queue.advance()
        self.assertTrue(queue.has_previous())
        queue.clear()
        self.assertFalse(queue.has_previous())


if __name__ == "__main__":
    unittest.main()
