import unittest

from pycommander.tabs import TAB_COLORS


class TabPaletteTests(unittest.TestCase):
    def test_palette_has_default_plus_five_presets(self):
        self.assertEqual(set(TAB_COLORS), {"default", "amber", "coral", "pink", "violet", "teal"})


if __name__ == "__main__":
    unittest.main()
