import tempfile
import unittest
from pathlib import Path

from pycommander.search import content_matches, name_matches, search_column_widths, search_attributes
from pycommander.i18n import tr
from types import SimpleNamespace


class SearchTests(unittest.TestCase):
    def test_hidden_system_notes_reuse_stat_attributes(self):
        for flags,expected in ((0,''),(2,tr('Hidden')),(4,tr('System')),
                               (6,tr('Hidden')+' · '+tr('System'))):
            self.assertEqual(search_attributes(Path('ordinary.txt'),SimpleNamespace(st_file_attributes=flags)),expected)
        self.assertEqual(search_attributes(Path('.config'),SimpleNamespace()),tr('Hidden'))
        self.assertEqual(search_attributes(Path('plain.txt'),SimpleNamespace()),'')
        self.assertEqual(search_attributes(Path('.config'),SimpleNamespace(st_file_attributes=4)),tr('Hidden')+' · '+tr('System'))
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

    def test_long_paths_do_not_compress_readable_names(self):
        widths=search_column_widths(1180,{'name':230,'folder':900,'attributes':230,
                                        'size':125,'modified':200,'ext':100})
        self.assertEqual(widths['name'],230)
        self.assertGreaterEqual(widths['folder'],150)


if __name__ == "__main__": unittest.main()
