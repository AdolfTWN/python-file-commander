import tempfile
import unittest
from pathlib import Path

from pycommander.fileops import copy_items, delete_items, format_size, move_items


class FileOpsTests(unittest.TestCase):
    def test_copy_move_delete(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source, target, moved = root / "source", root / "target", root / "moved"
            source.mkdir(); target.mkdir(); moved.mkdir()
            item = source / "report.txt"; item.write_text("office", encoding="utf-8")
            copy_items([item], target)
            self.assertEqual((target / item.name).read_text(encoding="utf-8"), "office")
            move_items([target / item.name], moved)
            self.assertFalse((target / item.name).exists())
            delete_items([moved / item.name])
            self.assertFalse((moved / item.name).exists())

    def test_format_size(self):
        self.assertEqual(format_size(1024), "1.0 KB")


if __name__ == "__main__":
    unittest.main()
