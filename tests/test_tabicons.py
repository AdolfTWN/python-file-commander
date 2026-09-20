import struct
import unittest
import zlib

from pycommander.tabicons import tab_lock_icon_png


def pixels(png):
    size = struct.unpack('>I', png[16:20])[0]
    offset, compressed = 8, bytearray()
    while offset < len(png):
        length = struct.unpack('>I', png[offset:offset+4])[0]
        if png[offset+4:offset+8] == b'IDAT':
            compressed.extend(png[offset+8:offset+8+length])
        offset += length + 12
    rows = zlib.decompress(compressed)
    stride = 1 + 4*size
    return [tuple(rows[y*stride+1+x*4:y*stride+5+x*4])
            for y in range(size) for x in range(size)]


class TabIconTests(unittest.TestCase):
    def test_geometry_scales_and_has_antialiased_transparent_edges(self):
        for size in (16, 20, 28, 40, 56):
            for mode in ('locked', 'reset'):
                with self.subTest(size=size, mode=mode):
                    png = tab_lock_icon_png(mode, size, '#414141', '#fafafa')
                    self.assertEqual(struct.unpack('>II', png[16:24]), (size, size))
                    values = pixels(png)
                    self.assertTrue(any(0 < p[3] < 255 for p in values))
                    self.assertEqual(values[0][3], 0)
                    self.assertIn((65, 65, 65, 255), values)
                    self.assertIn((250, 250, 250, 255), values)

    def test_same_tile_distinct_silhouette_in_both_themes(self):
        for bg, fg in (('#414141', '#fafafa'), ('#dedede', '#252525')):
            for size in (16, 24, 40):
                full = pixels(tab_lock_icon_png('locked', size, bg, fg))
                reset = pixels(tab_lock_icon_png('reset', size, bg, fg))
                # Their outer tile is pixel-identical. At least 15% of pixels
                # differ internally, not merely a tiny added color/symbol dot.
                self.assertEqual(full[:size*2], reset[:size*2])
                self.assertGreater(sum(a != b for a,b in zip(full, reset)), size*size*.15)

    def test_reject_invalid_states_and_sizes(self):
        for mode, size in (('unlocked', 24), ('unknown', 24), ('locked', 8), ('reset', 129)):
            with self.assertRaises(ValueError):
                tab_lock_icon_png(mode, size, '#414141', '#fafafa')


if __name__ == '__main__':
    unittest.main()
