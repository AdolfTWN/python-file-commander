import tempfile
import unittest
import threading
import queue
from unittest.mock import patch
from unittest.mock import Mock
from pathlib import Path

from pycommander.search import SearchWindow, content_matches, name_matches, search_column_widths, search_attributes, search_files
from pycommander.i18n import tr
from types import SimpleNamespace


class SearchTests(unittest.TestCase):
    def test_fast_folder_progress_is_coalesced_and_final_count_remains_exact(self):
        root=Path('fixture');messages=queue.Queue();cancel=threading.Event()
        names=[f'folder-{n}' for n in range(500)]
        walk=[(root,names,[])]+[(root/name,[],[]) for name in names]
        criteria=dict(root=root,masks='*.missing',case=False,max_depth=None,files=True,folders=False,
                      min_size=None,max_size=None,since=None,content='')
        with patch('pycommander.search.os.walk',return_value=walk),\
                patch('pycommander.search.time.monotonic',return_value=0):
            search_files(criteria,cancel,messages)
        rows=list(messages.queue);progress=[row for row in rows if row[0]=='progress']
        self.assertEqual(progress[0],('progress',1,501))
        self.assertEqual(progress[-1],('progress',501,501))
        self.assertLessEqual(len(progress),2,'Every fast directory still queues redundant UI work')
        self.assertEqual(rows[-1],('done',0,False,False))

    def test_slow_folder_progress_stays_live_during_cancel(self):
        root=Path('fixture');messages=queue.Queue();cancel=threading.Event()
        criteria=dict(root=root,masks='*.missing',case=False,max_depth=None,files=True,folders=False,
                      min_size=None,max_size=None,since=None,content='')
        def walk(*a,**k):
            yield root,['one','two','three'],[]
            yield root/'one',[],[]
            yield root/'two',[],[]
            cancel.set()
            yield root/'three',[],[]
        with patch('pycommander.search.os.walk',walk),\
                patch('pycommander.search.time.monotonic',side_effect=[0,.11,.22]):
            search_files(criteria,cancel,messages)
        rows=list(messages.queue)
        self.assertEqual([row[1] for row in rows if row[0]=='progress'],[1,2,3])
        self.assertEqual(rows[-1],('done',0,True,False))

    def test_fast_cancel_flushes_the_last_processed_folder_count(self):
        root=Path('fixture');messages=queue.Queue();cancel=threading.Event()
        criteria=dict(root=root,masks='*.missing',case=False,max_depth=None,files=True,folders=False,
                      min_size=None,max_size=None,since=None,content='')
        def walk(*a,**k):
            yield root,['one','two','three'],[]
            yield root/'one',[],[]
            yield root/'two',[],[]
            cancel.set()
            yield root/'three',[],[]
        with patch('pycommander.search.os.walk',walk),\
                patch('pycommander.search.time.monotonic',side_effect=[0,.01,.02]):
            search_files(criteria,cancel,messages)
        rows=list(messages.queue)
        self.assertEqual([row[1] for row in rows if row[0]=='progress'],[1,3])
        self.assertEqual(rows[-1],('done',0,True,False))

    def test_activation_defers_geometry_without_recursively_pumping_tk(self):
        window=SimpleNamespace(_destroying=False,reset_for_open=Mock(),deiconify=Mock(),
            lift=Mock(),focus_force=Mock(),update_idletasks=Mock(),_finish_activation=Mock())
        with patch('pycommander.search.schedule_owned_idle') as schedule:
            SearchWindow.activate(window)
        window.update_idletasks.assert_not_called()
        schedule.assert_called_once_with(window,'activate-ready',window._finish_activation)
        window._destroying=True
        SearchWindow.activate(window)
        self.assertEqual(window.reset_for_open.call_count,1)

    def test_selective_search_does_not_stat_unmatched_names_and_still_descends_unmatched_folders(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);nested=root/'not-a-markdown-folder';nested.mkdir()
            (root/'ignored.txt').write_text('unrelated')
            hit=nested/'report.md';hit.write_text('NEEDLE')
            window=SimpleNamespace(cancel_event=threading.Event(),messages=queue.Queue())
            criteria=dict(root=root,masks='*.md',case=False,max_depth=None,files=True,folders=True,
                          min_size=None,max_size=None,since=None,content='NEEDLE')
            original=Path.stat;calls=[]
            def stat(path,*a,**kw):
                calls.append(path);return original(path,*a,**kw)
            with patch.object(Path,'stat',stat):SearchWindow._search(window,criteria)
            messages=list(window.messages.queue)
            self.assertEqual([row[1] for row in messages if row[0]=='item'],[hit])
            self.assertNotIn(root/'ignored.txt',calls);self.assertNotIn(nested,calls)
            self.assertEqual(calls,[hit])
            self.assertEqual(messages[-1],('done',1,False,False))

    def test_size_units_and_validation(self):
        def var(value):return SimpleNamespace(get=lambda:value)
        window=SimpleNamespace(depth_values={},depth_var=var('All'),path_var=var('.'),
            mask_var=var('*'),content_var=var(''),case_var=var(False),files_var=var(True),folders_var=var(True),
            min_size_var=var('1.5'),max_size_var=var('2'),days_var=var(''))
        for unit,factor in (('kB',1024),('MB',1024**2),('GB',1024**3)):
            window.size_unit_var=var(unit)
            self.assertEqual(SearchWindow.criteria(window)['min_size'],1.5*factor)
            self.assertEqual(SearchWindow.criteria(window)['max_size'],2*factor)
        window.min_size_var=var('3')
        with self.assertRaises(ValueError):SearchWindow.criteria(window)
        for invalid in ('nan','inf','-1','bad','1e309'):
            window.min_size_var=var(invalid)
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):SearchWindow.criteria(window)

    def test_hidden_system_notes_reuse_stat_attributes(self):
        for flags,expected in ((0,''),(2,tr('Hidden')),(4,tr('System')),
                               (6,tr('Hidden')+' · '+tr('System'))):
            self.assertEqual(search_attributes(Path('ordinary.txt'),SimpleNamespace(st_file_attributes=flags)),expected)
        self.assertEqual(search_attributes(Path('.config'),SimpleNamespace()),tr('Hidden'))
        self.assertEqual(search_attributes(Path('plain.txt'),SimpleNamespace()),'')
        self.assertEqual(search_attributes(Path('.config'),SimpleNamespace(st_file_attributes=4)),tr('Hidden')+' · '+tr('System'))
    def test_masks_and_partial_names(self):
        self.assertTrue(name_matches("Quarterly Report.xlsx", "report", False))
        self.assertTrue(name_matches("notes.txt", "*.txt;*.md", False))
        self.assertFalse(name_matches("notes.txt", "*.csv", False))

    def test_content_case(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "notes.txt"; path.write_text("Alpha beta", encoding="utf-8")
            self.assertTrue(content_matches(path, "alpha", False))
            self.assertFalse(content_matches(path, "alpha", True))

    def test_unreadable_content_is_reported_without_changing_boolean_contract(self):
        with tempfile.TemporaryDirectory() as raw:
            errors=[]
            self.assertFalse(content_matches(Path(raw)/'missing.txt','needle',False,on_error=lambda:errors.append(1)))
            self.assertEqual(errors,[1])
            self.assertTrue(content_matches(Path(raw)/'missing.txt','',False,on_error=lambda:errors.append(1)))
            self.assertEqual(errors,[1])

    def test_column_fit_uses_available_width(self):
        widths = search_column_widths(
            1000, {"name": 420, "folder": 600, "size": 90, "modified": 150, "ext": 60})
        self.assertLessEqual(sum(widths.values()), 1000)
        self.assertGreaterEqual(widths["name"], 130)
        self.assertGreaterEqual(widths["folder"], 150)

    def test_long_paths_do_not_compress_readable_names(self):
        widths=search_column_widths(1180,{'name':230,'folder':900,'attributes':230,
                                        'size':125,'modified':200,'ext':100})
        self.assertEqual(widths['name'],230)
        self.assertGreaterEqual(widths['folder'],150)


if __name__ == "__main__": unittest.main()
