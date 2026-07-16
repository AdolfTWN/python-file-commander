import unittest

from pycommander.app import clipboard_header_widths, ellipsize_middle, split_clipboard_summary


class HeaderLayoutTests(unittest.TestCase):
    @staticmethod
    def measure(text: str) -> int:
        return len(text) * 10

    def test_clipboard_text_fits_and_preserves_both_ends(self):
        text = "Clipboard: quarterly-report-final.xlsx and 10 more files"
        fitted = ellipsize_middle(text, 260, self.measure)
        self.assertLessEqual(self.measure(fitted), 260)
        self.assertTrue(fitted.startswith("Clipboard"))
        self.assertTrue(fitted.endswith("more files"))
        self.assertIn("…", fitted)

    def test_short_clipboard_text_is_unchanged(self):
        text = "Clipboard: OBJ"
        self.assertEqual(ellipsize_middle(text, 200, self.measure), text)

    def test_clipboard_frame_never_exceeds_remaining_header_width(self):
        for window_width, left_width in ((1920, 620), (1100, 580), (760, 650), (300, 290)):
            frame_width, text_width = clipboard_header_widths(window_width, left_width, 48)
            self.assertLessEqual(frame_width, max(0, window_width - left_width - 24))
            self.assertGreaterEqual(frame_width, 0)
            self.assertGreaterEqual(text_width, 0)

    def test_clipboard_prefix_is_separated_before_the_file_icon(self):
        self.assertEqual(split_clipboard_summary("Clipboard: report.xlsx & other 2 files"),
                         ("Clipboard:", "report.xlsx & other 2 files"))
        self.assertEqual(split_clipboard_summary("剪貼簿：文字 10 位元組"),
                         ("剪貼簿：", "文字 10 位元組"))


if __name__ == "__main__":
    unittest.main()
