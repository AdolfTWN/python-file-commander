"""Real F4 many-folder traversal: exact terminal counts, bounded progress, no lost items."""
import importlib
import math
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
api=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')
backend=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.search')

with tempfile.TemporaryDirectory(prefix='pfc-search-progress-') as raw:
    root=Path(raw);data=root/'data';data.mkdir();expected=set()
    for n in range(3000):
        folder=data/f'folder-{n:04}';folder.mkdir()
        path=folder/'entry.dat';path.write_bytes(b'fixture');expected.add(path)
    api.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    api.Commander._sync_auto_start=lambda *a,**k:True
    api.Commander._start_windows_tray=lambda *a:None
    app=api.Commander();errors=[];pulses=[];beat_job=None;stats={}
    app.report_callback_exception=lambda *exc:errors.append(exc[0].__name__)
    def pump(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:app.update();time.sleep(.003)
    def beat():
        global beat_job
        pulses.append(time.monotonic());beat_job=app.after(20,beat)
    original=backend.search_files
    def worker(*a,**k):
        started=time.monotonic()
        try:return original(*a,**k)
        finally:stats['worker_seconds']=time.monotonic()-started
    try:
        app.auto_font_size_var.set(False);pump(.2);app.search();pump(.4)
        search=app.search_window;search.path_var.set(str(data))
        search.files_var.set(True);search.folders_var.set(False)
        original_put=search.messages.put
        def put(message,*a,**k):
            if message[0]=='progress':stats['progress']+=1
            return original_put(message,*a,**k)
        search.messages.put=put;backend.search_files=worker;beat()
        def run(mask):
            stats.clear();stats['progress']=0;search.mask_var.set(mask);search.start()
            worker_thread=search.worker
            deadline=time.monotonic()+90
            while search.worker is not None or worker_thread.is_alive():
                app.update();time.sleep(.003)
                assert time.monotonic()<deadline,'Search did not reach a terminal state'
            assert search._scanned_folders==3001,search._scanned_folders
            assert stats['progress']<=math.ceil(stats['worker_seconds']/backend.SEARCH_PROGRESS_INTERVAL)+2,stats
            assert not search.progress.winfo_ismapped(),'Completed search still animates'
            assert search._elapsed_finished is not None
            assert not errors,errors
        run('*.missing')
        assert search.search_state=='complete' and not search.results
        assert search.empty_hint.winfo_ismapped(),'Empty completion has no visible explanation'
        # Items and unreadable counts are not disposable progress snapshots.
        denied=data/'folder-0000'/'entry.dat';original_stat=Path.stat
        def stat(path,*a,**k):
            if path==denied:raise PermissionError('fixture denied')
            return original_stat(path,*a,**k)
        with patch.object(Path,'stat',stat):run('*.dat')
        assert search.search_state=='partial' and search._skipped==1
        assert set(search.results)==expected-{denied},('Lost matching items',len(search.results))
        assert len(pulses)>4 and max(b-a for a,b in zip(pulses,pulses[1:]))<5,'F4 blocked event processing'
        print('PASS: 3001 folders scanned; bounded live/final progress; zero-result completion visible; 2999 items and one unreadable preserved')
    finally:
        backend.search_files=original
        if beat_job is not None:app.after_cancel(beat_job)
        app.close_app()
