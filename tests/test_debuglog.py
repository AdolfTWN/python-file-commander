import json
from pathlib import Path
import tempfile
import unittest

from pycommander.debuglog import DiagnosticLog


class DebugLogTests(unittest.TestCase):
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
