import tempfile
import unittest
from pathlib import Path

from pycommander.shellmenu import context_menu_paths


class ShellMenuTests(unittest.TestCase):
    def test_context_menu_accepts_sibling_local_items(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first, second = root / "first.txt", root / "second.txt"
            first.write_text("one", encoding="utf-8")
            second.write_text("two", encoding="utf-8")
            self.assertEqual(context_menu_paths([first, second]), [first.resolve(), second.resolve()])

    def test_context_menu_rejects_items_from_different_folders(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first = root / "first.txt"; first.write_text("one", encoding="utf-8")
            nested = root / "nested"; nested.mkdir()
            second = nested / "second.txt"; second.write_text("two", encoding="utf-8")
            with self.assertRaises(OSError):
                context_menu_paths([first, second])

