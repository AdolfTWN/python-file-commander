import unittest

from pycommander.app import middle_ellipsize


class NameDisplayTests(unittest.TestCase):
    def test_middle_ellipsis_preserves_name_start_and_extension(self):
        text = "ABCDEFGHIJKLMN123456789123.txt"
        shortened = middle_ellipsize(text, 22, len)
        self.assertLessEqual(len(shortened), 22)
        self.assertTrue(shortened.startswith("ABCDEFG"))
        self.assertTrue(shortened.endswith(".txt"))
        self.assertIn("...", shortened)

    def test_short_name_is_unchanged(self):
        self.assertEqual(middle_ellipsize("report.txt", 40, len), "report.txt")


if __name__ == "__main__":
    unittest.main()
