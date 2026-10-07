"""Small architecture invariants, executable against source or portable builds."""
import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PORTABLE = __name__ == "__main__" and "pfc" in sys.argv
if PORTABLE:
    sys.argv.remove("pfc")
archive = importlib.import_module("pfc" if PORTABLE else "pycommander.archivefs")
watch = importlib.import_module("pfc" if PORTABLE else "pycommander.dirwatch")


class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pfc-architecture-check-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_manifest_queries_each_descendant_metadata_once(self):
        source = self.root / "source"; source.mkdir()
        (source / "empty").mkdir()
        (source / "note.md").write_bytes(b"note")
        calls = []
        real_stat = Path.stat
        def counted(path, *args, **kwargs):
            calls.append(path)
            return real_stat(path, *args, **kwargs)
        with patch.object(Path, "stat", counted):
            records, writable, total = archive._zip_input_manifest([source])
        # Some pathlib versions stat the selected root inside rglob as well.
        # Its O(1) entry check is separate from per-descendant snapshot reuse.
        self.assertLessEqual(len(calls), 4)
        self.assertEqual(calls.count(source / "empty"), 1)
        self.assertEqual(calls.count(source / "note.md"), 1)
        self.assertEqual(len(set(calls)), 3)
        self.assertEqual(total, 4)
        self.assertEqual([name for _, name, _ in writable], ["source/empty", "source/note.md"])
        self.assertEqual(len(records), 3)

    def test_selected_order_unicode_empty_folders_and_progress_preserved(self):
        folder = self.root / "資料夾"; folder.mkdir()
        (folder / "empty").mkdir()
        (folder / "note.md").write_bytes(b"abc")
        file = self.root / "first.md"; file.write_bytes(b"12")
        target = self.root / "result.zip"
        updates = []
        archive.create_zip_archive([file, folder], target, lambda *args: updates.append(args))
        with zipfile.ZipFile(target) as output:
            self.assertEqual(output.namelist(), ["first.md", "資料夾/empty/", "資料夾/note.md"])
            self.assertEqual(output.read("資料夾/note.md"), b"abc")
        self.assertEqual(updates, [(2, 5, "first.md"), (5, 5, "note.md"), (5, 5, "result.zip")])

    def test_duplicate_inputs_still_rejected_before_target_is_changed(self):
        paths = []
        for name in ("a", "b"):
            directory = self.root / name; directory.mkdir()
            path = directory / "same.md"; path.write_bytes(b"text"); paths.append(path)
        target = self.root / "result.zip"; target.write_bytes(b"preserved")
        with self.assertRaises(OSError): archive.create_zip_archive(paths, target)
        self.assertEqual(target.read_bytes(), b"preserved")

    def test_progress_callback_failure_preserves_target_and_cleans_staging(self):
        path = self.root / "note.md"; path.write_bytes(b"text")
        target = self.root / "result.zip"; target.write_bytes(b"preserved")
        def fail(*args): raise RuntimeError("cancelled callback")
        with self.assertRaises(RuntimeError): archive.create_zip_archive([path], target, fail)
        self.assertEqual(target.read_bytes(), b"preserved")
        self.assertFalse(list(self.root.glob(".pfc-zip-*")))

    def test_notification_storm_is_coalesced_and_queue_can_be_reused(self):
        manager = watch.DirectoryWatchManager(supported=False)
        self.addCleanup(manager.close)
        paths = [self.root / "a", self.root / "b"]
        for _ in range(1000):
            for path in paths: manager.events.put(path)
        self.assertEqual(manager.events.qsize(), 2)
        self.assertEqual(manager.drain(), {watch.directory_key(p) for p in paths})
        manager.events.put(paths[0])
        self.assertEqual(manager.drain(), {watch.directory_key(paths[0])})
        manager.events.join()

    def test_notification_drain_does_not_chase_new_events(self):
        manager = watch.DirectoryWatchManager(supported=False)
        self.addCleanup(manager.close)
        first, later = self.root / "first", self.root / "later"
        manager.events.put(first)
        original_get = manager.events.get_nowait
        def get():
            result = original_get(); manager.events.put(later); return result
        with patch.object(manager.events, "get_nowait", get):
            self.assertEqual(manager.drain(), {watch.directory_key(first)})
        self.assertEqual(manager.drain(), {watch.directory_key(later)})


if __name__ == "__main__":
    unittest.main(verbosity=2)
