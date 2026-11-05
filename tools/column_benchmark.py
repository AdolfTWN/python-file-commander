"""Actual populated-folder column sizing: semantic widths, Tk traffic and time."""
import importlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

module_root=Path(sys.argv[sys.argv.index('--module-root')+1]) if '--module-root' in sys.argv else Path(__file__).resolve().parents[1]
sys.path.insert(0,str(module_root))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')


def pump(app,seconds=.2):
    until=time.monotonic()+seconds
    while time.monotonic()<until:app.update();time.sleep(.002)


with tempfile.TemporaryDirectory(prefix='pfc-column-bench-') as raw:
    root=Path(raw);folder=root/'data';folder.mkdir()
    for n in range(1500):
        path=folder/f'{n:05} Engineering 報告.txt'
        path.write_bytes(b'x'*((n%10+1)*120));os.utime(path,(1500000000,1500000000))
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**k:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander()
    try:
        app.auto_font_size_var.set(False);pump(app)
        app.geometry('1260x700+0+0')
        pane=app.left_tabs.current()
        started=time.perf_counter();pane.navigate(folder)
        navigation=time.perf_counter()-started
        app.update_idletasks();first_frame=time.perf_counter()-started
        pump(app,.5)
        original=pane.tree.item;calls=[0]
        def counted(*args,**kwargs):
            calls[0]+=1;return original(*args,**kwargs)
        pane.tree.item=counted
        samples=[];widths=[]
        for n in range(15):
            calls[0]=0;start=time.perf_counter();pane._autosize_columns()
            elapsed=time.perf_counter()-start
            current=[int(pane.tree.column(col,'width')) for col in ('#0',*pane.columns)]
            if n>=3:samples.append((elapsed,calls[0]));widths.append(current)
        assert all(w==widths[0] for w in widths)
        resize=[]
        for n in range(18):
            started=time.perf_counter()
            app.geometry(f'{1200 if n%2 else 1260}x700+0+0')
            app.update()
            elapsed=time.perf_counter()-started
            assert app.winfo_width()==(1200 if n%2 else 1260)
            if n>=4:resize.append(elapsed)
            pump(app,.025)
        print(json.dumps({'version':pfc.__version__,'rows':len(pane.tree.get_children()),
                          'navigation_sync_s':navigation,'navigation_first_idle_s':first_frame,
                          'autosize_median_s':statistics.median(s[0] for s in samples),
                          'autosize_range_s':[min(s[0] for s in samples),max(s[0] for s in samples)],
                          'tree_item_calls':sorted(set(s[1] for s in samples)),
                          'widths':widths[0],'samples':len(samples),
                          'resize_frame_median_s':statistics.median(resize),
                          'resize_frame_range_s':[min(resize),max(resize)]},sort_keys=True))
    finally:app.close_app()
