import faulthandler
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pycommander.debuglog import DiagnosticLog, diagnostic_records, diagnostic_summary
from pycommander.nativecrash import NativeCrashCapture, native_crash_record


class NativeCrashTests(unittest.TestCase):
    def header(self):
        return dict(version='0.18.old', session='abcdef123456', runtime={'python': '3.11.9'},
                    started_at='2026-10-28T09:00:00+08:00')

    def fixture(self, directory, dump):
        path = Path(directory) / 'pfc-native-abcdef123456.log'
        path.write_text(json.dumps(self.header()) + '\n' + dump, encoding='utf-8')
        return path

    def test_safe_card_preserves_crash_identity_and_faulting_frame(self):
        dump = ('Windows fatal exception: access violation\n\nCurrent thread 0x123:\n'
                '  File "C:\\PRIVATE\\pfc.py", line 42 in work\n'
                '  File "C:\\PRIVATE\\threading.py", line 99 in run\n\n'
                'Thread 0x456:\n  File "C:\\PRIVATE\\other.py", line 8 in wait\n')
        row = native_crash_record(self.header(), dump, 1792680000)
        card = diagnostic_summary(row)
        self.assertIn('0xC0000005', card)
        self.assertIn('0.18.old', card)
        self.assertIn('Python stack: pfc.py:42 · work', card)
        self.assertNotIn('PRIVATE', json.dumps(row) + card)
        self.assertNotIn('other.py', card)
        self.assertIsNotNone(__import__('datetime').datetime.fromisoformat(row['time']).utcoffset())
        self.assertEqual(row['crash_time_source'], 'journal_mtime')

    def test_recover_once_into_automatic_log_without_debug_mode(self):
        with tempfile.TemporaryDirectory() as raw:
            path = self.fixture(raw, 'Fatal Python error: Aborted\n\n'
                                     'Current thread 0x1:\n  File "/private/app.py", line 5 in work\n')
            log = DiagnosticLog('new-version', raw, automatic=True)
            try:
                capture = NativeCrashCapture(raw, 'new-version', log.session, {}, log._recover_native_record)
                capture.recover(); capture.recover()
                rows = [r for r in diagnostic_records(log.snapshot(automatic=True)) if r['event']=='process.native_crash']
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['version'], '0.18.old')
                self.assertEqual(rows[0]['session'], 'abcdef123456')
                self.assertFalse(path.exists())
                self.assertFalse(log.path.exists())
            finally:
                log.close()

    def test_prior_timeout_stack_is_not_reported_as_crash_stack(self):
        dump = ('Timeout (0:00:45)!\n  File "/old/wait.py", line 12 in wait\n\n'
                'Windows fatal exception: code 0xc000001d\n\n'
                'Thread 0x1:\n  File "/new/main.py", line 25 in run\n')
        row = native_crash_record(self.header(), dump, 0)
        self.assertEqual(row['native_code'], '0xC000001D')
        self.assertEqual(row['frames'], [dict(module='main.py', line=25, function='run')])

    def test_failed_append_retains_crash_and_timeout_is_not_failure(self):
        with tempfile.TemporaryDirectory() as raw:
            path = self.fixture(raw, 'Fatal Python error: Aborted\n')
            capture = NativeCrashCapture(raw, 'new', 'bbbbbbbbbbbb', {}, lambda row: False)
            capture.recover()
            self.assertTrue(path.exists())
            path.write_text(json.dumps(self.header())+'\nTimeout (0:00:45)!\n', encoding='utf-8')
            capture.recover()
            self.assertFalse(path.exists())
            self.assertIsNone(native_crash_record(self.header(), '', 0))

    def test_live_process_not_recovered_and_close_restores_handler(self):
        if faulthandler.is_enabled():
            self.skipTest('runner owns handler; isolated check tests ownership')
        with tempfile.TemporaryDirectory() as raw:
            capture = NativeCrashCapture(raw, 'test', 'aaaaaaaaaaaa', {}, lambda row: self.fail('live recovery'))
            try:
                self.assertIsNone(capture.start())
                self.assertTrue(faulthandler.is_enabled())
                other = NativeCrashCapture(raw, 'test', 'bbbbbbbbbbbb', {}, lambda row: self.fail('live recovery'))
                other.recover()
                self.assertTrue(capture.path.exists())
                self.assertEqual(other.start(), 'native-handler-already-installed')
                other.close()
                self.assertTrue(faulthandler.is_enabled())
            finally:
                capture.close(); capture.close()
            self.assertFalse(faulthandler.is_enabled())
            self.assertFalse(list(Path(raw).glob('pfc-native-*.log')))

    def test_storage_failure_does_not_change_global_handler(self):
        if faulthandler.is_enabled():
            self.skipTest('runner owns handler')
        with tempfile.TemporaryDirectory() as raw:
            capture = NativeCrashCapture(raw, 'test', 'aaaaaaaaaaaa', {}, lambda row: True)
            with patch('builtins.open', side_effect=PermissionError):
                self.assertEqual(capture.start(), 'native-crash-log-unavailable')
            self.assertFalse(faulthandler.is_enabled())

    def test_unreadable_journal_directory_does_not_break_startup(self):
        with tempfile.TemporaryDirectory() as raw:
            capture = NativeCrashCapture(raw, 'test', 'aaaaaaaaaaaa', {}, lambda row: True)
            with patch.object(Path, 'glob', side_effect=PermissionError):
                capture.recover()


if __name__ == '__main__':
    unittest.main()
