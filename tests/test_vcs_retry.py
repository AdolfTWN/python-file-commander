import queue
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace, MethodType
from unittest.mock import patch

from pycommander import app, vcs


class OverlayRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.clock=20.0
        self.workers=[]
        self.enabled=True
        self.events=[]
        owner=SimpleNamespace(vcs_overlay_var=SimpleNamespace(get=lambda:self.enabled),
                              debug_log=SimpleNamespace(event=lambda *a,**kw:self.events.append((a,kw))))
        self.pane=SimpleNamespace(path=self.root,archive_session=None,_vcs_path=None,
            _vcs_statuses={},_vcs_requested_at=0,_vcs_generation=0,_vcs_inflight=None,
            _vcs_results=queue.Queue(),_vcs_loading=False,after=lambda *a:None,
            winfo_toplevel=lambda:owner,_apply_vcs_icons=lambda old:None)
        for name in ('_request_vcs_statuses','_poll_vcs_results'):
            setattr(self.pane,name,MethodType(getattr(app.FilePane,name),self.pane))
        for context in (
            patch.object(app.time,'monotonic',side_effect=lambda:self.clock),
            patch.object(app.threading,'Thread',side_effect=lambda **kw:
                         SimpleNamespace(start=lambda:self.workers.append(kw['target']))),
            patch.object(app,'cached_folder_statuses',return_value=None)):
            context.start();self.addCleanup(context.stop)

    def fail_and_poll(self,reason='tracked-files-timeout'):
        self.pane._request_vcs_statuses()
        with patch.object(app,'folder_statuses',side_effect=vcs.VcsOverlayError(reason,statuses={'known':'modified'})):
            self.workers[-1]()
        self.pane._poll_vcs_results()

    def test_timeout_recovers_without_navigation_or_refresh_and_keeps_partial_states(self):
        self.fail_and_poll()
        self.assertEqual(self.pane._vcs_statuses,{'known':'modified'})
        self.assertEqual(len(self.workers),1)
        self.clock+=.9;self.pane._poll_vcs_results()
        self.assertEqual(len(self.workers),1)
        self.clock+=.2;self.pane._poll_vcs_results()
        self.assertEqual(len(self.workers),2)
        with patch.object(app,'folder_statuses',return_value={'known':'modified','clean':'clean'}) as query:
            self.workers[-1]()
        query.assert_called_once_with(self.root,timeout=8)
        self.pane._poll_vcs_results()
        self.assertEqual(self.pane._vcs_statuses['clean'],'clean')
        self.assertIsNone(self.pane._vcs_retry_at)
        self.assertEqual(self.events[0][1]['attempt'],1)
        self.assertEqual(self.events[0][1]['command_timeout_seconds'],4)

    def test_persistent_timeout_is_bounded_to_one_automatic_retry(self):
        self.fail_and_poll('status-timeout')
        self.clock+=2;self.pane._poll_vcs_results()
        with patch.object(app,'folder_statuses',side_effect=vcs.VcsOverlayError('status-timeout')):
            self.workers[-1]()
        self.pane._poll_vcs_results()
        for _ in range(5):
            self.clock+=60;self.pane._poll_vcs_results()
        self.assertEqual(len(self.workers),2)
        self.assertIsNone(self.pane._vcs_retry_at)
        self.assertEqual(self.events[-1][1]['attempt'],2)
        self.assertEqual(self.events[-1][1]['command_timeout_seconds'],8)

    def assert_discard(self,action):
        self.fail_and_poll()
        if action=='navigate':self.pane.path=self.root/'another'
        elif action=='disable':self.enabled=False
        else:self.pane.archive_session=object()
        self.clock+=2;self.pane._poll_vcs_results()
        self.assertEqual(len(self.workers),1)
        self.assertIsNone(self.pane._vcs_retry_at)

    def test_navigation_discards_pending_retry(self):self.assert_discard('navigate')

    def test_disabled_overlay_discards_pending_retry(self):self.assert_discard('disable')

    def test_archive_discards_pending_retry(self):self.assert_discard('archive')

    def test_permanent_errors_do_not_retry(self):
        self.fail_and_poll('unsafe-ownership')
        self.clock+=60;self.pane._poll_vcs_results()
        self.assertEqual(len(self.workers),1)
        self.assertIsNone(self.pane._vcs_retry_at)

    def test_new_manual_query_supersedes_delayed_retry(self):
        self.fail_and_poll()
        self.clock+=20
        self.pane._request_vcs_statuses()
        self.assertIsNone(self.pane._vcs_retry_at)
        with patch.object(app,'folder_statuses',return_value={'clean':'clean'}):
            self.workers[-1]()
        self.pane._poll_vcs_results()
        self.clock+=20;self.pane._poll_vcs_results()
        self.assertEqual(len(self.workers),2)


if __name__=='__main__':unittest.main()
