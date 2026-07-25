import tempfile
import unittest
from pathlib import Path

from pycommander.search import content_matches, name_matches, search_column_widths


class SearchTests(unittest.TestCase):
    def test_masks_and_partial_names(self):
        self.assertTrue(name_matches("Quarterly Report.xlsx", "report", False))
        self.assertTrue(name_matches("notes.txt", "*.txt;*.md", False))
        self.assertFalse(name_matches("notes.txt", "*.csv", False))

    def test_content_case(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "notes.txt"; path.write_text("Alpha beta", encoding="utf-8")
            self.assertTrue(content_matches(path, "alpha", False))
            self.assertFalse(content_matches(path, "alpha", True))

    def test_column_fit_uses_available_width(self):
        widths = search_column_widths(
            1000, {"name": 420, "folder": 600, "size": 90, "modified": 150, "ext": 60})
        self.assertLessEqual(sum(widths.values()), 1000)
        self.assertGreaterEqual(widths["name"], 130)
        self.assertGreaterEqual(widths["folder"], 150)


if __name__ == "__main__": unittest.main()
