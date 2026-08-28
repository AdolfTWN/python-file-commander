import tempfile
import unittest
from pathlib import Path

from pycommander.app import FilePane
from pycommander.dirwatch import DirectoryWatchManager, directory_key


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


class _FakeWatcher:
    def __init__(self, path, events):
        self.path, self.events = Path(path), events
        self.alive = False
        self.stopped = False

    def start(self):
        self.alive = True

    def stop(self):
        self.alive = False
        self.stopped = True


class DirectoryWatchManagerTests(unittest.TestCase):
    def test_deduplicates_paths_and_reports_changes(self):
        manager = DirectoryWatchManager(_FakeWatcher, supported=True)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            watched = manager.sync([root, root])
            self.assertEqual(watched, {directory_key(root)})
            manager.events.put(root)
            manager.events.put(root)
            self.assertEqual(manager.drain(), {directory_key(root)})
        manager.close()

    def test_removes_watch_when_folder_is_no_longer_visible(self):
        created = []
        def factory(path, events):
            watcher = _FakeWatcher(path, events); created.append(watcher); return watcher
        manager = DirectoryWatchManager(factory, supported=True)
        with tempfile.TemporaryDirectory() as raw:
            manager.sync([Path(raw)])
            manager.sync([])
        self.assertTrue(created[0].stopped)


if __name__ == "__main__":
    unittest.main()
