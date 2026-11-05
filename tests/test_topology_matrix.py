"""Deterministic model coverage, not proof of physical multi-monitor hardware."""
import random
import unittest
from unittest.mock import Mock

from pycommander.windowplacement import WindowVisibilityGuard, visible_window_target


class TopologyMatrixTests(unittest.TestCase):
    layouts = (
        ((0,0,1366,728),),
        ((0,0,1920,1040),),
        ((0,0,2560,1400),),
        ((0,0,3840,2120),),
        ((0,0,1920,1040),(1920,0,3840,1040)),
        ((0,0,1920,1040),(-2560,-200,0,1200)),
        ((0,0,2560,1400),(2800,200,4720,1240),(-1366,0,0,728)),
        ((0,0,1920,1040),(-1920,0,0,1040),(0,-1080,1920,-40),(1920,0,5760,2120)),
    )

    def test_seeded_fit_invariants_with_negative_gaps_and_mixed_monitor_sizes(self):
        rng=random.Random(20261105)
        for layout in self.layouts:
            for _ in range(250):
                x,y=rng.randint(-6000,6000),rng.randint(-3000,3000)
                width,height=rng.randint(200,5000),rng.randint(160,2500)
                rect=(x,y,x+width,y+height)
                target=visible_window_target(rect,layout,16,fit=True)
                if target is None:
                    self.assertTrue(any(x>=a-16 and y>=b-16 and x+width<=c+16 and y+height<=d+16
                                        for a,b,c,d in layout),(rect,layout))
                else:
                    tx,ty,tw,th=target
                    self.assertGreater(tw,0);self.assertGreater(th,0)
                    self.assertTrue(any(tx>=a and ty>=b and tx+tw<=c and ty+th<=d
                                        for a,b,c,d in layout),(target,layout))
                    # A recovered normal frame must not keep drifting.
                    self.assertIsNone(visible_window_target((tx,ty,tx+tw,ty+th),layout,16,fit=True))

    def test_disconnect_reconnect_cycles_are_debounced_and_preserve_intent(self):
        widget,backend=Mock(),Mock()
        widget.state.return_value='normal';widget.winfo_ismapped.return_value=True
        guard=WindowVisibilityGuard(widget,backend,fit_to_monitor=True)
        try:
            for layout in self.layouts*4:
                backend.snapshot.return_value=((3000,50,4800,1050),layout,12)
                backend.move.reset_mock()
                guard.previous=None
                guard.check();backend.move.assert_not_called()
                guard.check()
                self.assertLessEqual(backend.move.call_count,1)
                widget.state.return_value='iconic'
                backend.move.reset_mock();guard.check();guard.check()
                backend.move.assert_not_called()
                widget.state.return_value='normal'
        finally:guard.close()
