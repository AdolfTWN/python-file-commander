import tempfile
import unittest
from pathlib import Path

from pycommander.app import FilePane


class RefreshSignatureTests(unittest.TestCase):
    def test_signature_changes_after_file_edit(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); item = root / "report.txt"
            item.write_text("old", encoding="utf-8")
            before = FilePane.signature_for(list(root.iterdir()))
            item.write_text("new content", encoding="utf-8")
            after = FilePane.signature_for(list(root.iterdir()))
            self.assertNotEqual(before, after)

    def test_signature_is_order_independent(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "a.txt").write_text("a", encoding="utf-8")
            (root / "b.txt").write_text("b", encoding="utf-8")
            entries = list(root.iterdir())
            self.assertEqual(FilePane.signature_for(entries), FilePane.signature_for(reversed(entries)))


if __name__ == "__main__":
    unittest.main()
