import struct
import unittest
import zlib

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

    def test_pfc_logo_uses_bold_red_arrows(self):
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
        self.assertGreater(len(visible), 32 * 32 // 4)
        self.assertTrue(all(pixel[0] > pixel[1] * 2 for pixel in visible))

    def test_bgra_is_encoded_as_png(self):
        image = _png_from_bgra(bytes((0, 0, 255, 255)), 1)
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
