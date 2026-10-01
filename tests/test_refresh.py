import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import queue
import threading
import configparser
from pathlib import Path

from pycommander.app import FilePane, Commander
from pycommander.dirwatch import DirectoryWatchManager, directory_key, _WindowsDirectoryWatcher


class RefreshSignatureTests(unittest.TestCase):
    def test_fallback_updates_all_visible_copies_of_a_folder(self):
        config = configparser.ConfigParser()
        config['refresh'] = {'auto_refresh': 'true', 'active_interval_ms': '2000'}
        panes = [SimpleNamespace(path=Path('Downloads'), mode='files', archive_session=None,
                                 refresh_if_changed=Mock()) for _ in range(2)]
        owner = SimpleNamespace(config_data=config, visible_panes=lambda: panes,
            active=panes[1], cloud_status=SimpleNamespace(roots=[]),
            _directory_watches=SimpleNamespace(sync=lambda paths: set(), drain=lambda: set()),
            _pending_directory_changes=set(), _network_refresh_due={})
        Commander._auto_refresh_visible(owner)
        for pane in panes: pane.refresh_if_changed.assert_called_once_with()
        Commander._auto_refresh_visible(owner)
        for pane in panes: self.assertEqual(pane.refresh_if_changed.call_count, 1)

    def test_transient_failure_does_not_kill_refresh_timer(self):
        owner = SimpleNamespace(_auto_refresh_job='old',
            _auto_refresh_visible=Mock(side_effect=OSError('transient shell failure')),
            _schedule_auto_refresh=Mock())
        with self.assertRaises(OSError): Commander._auto_refresh_tick(owner)
        owner._schedule_auto_refresh.assert_called_once_with(100)

    def test_native_overflow_invalidates_directory(self):
        watcher = object.__new__(_WindowsDirectoryWatcher)
        watcher._lock = threading.Lock(); watcher._stopping = threading.Event()
        watcher._handle = 1; watcher.path = Path('Downloads'); watcher._events = queue.Queue()
        def read(*args):
            watcher._stopping.set()
            return True  # returned byte count is zero, i.e. lost/overflowed events
        watcher._kernel32 = SimpleNamespace(ReadDirectoryChangesW=read)
        watcher._run()
        self.assertEqual(watcher._events.get_nowait(), Path('Downloads'))

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
