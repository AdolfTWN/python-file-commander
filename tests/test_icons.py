import struct
import unittest

from pycommander.icons import _png_from_bgra, pfc_icon_png


class IconTests(unittest.TestCase):
    def test_pfc_logo_is_an_embedded_rgba_png_at_requested_size(self):
        png = pfc_icon_png(32)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", png[16:24])
        self.assertEqual((width, height), (32, 32))
        self.assertGreater(len(png), 200)

    def test_pfc_logo_rejects_unreadable_sizes(self):
        with self.assertRaises(ValueError):
            pfc_icon_png(7)

    def test_bgra_is_encoded_as_png(self):
        image = _png_from_bgra(bytes((0, 0, 255, 255)), 1)
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
