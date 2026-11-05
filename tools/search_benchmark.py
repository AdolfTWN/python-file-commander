"""Measure an actual selective F4 search, separating worker/UI completion."""
import importlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

module_root=Path(sys.argv[sys.argv.index('--module-root')+1]) if '--module-root' in sys.argv else Path(__file__).resolve().parents[1]
sys.path.insert(0,str(module_root))
pfc=importlib.import_module('pycommander.app')


def pump(app,seconds=.1):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.update();time.sleep(.002)


with tempfile.TemporaryDirectory(prefix='pfc-selective-search-') as raw:
    root=Path(raw);folder=root/'data';folder.mkdir();total=6000
    for n in range(total):(folder/f'entry-{n:05}.{ "md" if n%100==0 else "txt" }').write_text('NEEDLE')
    expected={path for path in folder.iterdir() if path.suffix=='.md'}
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**k:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();original=Path.stat;stat_calls=[0]
    def stat(path,*a,**kw):
        if path.parent==folder and path.name.startswith('entry-'):stat_calls[0]+=1
        return original(path,*a,**kw)
    try:
        app.auto_font_size_var.set(False);pump(app)
        app.search();pump(app,.3);search=app.search_window;search.path_var.set(str(folder));search.mask_var.set('*.md')
        search.files_var.set(True);search.folders_var.set(False);pump(app)
        samples=[]
        Path.stat=stat
        for repeat in range(5):
            stat_calls[0]=0;start=time.perf_counter();search.start();worker_done=None
            deadline=time.monotonic()+30
            while search.worker is not None and time.monotonic()<deadline:
                app.update()
                if search.worker is not None and not search.worker.is_alive() and worker_done is None:
                    worker_done=time.perf_counter()-start
                time.sleep(.002)
            app.update_idletasks();elapsed=time.perf_counter()-start
            assert search.worker is None,'Search completion timed out'
            assert set(search.results)==expected,(len(search.results),len(expected))
            samples.append({'elapsed_s':elapsed,'worker_observed_s':worker_done,'file_stat_calls':stat_calls[0],
                            'results':len(search.results)})
            pump(app,.1)
        print(json.dumps({'version':pfc.__version__,'input_files':total,'mask':'*.md','samples':samples,
                          'completion_median_s':statistics.median(row['elapsed_s'] for row in samples[1:])}),flush=True)
    finally:
        Path.stat=original
        app.close_app()
