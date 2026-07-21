import unittest

from pycommander.tabs import COLOR_SCHEMES, TAB_COLORS, TAB_STYLES, color_scheme


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


if __name__ == "__main__":
    unittest.main()
