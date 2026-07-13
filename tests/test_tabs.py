import unittest

from pycommander.tabs import TAB_COLORS, TAB_STYLES


class TabPaletteTests(unittest.TestCase):
    def test_palette_has_default_plus_five_presets(self):
        self.assertEqual(set(TAB_COLORS), {"default", "amber", "coral", "pink", "violet", "teal"})

    def test_tab_shape_presets_are_stable(self):
        self.assertEqual(TAB_STYLES, {"rounded": "Soft Rounded", "slanted": "Slanted",
                                     "chamfered": "Chamfered", "compact": "Compact"})


if __name__ == "__main__":
    unittest.main()
