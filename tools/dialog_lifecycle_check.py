"""Destroyed Settings/Search must release owned Tcl traces, not only widgets."""
import gc
import importlib
from pathlib import Path
import sys
import tempfile
import time
import weakref

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')


def pump(app):
    end=time.monotonic()+.07
    while time.monotonic()<end:app.update();time.sleep(.004)


with tempfile.TemporaryDirectory(prefix='pfc-dialog-lifetime-') as raw:
    root=Path(raw);folder=root/'files';folder.mkdir();(folder/'a.txt').write_text('Fixture')
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**k:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();refs=[];counts=[]
    try:
        app.auto_font_size_var.set(False);pump(app)
        for cycle in range(10):
            app.show_settings('navigation');d=app.settings_window;pump(app)
            # Rebuilding prefix controls must also release their variable traces.
            for page in ('appearance','navigation','columns'):d.show_page(page);pump(app)
            refs.append(weakref.ref(d));d.cancel();del d
            app.search();s=app.search_window;pump(app)
            refs.append(weakref.ref(s));s.close();del s
            gc.collect();pump(app)
            counts.append(len(app.tk.splitlist(app.tk.call('info','commands'))))
        # One last closed window per app reference may be retained deliberately;
        # older windows have no legitimate root lifetime.
        alive=[i for i,ref in enumerate(refs[:-2]) if ref() is not None]
        assert not alive,('Destroyed dialogs retained by Tcl callbacks',alive,counts)
        assert max(counts[3:])-min(counts[3:])<=12,('Tcl commands grow per cycle',counts)
        print('PASS: destroyed dialogs collected; owned variable traces and prefix-page rebuilds bounded',counts)
    finally:app.close_app()
