import unittest

from pycommander.flowlayout import toolbar_rows,wrapped_control_text


class ToolbarRowsTests(unittest.TestCase):
    def test_control_wrap_preserves_text_and_handles_cjk(self):
        for value in ('Apply this to all remaining conflicts','将此选择套用至所有剩余冲突'):
            wrapped=wrapped_control_text(value,lambda s:len(s)*10,100)
            self.assertEqual(value.replace(' ',''),wrapped.replace('\n','').replace(' ',''))
            self.assertTrue(all(len(line)<=10 for line in wrapped.splitlines()))
    def test_exact_fit_keeps_one_row(self):
        self.assertEqual(toolbar_rows(206, [100, 100]), [[0, 1]])

    def test_requested_widths_not_widest_equal_columns(self):
        self.assertEqual(toolbar_rows(312, [150, 50, 100]), [[0, 1, 2]])

    def test_wraps_at_semantic_boundary_preserving_order(self):
        self.assertEqual(toolbar_rows(205, [100, 100, 40]), [[0], [1, 2]])

    def test_oversized_group_is_kept_for_responsive_internal_layout(self):
        self.assertEqual(toolbar_rows(100, [150, 20]), [[0], [1]])

    def test_empty_and_not_yet_mapped_width(self):
        self.assertEqual(toolbar_rows(0, []), [])
        self.assertEqual(toolbar_rows(0, [50, 100]), [[0], [1]])
