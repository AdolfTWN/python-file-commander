"""Controlled fixture navigation/filter/search phases; no production paths."""
import importlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import threading
import time
from unittest.mock import patch

sys.path.insert(0,os.environ.get('PFC_AUDIT_ROOT',str(Path(__file__).resolve().parents[1])))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')
count=int(next((a.split('=')[1] for a in sys.argv if a.startswith('--count=')),'2000'))

with tempfile.TemporaryDirectory(prefix='pfc-benchmark-') as raw:
    root=Path(raw);folder=root/'Project';folder.mkdir()
    for i in range(count):(folder/f'{i:05d}_project_notes.md').write_text('alpha\n',encoding='utf-8')
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**kw:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();app.auto_font_size_var.set(False);app.vcs_overlay_var.set(False)
    pane=app.active;app.geometry('1400x900');app.update()
    # Keep periodic background refresh out of this controlled foreground task.
    # Normal refresh/watch correctness is covered separately by deep_tasks.
    app.after_cancel(app._auto_refresh_job);app._auto_refresh_job=None
    records=[]
    try:
        pane.navigate(folder);app.update()
        original=Path.stat
        for operation in ('refresh','filter','search'):
            repetitions=[]
            for trial in range(3):
                pane.quick_filter_var.set('');pane.refresh();app.update()
                calls={'main':0,'worker':0};phases={}
                def stat(path,*args,**kw):
                    if path.parent==folder:calls['main' if threading.current_thread() is threading.main_thread() else 'worker']+=1
                    return original(path,*args,**kw)
                def timed(label,call):
                    start=time.perf_counter();result=call();phases[label]=time.perf_counter()-start;return result
                with patch.object(Path,'stat',stat):
                    start=time.perf_counter()
                    if operation=='refresh':
                        timed('list_render',pane.refresh);timed('settle',app.update)
                        assert len(pane.tree.get_children())==count
                    elif operation=='filter':
                        timed('filter_render',lambda:pane.set_quick_filter('000'));timed('settle',app.update)
                        expected=sum('000' in f'{i:05d}_project_notes.md' for i in range(count))
                        assert len(pane.tree.get_children())==expected
                    else:
                        app.search();app.update();s=app.search_window;s.path_var.set(str(folder));s.mask_var.set('*.md')
                        poll=s._poll;poll_times=[]
                        def polled():
                            begin=time.perf_counter();result=poll();poll_times.append(time.perf_counter()-begin);return result
                        s._poll=polled;s.start();deadline=time.monotonic()+30
                        while s.worker is not None:
                            assert time.monotonic()<deadline,'Search fixture timed out'
                            app.update();time.sleep(.002)
                        phases['poll_total']=sum(poll_times);phases['poll_peak']=max(poll_times)
                        assert len(s.results)==count
                        s.close();app.search_window=None
                    elapsed=time.perf_counter()-start
                repetitions.append(dict(seconds=elapsed,metadata_calls=calls,phases=phases))
            records.append(dict(operation=operation,count=count,median_seconds=statistics.median(x['seconds'] for x in repetitions),trials=repetitions))
        print(json.dumps(records,indent=2))
    finally:app.close_app()
