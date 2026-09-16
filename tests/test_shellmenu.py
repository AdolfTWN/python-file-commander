import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pycommander.shellmenu import context_menu_paths


class ShellMenuTests(unittest.TestCase):
    def test_corrupt_zip_does_not_crash_menu_count_worker(self):
        from pycommander.app import Commander, tr
        with tempfile.TemporaryDirectory() as raw:
            archive = Path(raw)/'broken.zip'; archive.write_text('not a ZIP')
            callbacks, changes = [], []
            owner = SimpleNamespace(after=lambda delay, callback: callbacks.append(callback))
            menu = SimpleNamespace(winfo_exists=lambda: True,
                                   entryconfigure=lambda index, **kw: changes.append((index,kw)))
            with patch('pycommander.app.threading.Thread',
                       side_effect=lambda target, **kw: SimpleNamespace(start=target)):
                Commander._load_archive_menu_count(owner,menu,2,archive)
            callbacks.pop()()
            self.assertEqual(changes, [(2, {'label': tr('Extract Here')})])

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
