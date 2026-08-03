import io
import unittest

from PIL import Image

from services.welcome_card import CANVAS_SIZE, render_card


def make_avatar_bytes(color=(255, 200, 0)) -> bytes:
    avatar = Image.new("RGB", (256, 256), color)
    buffer = io.BytesIO()
    avatar.save(buffer, format="PNG")
    return buffer.getvalue()


class RenderCardTests(unittest.TestCase):
    def test_produces_a_valid_png_at_the_expected_size(self):
        png_bytes = render_card(make_avatar_bytes())
        image = Image.open(io.BytesIO(png_bytes))
        self.assertEqual(image.format, "PNG")
        self.assertEqual(image.size, CANVAS_SIZE)

    def test_output_has_no_transparency(self):
        # The card is meant to render as a solid white card, matching the source asset.
        png_bytes = render_card(make_avatar_bytes())
        image = Image.open(io.BytesIO(png_bytes))
        self.assertEqual(image.mode, "RGB")

    def test_avatar_color_appears_near_its_placement_center(self):
        from services.welcome_card import AVATAR_CENTER

        avatar_color = (10, 200, 30)
        png_bytes = render_card(make_avatar_bytes(avatar_color))
        image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        sampled = image.getpixel(AVATAR_CENTER)
        self.assertEqual(sampled, avatar_color)

    def test_handles_non_square_avatar_input(self):
        avatar = Image.new("RGB", (128, 300), (0, 0, 0))
        buffer = io.BytesIO()
        avatar.save(buffer, format="PNG")
        # Should not raise despite non-square input.
        render_card(buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
