import unittest
from pycommander.marquee import marquee_offset


class MarqueeTests(unittest.TestCase):
    def test_start_travel_end_and_repeat(self):
        # 360px at 36px/s: 1s initial hold + 10s travel + 1.5s end hold.
        for elapsed, expected in ((0,0), (.99,0), (2,36), (6,180),
                                  (11,360), (12.49,360), (12.5,0), (13.4,0)):
            self.assertAlmostEqual(marquee_offset(elapsed,360,36), expected)

    def test_font_scale_preserves_reading_time(self):
        self.assertEqual(marquee_offset(3,720,72), 2*marquee_offset(3,360,36))

    def test_no_overflow_or_invalid_speed_is_static(self):
        for overflow, speed in ((0,36), (-1,36), (100,0)):
            self.assertEqual(marquee_offset(99,overflow,speed),0)
