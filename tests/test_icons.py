import unittest

from pycommander.icons import _png_from_bgra


class IconTests(unittest.TestCase):
    def test_bgra_is_encoded_as_png(self):
        image = _png_from_bgra(bytes((0, 0, 255, 255)), 1)
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
