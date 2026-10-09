import json
from pathlib import Path
import tempfile
import unittest
import logging
import warnings
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from pycommander.debuglog import DiagnosticLog


class DebugLogTests(unittest.TestCase):
    def test_automatic_errors_with_debug_disabled_and_version_per_record(self):
        with tempfile.TemporaryDirectory() as raw:
            log=DiagnosticLog('0.18.test', raw, automatic=True)
            try:
                log.event('detail.hidden')
                log.event('worker.warning', severity='WARNING')
                try: raise ValueError('PRIVATE DOCUMENT')
                except ValueError as exc: log.exception('preview.failed', exc)
                self.assertFalse(log.path.exists())
                events=[json.loads(s) for s in log.snapshot(automatic=True).splitlines()]
                self.assertEqual([e['severity'] for e in events], ['INFO','WARNING','ERROR'])
                for entry in events:
                    self.assertEqual(entry['version'], '0.18.test')
                    self.assertEqual(entry['session'], log.session)
                    self.assertIsNotNone(datetime.fromisoformat(entry['time']).utcoffset())
                    self.assertIsNotNone(datetime.fromisoformat(entry['utc_time']).utcoffset())
                self.assertNotIn('PRIVATE',log.snapshot(automatic=True))
            finally: log.close()

    def test_hooks_restore_and_concurrent_records_are_valid(self):
        with tempfile.TemporaryDirectory() as raw:
            old=warnings.showwarning
            log=DiagnosticLog('test',raw,automatic=True)
            try:
                log.install_hooks()
                with warnings.catch_warnings(record=True):
                    # catch_warnings changes the warning renderer: exercise our
                    # installed observer directly without emitting test noise.
                    observer=next(new for obj,name,new,prev in log._hooks if name=='showwarning')
                    from unittest.mock import patch
                    with patch.object(warnings,'_showwarnmsg_impl'):
                        observer('PRIVATE CONTENT',UserWarning,__file__,10)
                logging.getLogger('pfc.test').warning('PRIVATE CONTENT')
                with ThreadPoolExecutor(max_workers=4) as pool:
                    list(pool.map(lambda n:log.event('parallel',severity='WARNING',index=n),range(80)))
                rows=[json.loads(s) for s in log.snapshot(automatic=True).splitlines()]
                self.assertEqual(len([r for r in rows if r['event']=='parallel']),80)
                self.assertTrue(any(r['event']=='logging.warning' for r in rows))
                self.assertTrue(any(r['event']=='python.warning' for r in rows))
                self.assertNotIn('PRIVATE',log.snapshot(automatic=True))
            finally: log.close()
            self.assertIs(warnings.showwarning,old)
            self.assertIsNone(log.error_handler)

    def test_off_by_default_and_private_metadata(self):
        with tempfile.TemporaryDirectory() as raw:
            log = DiagnosticLog('test', Path(raw)/'logs')
            file = Path(raw)/'private-name.md'; file.write_text('CONFIDENTIAL DOCUMENT')
            log.file('preview.request', file)
            self.assertFalse(log.path.exists())
            self.assertTrue(log.set_enabled(True))
            log.file('preview.request', file)
            try: raise ValueError('CONFIDENTIAL DOCUMENT '+str(file))
            except ValueError as exc: log.exception('preview.failed', exc)
            snapshot=log.snapshot()
            self.assertNotIn('CONFIDENTIAL',snapshot)
            self.assertNotIn(str(file),snapshot)
            self.assertNotIn(file.name,snapshot)
            events=[json.loads(line) for line in snapshot.splitlines()]
            self.assertEqual(events[-1]['error'],'ValueError')
            self.assertTrue(events[-1]['frames'])
            self.assertEqual(events[-2]['bytes'],len('CONFIDENTIAL DOCUMENT'))
            log.set_enabled(False); before=log.snapshot();log.event('must-not-write')
            self.assertEqual(before,log.snapshot())

    def test_rotation_and_unwritable_location(self):
        with tempfile.TemporaryDirectory() as raw:
            log=DiagnosticLog('test',raw);log.set_enabled(True)
            log.handler.maxBytes=256
            for i in range(30):log.event('test',index=i)
            log.set_enabled(False)
            self.assertLessEqual(len(list(Path(raw).glob('pfc-debug.jsonl*'))),3)
            bad=Path(raw)/'file';bad.write_text('not-directory')
            broken=DiagnosticLog('test',bad)
            self.assertFalse(broken.set_enabled(True))
            broken.event('no-crash')


if __name__=='__main__': unittest.main()
