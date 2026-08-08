import unittest

from cogs.admin import _render_announcement_body


class RenderAnnouncementBodyTests(unittest.TestCase):
    def test_converts_atx_headers_to_bold(self):
        # Discord embeds don't render "#"/"##" headers -- they show as literal hash characters.
        result = _render_announcement_body("# Title\nSome text\n## Section")
        self.assertEqual(result, "**Title**\nSome text\n**Section**")

    def test_leaves_non_header_lines_untouched(self):
        result = _render_announcement_body("**Bold** and *italic* and a `code span`.")
        self.assertEqual(result, "**Bold** and *italic* and a `code span`.")

    def test_does_not_touch_a_hashtag_mid_line(self):
        result = _render_announcement_body("Check #general for details.")
        self.assertEqual(result, "Check #general for details.")

    def test_handles_deeper_header_levels(self):
        result = _render_announcement_body("### Deep header")
        self.assertEqual(result, "**Deep header**")


if __name__ == "__main__":
    unittest.main()
