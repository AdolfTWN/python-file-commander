import unittest
from unittest.mock import Mock

from pycommander.windowplacement import WindowVisibilityGuard, visible_window_target, popup_work_area


class WindowPlacementTests(unittest.TestCase):
    primary = (0, 0, 1920, 1040)

    def test_popup_uses_owner_monitor_work_area_not_full_screen(self):
        owner = Mock()
        owner._root.return_value = owner
        secondary = (-1920, 0, 0, 1000)
        owner._window_visibility.backend.snapshot.return_value = (
            (-1800, 40, -400, 900), (self.primary, secondary), 8)
        self.assertEqual(popup_work_area(owner), secondary)

    def test_disconnected_right_display_returns_to_center(self):
        self.assertEqual(visible_window_target((2100, 100, 3300, 820), [self.primary]),
                         (360, 160, 1200, 720))

    def test_full_frame_fit_is_opt_in_for_title_reachable_windows(self):
        area=(0,0,1280,680)
        rect=(1100,100,2600,1000)
        self.assertIsNone(visible_window_target(rect,[area]))
        self.assertEqual(visible_window_target(rect,[area],fit=True),(0,0,1280,680))

    def test_popup_fit_preserves_connected_negative_monitor(self):
        area=(-1600,-200,0,760)
        rect=(-1500,-100,-200,600)
        self.assertIsNone(visible_window_target(rect,[self.primary,area],fit=True))

    def test_popup_topology_fit_does_not_snap_back_normal_user_moves(self):
        widget,backend=Mock(),Mock()
        widget.state.return_value='normal';widget.winfo_ismapped.return_value=True
        area=(0,0,1280,680)
        backend.snapshot.return_value=((100,100,1100,650),(area,),8)
        guard=WindowVisibilityGuard(widget,backend,fit_to_monitor=True)
        guard.check(force=True);backend.move.assert_not_called()
        # A user can deliberately leave part of a window offscreen.
        backend.snapshot.return_value=((1100,100,2100,650),(area,),8)
        guard.check();guard.check();backend.move.assert_not_called()
        # A smaller work area is fitted after stable topology observations.
        backend.snapshot.return_value=((1100,100,2100,650),((0,0,1200,600),),8)
        guard.check();guard.check()
        backend.move.assert_called_once_with((100,25,1000,550))
        guard.close()

    def test_popup_fitting_preserves_native_maximized_border(self):
        self.assertIsNone(visible_window_target((-12,-12,1932,1052),[self.primary],12,fit=True))

    def test_immediate_recovery_tolerates_display_api_transition_failure(self):
        widget,backend=Mock(),Mock()
        widget.state.return_value='normal';widget.winfo_ismapped.return_value=True
        backend.snapshot.side_effect=OSError('display changing')
        guard=WindowVisibilityGuard(widget,backend,fit_to_monitor=True)
        guard.recover();backend.move.assert_not_called()
        self.assertIsNone(guard.previous)
        guard.close()

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
