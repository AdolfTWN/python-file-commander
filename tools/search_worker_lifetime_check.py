"""A slow cancelled search must not retain its closed Tk window in the worker."""
import gc
import importlib
from pathlib import Path
import sys
import tempfile
import threading
import time
import weakref
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')


def pump(app,seconds=.1):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.update();time.sleep(.003)


with tempfile.TemporaryDirectory(prefix='pfc-search-worker-lifetime-') as raw:
    root=Path(raw);folder=root/'data';folder.mkdir();item=folder/'slow.txt';item.write_text('NEEDLE')
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**k:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();entered=threading.Event();release=threading.Event();original=Path.stat
    def delayed_stat(path,*a,**kw):
        if path==item and threading.current_thread() is not threading.main_thread():
            entered.set()
            if not release.wait(10):raise TimeoutError('Fixture worker was not released')
        return original(path,*a,**kw)
    worker=None
    try:
        app.auto_font_size_var.set(False);pump(app)
        app.search();pump(app,.2);search=app.search_window
        search.path_var.set(str(folder));search.mask_var.set('*.txt')
        with patch.object(Path,'stat',delayed_stat):
            search.start();worker=search.worker
            deadline=time.monotonic()+3
            while not entered.is_set() and time.monotonic()<deadline:pump(app,.02)
            assert entered.is_set(),'Fixture did not pause worker I/O'
            ref=weakref.ref(search)
            search.close();app.search_window=None;del search
            gc.collect();pump(app)
            assert worker.is_alive(),'Fixture must inspect a still-running worker'
            assert ref() is None,'Cancelled worker retains a destroyed SearchWindow/Tk interpreter'
            release.set();worker.join(3)
            assert not worker.is_alive()
        print('PASS: cancelled slow search retains only data/queue/cancellation state, not Tk window')
    finally:
        release.set()
        if worker is not None:worker.join(3)
        app.close_app()
