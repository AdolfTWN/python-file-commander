import tempfile
import time
import unittest
from pathlib import Path

from pycommander.mdjobs import MarkdownJobs


class MarkdownJobsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        script=Path(self.temp.name)/'worker.py'
        script.write_text('''import sys,json,time
def markdown_worker_main():
    for raw in sys.stdin:
        item=json.loads(raw)
        time.sleep(item.get('delay',0))
        print(json.dumps(item),flush=True)
''',encoding='utf-8')
        self.jobs=MarkdownJobs(script,False)

    def tearDown(self):
        self.jobs.close()
        end=time.monotonic()+3
        while self.jobs.retiring and time.monotonic()<end:
            self.jobs.reap();time.sleep(.01)
        self.assertFalse(self.jobs.retiring)
        self.temp.cleanup()

    def result(self):
        end=time.monotonic()+3
        while time.monotonic()<end:
            result=self.jobs.poll()
            if result is not None:return result
            time.sleep(.01)
        self.fail('Worker did not return')

    def test_one_worker_is_reused_and_no_concurrent_job(self):
        self.assertTrue(self.jobs.submit({'value':'first'}))
        process=self.jobs.process
        self.assertFalse(self.jobs.submit({'value':'ignored'}))
        self.assertEqual(self.result()['value'],'first')
        self.assertTrue(self.jobs.submit({'value':'second'}))
        self.assertIs(self.jobs.process,process)
        self.assertEqual(self.result()['value'],'second')

    def test_cancel_does_not_wait_for_blocked_worker_and_stale_result_is_ignored(self):
        self.jobs.submit({'value':'old','delay':30})
        old=self.jobs.process
        start=time.monotonic();self.jobs.cancel()
        self.assertLess(time.monotonic()-start,.2)
        self.jobs.results.put((old,{'id':1,'value':'stale'}))
        end=time.monotonic()+3
        while not self.jobs.submit({'value':'new'}):
            self.assertLess(time.monotonic(),end);time.sleep(.01)
        self.assertEqual(self.result()['value'],'new')


if __name__=='__main__':unittest.main()
