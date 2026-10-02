import unittest

from pycommander.app import automatic_font_size, extension_column_width, scaled_tree_row_height
from pycommander.search import search_row_height


class FontLayoutTests(unittest.TestCase):
    def test_automatic_font_size_uses_all_supported_steps_and_floor(self):
        for limit, expected in ((0, 'small'), (1.4, 'medium'), (1.75, '175'),
                                (2.25, '225'), (2.8, '275'), (4, '300')):
            self.assertEqual(automatic_font_size(lambda scale: scale <= limit), expected)

    def test_both_panel_constraints_must_fit(self):
        self.assertEqual(automatic_font_size(lambda scale: 200*scale <= 500 and
                                             300*scale <= 525), '175')

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
