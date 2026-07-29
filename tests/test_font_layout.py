import unittest

from pycommander.app import automatic_font_size, scaled_tree_row_height
from pycommander.search import search_row_height


class FontLayoutTests(unittest.TestCase):
    def test_automatic_font_size_respects_window_and_panel_density(self):
        self.assertEqual(automatic_font_size(1200, 720, 2), "medium")
        self.assertEqual(automatic_font_size(2400, 1300, 2), "huge")
        self.assertEqual(automatic_font_size(1200, 900, 4), "small")

    def test_row_height_leaves_space_below_font_and_icon(self):
        for linespace, scale in ((16, 1.0), (24, 1.5), (32, 2.0), (48, 3.0)):
            height = scaled_tree_row_height(linespace, scale)
            self.assertGreaterEqual(height, linespace + max(8, round(8 * scale)))
            self.assertGreaterEqual(height, max(16, round(16 * scale)) + max(8, round(8 * scale)))

    def test_small_mode_has_a_readable_minimum_height(self):
        self.assertGreaterEqual(scaled_tree_row_height(12, 1.0), 24)

    def test_search_results_have_scaled_text_padding(self):
        for linespace, scale in ((16, 1.0), (24, 1.5), (32, 2.0), (48, 3.0)):
            self.assertGreaterEqual(search_row_height(linespace, scale),
                                    linespace + max(8, round(6 * scale)))


if __name__ == "__main__":
    unittest.main()
