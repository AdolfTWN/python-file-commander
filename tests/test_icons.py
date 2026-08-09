import struct
import unittest
import zlib

from pycommander.icons import VCS_BADGE_SPECS, _png_from_bgra, pfc_icon_png, vcs_badge_png


class IconTests(unittest.TestCase):
    def test_vcs_badges_use_distinct_high_contrast_git_style_symbols(self):
        self.assertEqual(set(VCS_BADGE_SPECS),
                         {"clean", "modified", "added", "untracked", "deleted", "conflict"})
        self.assertEqual({spec[1] for spec in VCS_BADGE_SPECS.values()},
                         {"check", "alert", "plus", "question", "minus", "cross"})
        self.assertEqual(len({spec[0] for spec in VCS_BADGE_SPECS.values()}), 6)
        self.assertTrue(all(spec[2] in {"#ffffff", "#171717"}
                            for spec in VCS_BADGE_SPECS.values()))

    def test_vcs_badge_has_antialiasing_dark_outline_and_solid_color_face(self):
        png = vcs_badge_png(20, "modified")
        self.assertEqual(struct.unpack(">II", png[16:24]), (20, 20))
        offset, compressed = 8, bytearray()
        while offset < len(png):
            length = struct.unpack(">I", png[offset:offset + 4])[0]
            kind = png[offset + 4:offset + 8]
            if kind == b"IDAT":
                compressed.extend(png[offset + 8:offset + 8 + length])
            offset += 12 + length
        rows = zlib.decompress(bytes(compressed)); stride = 1 + 20 * 4
        pixels = [rows[row * stride + 1 + column * 4:row * stride + 5 + column * 4]
                  for row in range(20) for column in range(20)]
        self.assertTrue(any(0 < pixel[3] < 255 for pixel in pixels))
        self.assertTrue(any(pixel[3] and max(pixel[:3]) < 60 for pixel in pixels))
        self.assertTrue(any(pixel[3] and min(pixel[:3]) > 230 for pixel in pixels))
        upper_face = pixels[4 * 20 + 6]
        self.assertGreater(upper_face[0], 180)
        self.assertLess(upper_face[1], 100)
        self.assertLess(upper_face[2], 100)

    def test_pfc_logo_is_an_embedded_rgba_png_at_requested_size(self):
        png = pfc_icon_png(32)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", png[16:24])
        self.assertEqual((width, height), (32, 32))
        self.assertGreater(len(png), 200)

    def test_pfc_logo_rejects_unreadable_sizes(self):
        with self.assertRaises(ValueError):
            pfc_icon_png(7)

    def test_pfc_logo_uses_interlocking_red_black_arrows_with_light_outline(self):
        png = pfc_icon_png(32)
        offset = 8
        compressed = bytearray()
        while offset < len(png):
            length = struct.unpack(">I", png[offset:offset + 4])[0]
            kind = png[offset + 4:offset + 8]
            data = png[offset + 8:offset + 8 + length]
            if kind == b"IDAT":
                compressed.extend(data)
            offset += 12 + length
        rows = zlib.decompress(bytes(compressed))
        stride = 1 + 32 * 4
        pixels = [
            rows[row * stride + 1 + column * 4:row * stride + 5 + column * 4]
            for row in range(32) for column in range(32)
        ]
        visible = [pixel for pixel in pixels if pixel[3]]
        self.assertGreater(len(visible), 32 * 32 // 5)
        red = [pixel for pixel in visible if pixel[0] > 180 and pixel[1] < 90]
        black = [pixel for pixel in visible if max(pixel[:3]) < 65]
        white = [pixel for pixel in visible if min(pixel[:3]) > 220]
        self.assertGreater(len(red), 100)
        self.assertGreater(len(black), 100)
        self.assertGreater(len(white), 30)

    def test_bgra_is_encoded_as_png(self):
        image = _png_from_bgra(bytes((0, 0, 255, 255)), 1)
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
