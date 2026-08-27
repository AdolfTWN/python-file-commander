import unittest

from pycommander.app import automatic_font_size, extension_column_width, scaled_tree_row_height
from pycommander.search import search_row_height


class FontLayoutTests(unittest.TestCase):
    def test_automatic_font_size_respects_window_and_panel_density(self):
        self.assertEqual(automatic_font_size(1200, 720, 2), "medium")
        self.assertEqual(automatic_font_size(1500, 900, 2), "large")
        self.assertEqual(automatic_font_size(2000, 1050, 2), "xl")
        self.assertEqual(automatic_font_size(2400, 1300, 2), "xxl")
        self.assertEqual(automatic_font_size(1200, 900, 4), "small")

    def test_half_screen_high_dpi_window_stays_at_native_font_size(self):
        self.assertEqual(automatic_font_size(2560, 2073, 2, 5120), "small")
        self.assertEqual(automatic_font_size(3000, 1800, 2, 5120), "small")
        self.assertEqual(automatic_font_size(3600, 1800, 2, 5120), "medium")
        self.assertEqual(automatic_font_size(5120, 2073, 2, 5120), "xxl")

    def test_extension_column_is_exactly_four_wide_latin_characters(self):
        measured = []

        def measure(text):
            measured.append(text)
            return len(text) * 11

        self.assertEqual(extension_column_width(measure), 44)
        self.assertEqual(measured, ["MMMM"])

    def test_row_height_leaves_space_below_font_and_icon(self):
        for linespace, scale in ((16, 1.0), (20, 1.25), (24, 1.5), (32, 2.0), (40, 2.5)):
            height = scaled_tree_row_height(linespace, scale)
            self.assertGreaterEqual(height, linespace + max(8, round(8 * scale)))
            self.assertGreaterEqual(height, max(16, round(16 * scale)) + max(8, round(8 * scale)))

    def test_small_mode_has_a_readable_minimum_height(self):
        self.assertGreaterEqual(scaled_tree_row_height(12, 1.0), 24)

    def test_search_results_have_scaled_text_padding(self):
        for linespace, scale in ((16, 1.0), (20, 1.25), (24, 1.5), (32, 2.0), (40, 2.5)):
            self.assertGreaterEqual(search_row_height(linespace, scale),
                                    linespace + max(8, round(6 * scale)))


if __name__ == "__main__":
    unittest.main()
