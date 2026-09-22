import struct
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from pycommander import icons

from pycommander.icons import (FILE_ATTRIBUTE_NORMAL, SHGFI_ICON,
                               SHGFI_SMALLICON, SHGFI_USEFILEATTRIBUTES,
                               VCS_BADGE_SPECS, _png_from_bgra,
                               _shell_icon_request, pfc_icon_png,
                               vcs_badge_png, folder_nav_icon_png)


class IconTests(unittest.TestCase):
    def test_navigation_icons_are_distinct_scaled_antialiased_rgba(self):
        for size in (18,27,54):
            images = [folder_nav_icon_png(kind,size) for kind in ('folder','drive','pc')]
            self.assertEqual(len(set(images)),3)
            for png in images:
                self.assertEqual(struct.unpack('>II',png[16:24]),(size,size))
                offset, compressed = 8, bytearray()
                while offset < len(png):
                    length = struct.unpack('>I',png[offset:offset+4])[0]
                    if png[offset+4:offset+8] == b'IDAT':
                        compressed.extend(png[offset+8:offset+8+length])
                    offset += 12+length
                rows=zlib.decompress(compressed); stride=1+size*4
                alpha=[rows[y*stride+1+x*4+3] for y in range(size) for x in range(size)]
                self.assertIn(0,alpha)
                self.assertIn(255,alpha)
                self.assertTrue(any(0<a<255 for a in alpha))

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


class ShellIconRequestTests(unittest.TestCase):
    def test_executable_uses_safe_generic_type_icon(self):
        lookup, attributes, flags = _shell_icon_request(
            Path("C:/Downloads/untrusted-tool.EXE"), False)

        self.assertEqual(lookup, ".exe")
        self.assertEqual(attributes, FILE_ATTRIBUTE_NORMAL)
        self.assertEqual(
            flags, SHGFI_ICON | SHGFI_SMALLICON | SHGFI_USEFILEATTRIBUTES)

    def test_regular_file_keeps_live_path_lookup(self):
        path = Path("C:/Downloads/report.txt")
        lookup, attributes, flags = _shell_icon_request(path, False)

        self.assertEqual(lookup, str(path))
        self.assertEqual(attributes, 0)
        self.assertEqual(flags, SHGFI_ICON | SHGFI_SMALLICON)


class ShellIconCacheTests(unittest.TestCase):
    def test_cache_is_bounded_and_keeps_recently_used_paths(self):
        paths = [Path('/profile') / str(i) for i in range(5)]
        with patch.object(icons, 'PhotoImage'), patch.object(icons.os, 'name', 'nt'):
            provider = icons.ShellIconProvider(cache_limit=2)
            with patch.object(provider, '_load', side_effect=lambda p, d: object()) as load, \
                    patch.object(provider, '_with_text_gap', side_effect=lambda image: image):
                first = provider.get(paths[0], True)
                second = provider.get(paths[1], True)
                self.assertIs(provider.get(paths[0], True), first)
                provider.get(paths[2], True)
                self.assertIs(provider.get(paths[0], True), first)
                self.assertIsNot(provider.get(paths[1], True), second)
                self.assertEqual(load.call_count, 4)
                for path in paths:
                    provider.get(path, True)
                    self.assertLessEqual(len(provider.cache), 2)

    def test_folder_icons_are_path_specific_in_both_navigation_orders(self):
        paths = [Path('/profile') / name for name in
                 ('Downloads', 'OneDrive', 'Documents', 'Projects', 'Other/Downloads')]
        for order in (paths, list(reversed(paths))):
            with self.subTest(first=order[0]), patch.object(icons, 'PhotoImage'), \
                    patch.object(icons.os, 'name', 'nt'):
                provider = icons.ShellIconProvider()
                with patch.object(provider, '_load', side_effect=lambda p, d: object()) as load, \
                        patch.object(provider, '_with_text_gap', side_effect=lambda image: image):
                    images = [provider.get(path, True) for path in order]
                    self.assertEqual(len({id(image) for image in images}), len(paths))
                    for path, image in zip(order, images):
                        self.assertIs(provider.get(path, True), image)
                    self.assertEqual(load.call_count, len(paths))

    def test_file_type_reuse_and_path_sensitive_shortcuts_are_preserved(self):
        paths = [Path('/work') / name for name in
                 ('a.txt', 'b.TXT', 'a.lnk', 'b.lnk', 'a.ico', 'b.ico', 'folder.txt')]
        with patch.object(icons, 'PhotoImage'), patch.object(icons.os, 'name', 'nt'):
            provider = icons.ShellIconProvider()
            with patch.object(provider, '_load', side_effect=lambda p, d: object()), \
                    patch.object(provider, '_with_text_gap', side_effect=lambda image: image):
                images = [provider.get(path, index == 6) for index, path in enumerate(paths)]
                self.assertIs(images[0], images[1])
                self.assertEqual(len({id(image) for image in images}), 6)

    def test_folder_overlays_do_not_alias_other_paths_or_plain_icons(self):
        paths = [Path('/profile/Downloads'), Path('/profile/Documents')]
        with patch.object(icons, 'PhotoImage'), patch.object(icons.os, 'name', 'nt'):
            provider = icons.ShellIconProvider()
            with patch.object(provider, '_load', side_effect=lambda p, d: object()), \
                    patch.object(provider, '_with_text_gap', side_effect=lambda image: image), \
                    patch.object(provider, '_with_overlay', side_effect=lambda *a, **k: object()):
                images = [provider.get(path, True, overlay) for path in paths
                          for overlay in (None, 'clean', 'modified')]
                self.assertEqual(len({id(image) for image in images}), 6)


if __name__ == "__main__":
    unittest.main()
