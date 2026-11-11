import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from types import SimpleNamespace
import configparser

from pycommander.directorydata import DirectoryReads


class DirectoryReadsTests(unittest.TestCase):
    def test_cancel_does_not_publish_and_latest_read_finishes(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            (folder/'item').touch()
            reader = DirectoryReads()
            entered, release = threading.Event(), threading.Event()
            original = Path.stat
            def stat(path, *args, **kwargs):
                if path == folder/'item' and not release.is_set():
                    entered.set()
                    release.wait(2)
                return original(path, *args, **kwargs)
            try:
                with patch.object(Path, 'stat', stat):
                    first=reader.submit('pane',folder,True,True)
                    self.assertTrue(entered.wait(1))
                    first.cancel()
                    release.set()
                    last=reader.submit('pane',folder,True,True)
                    self.assertTrue(last.done.wait(2))
                    self.assertEqual([r.path.name for r in last.result[1]],['item'])
                    self.assertIsNone(first.result)
                    self.assertTrue(first.cancelled.is_set())
            finally:
                release.set();reader.close()
                for worker in reader._threads:worker.join(2)
                self.assertFalse(any(w.is_alive() for w in reader._threads))

    def test_close_wakes_consumers_and_error_has_no_traceback(self):
        with tempfile.TemporaryDirectory() as raw:
            reader=DirectoryReads()
            try:
                job=reader.submit('missing',Path(raw)/'absent',False,False)
                self.assertTrue(job.done.wait(2))
                self.assertIsInstance(job.error,OSError)
                self.assertIsNone(job.error.__traceback__)
            finally:
                reader.close()
                for worker in reader._threads:worker.join(2)


class DirectoryAuditTests(unittest.TestCase):
    def test_shared_scan_waits_from_completion_and_newer_manual_rows_win(self):
        from pycommander.app import Commander
        clock=[100.]
        config=configparser.ConfigParser()
        config['refresh']={'active_interval_ms':'2000'}
        pane_args=dict(path=Path('/synthetic'),mode='files',archive_session=None,
            _directory_disposed=False,show_hidden=False,show_system=False,
            _search_reveal_path=None,_inline_editor=None,_drag_press_item=None,
            _directory_request=None,_listing_revision=0,_signature='old',
            _listing_failure_key=None,_listing_key=lambda:'listing')
        first=SimpleNamespace(**pane_args,refresh=Mock(),_listing_failed=Mock())
        second=SimpleNamespace(**pane_args,refresh=Mock(),_listing_failed=Mock())
        job=SimpleNamespace(done=threading.Event(),cancelled=threading.Event(),cancel=Mock(),
                            result=None,error=None)
        submit=Mock(return_value=job)
        owner=SimpleNamespace(_directory_audits={},_pending_directory_changes=set(),
            _network_refresh_due={},config_data=config,active=first,
            _directory_reader=SimpleNamespace(submit=submit),_ui_latency=None)
        with patch('pycommander.app.time.monotonic',lambda:clock[0]):
            Commander._audit_visible_panes(owner,[first,second])
            self.assertEqual(1,submit.call_count)
            Commander._audit_visible_panes(owner,[first,second])
            self.assertEqual(1,submit.call_count)
            # Simulate manual refresh on the first view during this scan.
            first._listing_revision=1
            job.result=(first.path,(), 'fresh')
            job.done.set();clock[0]=104.08
            Commander._audit_visible_panes(owner,[first,second])
            first.refresh.assert_not_called()
            second.refresh.assert_called_once_with()
            self.assertEqual([106.08],list(owner._network_refresh_due.values()))
            clock[0]=104.18
            Commander._audit_visible_panes(owner,[first,second])
            self.assertEqual(1,submit.call_count)

    def test_changed_view_options_cancel_the_old_snapshot(self):
        from pycommander.app import Commander
        config=configparser.ConfigParser()
        config['refresh']={}
        pane=SimpleNamespace(path=Path('/synthetic'),mode='files',archive_session=None,
            _directory_disposed=False,show_hidden=False,show_system=False,
            _search_reveal_path=None,_inline_editor=None,_drag_press_item=None,
            _directory_request=None,_listing_revision=0)
        first=SimpleNamespace(done=threading.Event(),cancel=Mock())
        second=SimpleNamespace(done=threading.Event(),cancel=Mock())
        submit=Mock(side_effect=[first,second])
        owner=SimpleNamespace(_directory_audits={},_pending_directory_changes=set(),
            _network_refresh_due={},config_data=config,active=pane,
            _directory_reader=SimpleNamespace(submit=submit),_ui_latency=None)
        Commander._audit_visible_panes(owner,[pane])
        pane.show_hidden=True
        Commander._audit_visible_panes(owner,[pane])
        first.cancel.assert_called_once_with()
        self.assertEqual([second],list(owner._directory_audits.values()))
