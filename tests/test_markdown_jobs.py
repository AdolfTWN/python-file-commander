import tempfile
import time
import unittest
import threading
from unittest import mock
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
format_worker_main=markdown_worker_main
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

    def test_sender_cleanup_swallow_broken_pipe_on_close(self):
        closed = threading.Event(); errors = []
        class Input:
            def write(self, value): raise BrokenPipeError('worker exited')
            def flush(self): pass
            def close(self):
                closed.set(); raise BrokenPipeError('buffered close')
        class Output:
            def readline(self, size): closed.wait(2); return b''
            def close(self): pass
        class Process:
            stdin = Input(); stdout = Output()
            def poll(self): return None
            def kill(self): pass
            def wait(self): return 0
        process = Process()
        with mock.patch('pycommander.mdjobs.subprocess.Popen', return_value=process), \
             mock.patch('threading.excepthook', side_effect=lambda exc: errors.append(exc)):
            self.jobs._start(); self.jobs.outgoing.put({'id':1})
            self.assertTrue(closed.wait(2))
            for thread in threading.enumerate():
                if thread.name.startswith('PFC-Markdown-'): thread.join(2)
        self.jobs.process = None
        self.assertFalse(errors)

    def test_format_worker_owns_and_cleans_private_profile_root(self):
        import os
        real_popen=__import__('subprocess').Popen
        self.jobs=MarkdownJobs(self.jobs.module_file,False,'format_worker_main')
        with mock.patch('pycommander.mdjobs.subprocess.Popen',wraps=real_popen) as start:
            self.jobs.submit({'value':'safe'})
            self.assertEqual(self.result()['value'],'safe')
        options=start.call_args.kwargs
        owned=Path(options['env']['PFC_STATIC_ROOT'])
        self.assertTrue(owned.is_dir())
        self.assertEqual(options['start_new_session'],os.name!='nt')
        self.jobs.close()
        until=time.monotonic()+4
        while owned.exists() and time.monotonic()<until:time.sleep(.02)
        self.assertFalse(owned.exists())

    def test_format_worker_entry_is_allowlisted(self):
        with self.assertRaises(ValueError):MarkdownJobs(self.jobs.module_file,False,'arbitrary_function')


if __name__=='__main__':unittest.main()
