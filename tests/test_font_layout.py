import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from pycommander.app import Commander, automatic_font_size, extension_column_width, scaled_tree_row_height
from pycommander.search import search_row_height


class FontLayoutTests(unittest.TestCase):
    def test_auto_key_excludes_content_height_and_same_monitor_position(self):
        app = Mock()
        app._window_visibility = None
        app.winfo_width.return_value = 1400
        app.winfo_screenwidth.return_value = 1920
        app.winfo_screenheight.return_value = 1080
        app.panel_count_var.get.return_value = 2
        with patch('pycommander.app.popup_work_area', return_value=(0, 0, 1920, 1040)) as area:
            key = Commander._auto_font_key(app, [('old', 'short.txt')])
            app.winfo_height.return_value = 500
            self.assertEqual(key, Commander._auto_font_key(app, [('new', 'very-long-name.txt')]))
            app.winfo_width.return_value = 1000
            self.assertNotEqual(key, Commander._auto_font_key(app))
            app.winfo_width.return_value = 1400
            area.return_value = (1920, 0, 3840, 1040)
            self.assertNotEqual(key, Commander._auto_font_key(app))
        app._auto_font_samples.assert_not_called()

    def test_native_dpi_and_panel_count_are_external_triggers(self):
        app = Mock()
        app.winfo_width.return_value = 1400
        app.winfo_screenwidth.return_value = 1920
        app.winfo_screenheight.return_value = 1080
        app.panel_count_var.get.return_value = 2
        backend = Mock()
        backend.user.GetDpiForWindow.return_value = 96
        app._window_visibility = SimpleNamespace(backend=backend)
        with patch('pycommander.app.popup_work_area', return_value=(0, 0, 1920, 1040)):
            key = Commander._auto_font_key(app)
            backend.user.GetDpiForWindow.return_value = 144
            self.assertNotEqual(key, Commander._auto_font_key(app))
            backend.user.GetDpiForWindow.return_value = 96
            app.panel_count_var.get.return_value = 1
            self.assertNotEqual(key, Commander._auto_font_key(app))

    def test_unchanged_layout_never_schedules_or_samples(self):
        app = Mock()
        app._ready = True
        app._auto_font_busy = False
        app._auto_font_key.return_value = ('unchanged',)
        app._last_auto_window_size = ('unchanged',)
        Commander._schedule_auto_font_size(app)
        app.after.assert_not_called()
        app._auto_font_samples.assert_not_called()
        Commander._apply_automatic_font_size(app)
        app._auto_font_samples.assert_not_called()

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
