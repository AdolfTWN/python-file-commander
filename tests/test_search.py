import tempfile
import unittest
from pathlib import Path

from pycommander.search import content_matches, name_matches


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


if __name__ == "__main__": unittest.main()
