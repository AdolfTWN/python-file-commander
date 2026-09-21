import unittest
from unittest.mock import Mock

from pycommander.windowplacement import WindowVisibilityGuard, visible_window_target


class WindowPlacementTests(unittest.TestCase):
    primary = (0, 0, 1920, 1040)

    def test_disconnected_right_display_returns_to_center(self):
        self.assertEqual(visible_window_target((2100, 100, 3300, 820), [self.primary]),
                         (360, 160, 1200, 720))

    def test_valid_second_display_is_preserved(self):
        rect = (2100, 100, 3300, 820)
        self.assertIsNone(visible_window_target(rect, [self.primary, (1920, 0, 3840, 1040)]))

    def test_negative_coordinates_are_valid_on_a_connected_monitor(self):
        rect = (-1800, -100, -600, 620)
        self.assertIsNone(visible_window_target(rect, [self.primary, (-1920, -200, 0, 880)]))
        self.assertIsNotNone(visible_window_target(rect, [self.primary]))

    def test_gap_between_displays_is_not_a_visible_monitor(self):
        self.assertEqual(visible_window_target((1920, 100, 2300, 800),
                         [self.primary, (2400, 0, 4320, 1040)]), (770, 170, 380, 700))

    def test_visible_body_without_title_bar_and_tiny_sliver_are_recovered(self):
        for rect in ((100, -200, 1300, 500), (1900, 100, 3100, 820), (100, 1030, 1300, 1750)):
            self.assertIsNotNone(visible_window_target(rect, [self.primary]))

    def test_normal_partial_visibility_and_maximized_border_are_preserved(self):
        for rect in ((-8, -8, 1928, 1048), (-100, 100, 1100, 820), (1700, 100, 2900, 820)):
            self.assertIsNone(visible_window_target(rect, [self.primary]))

    def test_oversized_window_fits_work_area_not_taskbar(self):
        self.assertEqual(visible_window_target((2500, 0, 6000, 2000), [self.primary]),
                         (0, 0, 1920, 1040))

    def test_high_dpi_maximized_resize_border_is_not_offscreen(self):
        self.assertIsNone(visible_window_target((-12, -12, 1932, 1052), [self.primary], 12))

    def test_primary_on_negative_coordinates(self):
        self.assertEqual(visible_window_target((2000, 0, 3200, 720), [(-1920, 40, 0, 1080)]),
                         (-1560, 200, 1200, 720))

    def test_unavailable_monitor_snapshot_does_nothing(self):
        self.assertIsNone(visible_window_target((2000, 0, 3200, 720), []))

    def test_debounce_minimize_and_shutdown(self):
        widget, backend = Mock(), Mock()
        widget.state.return_value = 'normal'
        widget.winfo_ismapped.return_value = True
        backend.snapshot.return_value = ((2100, 100, 3300, 820), (self.primary,))
        guard = WindowVisibilityGuard(widget, backend)
        guard.check()
        backend.move.assert_not_called()
        guard.check()
        backend.move.assert_called_once_with((360, 160, 1200, 720))
        backend.move.reset_mock()
        widget.state.return_value = 'iconic'
        guard.check(); guard.check()
        backend.move.assert_not_called()
        widget.state.return_value = 'normal'
        guard.check(); guard.check()
        backend.move.assert_called_once()
        guard.close()
        widget.after_cancel.assert_called_once()


if __name__ == '__main__':
    unittest.main()
