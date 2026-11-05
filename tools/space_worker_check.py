"""Out-of-order cancelled disk scans must not overwrite/strand a newer scan."""
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
scanner=importlib.import_module(pfc.SpaceAnalyzerWindow.__module__)


def until(app,predicate,timeout=5):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        app.update();time.sleep(.003)
        if predicate():return
    raise AssertionError('Scan scenario did not reach expected state')


with tempfile.TemporaryDirectory(prefix='pfc-space-worker-') as raw:
    root=Path(raw);a=root/'A';b=root/'B';c=root/'C'
    for folder in (a,b,c):folder.mkdir()
    entered={p:threading.Event() for p in (a,b,c)};release={p:threading.Event() for p in (a,b,c)}
    def controlled_scan(path,cancel):
        entered[path].set()
        if not release[path].wait(10):raise TimeoutError('Fixture scan was not released')
        if cancel.is_set():raise InterruptedError
        return scanner.SpaceNode(path,10,True,[])
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**k:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();window=None;workers=[]
    try:
        app.auto_font_size_var.set(False)
        with patch.object(scanner,'scan_space',controlled_scan):
            window=pfc.SpaceAnalyzerWindow(app,a,lambda *_:None,lambda *_:False,app.palette)
            until(app,lambda:entered[a].is_set());workers.append(window._worker)
            window.scan(b);until(app,lambda:entered[b].is_set());workers.append(window._worker)
            release[a].set();until(app,lambda:not workers[0].is_alive())
            # Keep the new scan pending across multiple poll intervals.
            end=time.monotonic()+.25
            while time.monotonic()<end:app.update();time.sleep(.003)
            assert 'disabled' in window.scan_button.state(),'Old cancellation changed newer scan state'
            release[b].set();until(app,lambda:window.root_node is not None and window.root_node.path==b)
            window.scan(c);until(app,lambda:entered[c].is_set());workers.append(window._worker)
            ref=weakref.ref(window);window.close();window=None;gc.collect()
            assert ref() is None,'Slow disk worker retains closed Tk window'
            release[c].set();workers[-1].join(3)
        print('PASS: stale disk-scan results ignored; newest scan completes; closed window not worker-owned')
    finally:
        for event in release.values():event.set()
        for worker in workers:worker.join(3)
        if window is not None:window.close()
        app.close_app()
