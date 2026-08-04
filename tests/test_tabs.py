import unittest

from pycommander.tabs import (COLOR_SCHEMES, TAB_COLORS, TAB_STYLES, color_scheme,
                              clamp_popup_position, contrasting_edge_color, lock_indicator_segment,
                              normalize_tab_color)


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

    def test_lock_modes_use_distinct_solid_edges_without_extra_width(self):
        top = lock_indicator_segment("locked", 10, 100, 4, 34, 6, "right_skirt")
        left = lock_indicator_segment("reset", 10, 100, 4, 34, 6, "right_skirt")
        self.assertEqual(top[1], top[3], "Full lock should be a horizontal top edge")
        self.assertEqual(left[0], left[2], "Folder-change lock should be a vertical left edge")
        self.assertIsNone(lock_indicator_segment("unlocked", 10, 100, 4, 34, 6, "rounded"))
        self.assertEqual(contrasting_edge_color("#f2c14e"), "#17232c")
        self.assertEqual(contrasting_edge_color("#4c606e"), "#f7fbff")

    def test_popup_clamps_inside_multi_monitor_virtual_desktop(self):
        bounds = (0, 0, 3840, 1080)
        self.assertEqual(clamp_popup_position(2100, 100, 300, 400, bounds),
                         (2100, 100))
        self.assertEqual(clamp_popup_position(3700, 900, 300, 300, bounds),
                         (3540, 780))


if __name__ == "__main__":
    unittest.main()
