"""Measure a real global reading-scale change; count metadata in a separate pass."""
import importlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0,os.environ.get('PFC_AUDIT_ROOT',str(Path(__file__).resolve().parents[1])))
pfc=importlib.import_module('pfc')
with tempfile.TemporaryDirectory(prefix='pfc-font-bench-') as raw:
    root=Path(raw);folder=root/'Project';folder.mkdir()
    for index in range(1000):(folder/f'{index:04d}_review.md').write_text('alpha\n')
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**kw:True;pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();app.auto_font_size_var.set(False);app.vcs_overlay_var.set(False)
    app.geometry('1400x850')
    for pane in app.all_panes():pane.navigate(folder)
    app.update();app.after_cancel(app._auto_refresh_job);app._auto_refresh_job=None
    def scale(key):app.font_size_var.set(key);app.apply_font_size(save=False);app.update()
    try:
        scale('small');scale('large');scale('small')
        trials=[]
        for _ in range(3):
            scale('small');start=time.perf_counter();scale('large');trials.append(time.perf_counter()-start)
            assert all(len(p.tree.get_children())==1000 for p in app.all_panes())
        scale('small');calls=[];original=Path.stat
        def stat(path,*args,**kw):
            if path.parent==folder:calls.append(1)
            return original(path,*args,**kw)
        with patch.object(Path,'stat',stat):scale('large')
        print(json.dumps(dict(files=1000,bytes=6000,panes=len(app.all_panes()),
            task='100% to 150% font and settle',trials_seconds=trials,
            median_seconds=statistics.median(trials),separate_metadata_calls=len(calls))))
    finally:app.close_app()
