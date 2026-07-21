import unittest

from pycommander.tabs import (COLOR_SCHEMES, TAB_COLORS, TAB_STYLES, color_scheme,
                              contrasting_edge_color, lock_indicator_segment)


class TabPaletteTests(unittest.TestCase):
    def test_palette_has_default_plus_five_presets(self):
        self.assertEqual(set(TAB_COLORS), {"default", "amber", "coral", "pink", "violet", "teal"})

    def test_tab_shape_presets_are_stable(self):
        self.assertEqual(TAB_STYLES, {"right_skirt": "Right Skirt", "rounded": "Rounded",
                                     "squarish": "Squarish"})

    def test_color_schemes_have_complete_distinct_palettes(self):
        self.assertEqual(set(COLOR_SCHEMES), {"light", "light_grey", "dark"})
        self.assertEqual(set(color_scheme("light")), set(color_scheme("dark")))
        self.assertNotEqual(color_scheme("light")["surface"], color_scheme("dark")["surface"])
        self.assertIs(color_scheme("unknown"), COLOR_SCHEMES["light"])

    def test_lock_modes_use_distinct_solid_edges_without_extra_width(self):
        top = lock_indicator_segment("locked", 10, 100, 4, 34, 6, "right_skirt")
        left = lock_indicator_segment("reset", 10, 100, 4, 34, 6, "right_skirt")
        self.assertEqual(top[1], top[3], "Full lock should be a horizontal top edge")
        self.assertEqual(left[0], left[2], "Folder-change lock should be a vertical left edge")
        self.assertIsNone(lock_indicator_segment("unlocked", 10, 100, 4, 34, 6, "rounded"))
        self.assertEqual(contrasting_edge_color("#f2c14e"), "#17232c")
        self.assertEqual(contrasting_edge_color("#4c606e"), "#f7fbff")


if __name__ == "__main__":
    unittest.main()
