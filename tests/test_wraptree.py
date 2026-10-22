import unittest
from pycommander.wraptree import WrappedTreeview


class Font:
    def __init__(self):self.measured=[]
    def measure(self,text):self.measured.append(len(text));return len(text)


class WrappedLinesTests(unittest.TestCase):
    def test_preserves_spaces_and_wraps_within_width(self):
        for value in ('hello world',' leading and trailing  ','x'*1000,'完整顯示資料'*60):
            font=Font();lines=WrappedTreeview._lines(value,20,font)
            self.assertEqual(''.join(lines),value)
            self.assertTrue(all(len(line)<=20 for line in lines))

    def test_preserves_hard_line_breaks_and_empty_lines(self):
        self.assertEqual(WrappedTreeview._lines('first\r\n\rsecond\n',20,Font()),['first','','second',''])

    def test_long_values_are_not_truncated_or_measured_as_a_single_line(self):
        value='0123456789 '*10000+'END'
        font=Font();lines=WrappedTreeview._lines(value,40,font)
        self.assertEqual(''.join(lines),value)
        self.assertLessEqual(max(font.measured),80)
        self.assertLess(len(font.measured),len(value))


if __name__=='__main__':unittest.main()
