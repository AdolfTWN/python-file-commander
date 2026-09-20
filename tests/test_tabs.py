import unittest

from pycommander.tabs import (COLOR_SCHEMES, TAB_COLORS, TAB_STYLES, color_scheme,
                              clamp_popup_position, tab_lock_metrics, normalize_tab_color)


class TabPaletteTests(unittest.TestCase):
    def test_palette_has_default_plus_five_presets(self):
        self.assertEqual(set(TAB_COLORS),
                         {"default", "red", "light_blue", "orange", "green", "purple"})

    def test_legacy_tab_colours_map_to_current_palette(self):
        self.assertEqual(normalize_tab_color("amber"), "orange")
        self.assertEqual(normalize_tab_color("teal"), "light_blue")
        self.assertEqual(normalize_tab_color("violet"), "purple")
        self.assertEqual(normalize_tab_color("unknown"), "default")

    def test_tab_shape_presets_are_stable(self):
        self.assertEqual(TAB_STYLES, {"right_skirt": "Right Skirt", "rounded": "Rounded",
                                     "squarish": "Squarish"})

    def test_color_schemes_have_complete_distinct_palettes(self):
        self.assertEqual(set(COLOR_SCHEMES), {"light", "light_grey", "dark"})
        self.assertEqual(set(color_scheme("light")), set(color_scheme("dark")))
        self.assertNotEqual(color_scheme("light")["surface"], color_scheme("dark")["surface"])
        self.assertIs(color_scheme("unknown"), COLOR_SCHEMES["light"])

    def test_lock_badges_are_compact_and_theme_neutral(self):
        for style in TAB_STYLES:
            sizes = []
            for line in (16, 20, 24, 28, 32, 40, 48, 56):
                size, inset, gap = tab_lock_metrics(line, style)
                self.assertLessEqual(inset, 5)
                self.assertEqual(gap, 3)
                self.assertLessEqual(size, line)
                height = max(30, line + 13)
                self.assertLessEqual(size, height-max(4, round(height*.22))-3)
                sizes.append(size)
            self.assertEqual(sizes, sorted(sizes))
        for theme in COLOR_SCHEMES.values():
            # A single background/foreground pair, never a per-mode color.
            for key in ('tab_lock_bg', 'tab_lock_fg'):
                rgb = theme[key].lstrip('#')
                self.assertEqual(rgb[:2], rgb[2:4])
                self.assertEqual(rgb[2:4], rgb[4:])
        self.assertGreater(int(COLOR_SCHEMES['dark']['tab_lock_bg'][1:3], 16), 200)
        self.assertLess(int(COLOR_SCHEMES['light']['tab_lock_bg'][1:3], 16), 80)

    def test_popup_clamps_inside_multi_monitor_virtual_desktop(self):
        bounds = (0, 0, 3840, 1080)
        self.assertEqual(clamp_popup_position(2100, 100, 300, 400, bounds),
                         (2100, 100))
        self.assertEqual(clamp_popup_position(3700, 900, 300, 300, bounds),
                         (3540, 780))


if __name__ == "__main__":
    unittest.main()
