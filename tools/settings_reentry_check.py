"""Focus during a settings-page destroy must not pump Tk recursively."""
import importlib
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')


def pump(app,seconds=.1):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.update();time.sleep(.003)


with tempfile.TemporaryDirectory(prefix='pfc-settings-reentry-') as raw:
    root=Path(raw)
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**k:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();nested=[];errors=[]
    original_callback=app.report_callback_exception
    def callback(*exc):errors.append(exc[0].__name__);original_callback(*exc)
    app.report_callback_exception=callback
    try:
        app.auto_font_size_var.set(False);app.show_settings('navigation');pump(app)
        dialog=app.settings_window
        victim=dialog.page.winfo_children()[0]
        # Append a test-owned entry last so it remains alive while the first
        # sibling's native Destroy event is being delivered.
        entry=pfc.ttk.Entry(dialog.page);entry.pack();pump(app)
        original=dialog.update_idletasks;in_destroy=[False]
        def guarded_update():
            if in_destroy[0]:
                nested.append('update_idletasks during native child destruction')
                return  # Observe, without actually entering the unsafe nested loop.
            return original()
        dialog.update_idletasks=guarded_update
        def destroying(event):
            if event.widget is not victim:return
            in_destroy[0]=True
            try:entry.event_generate('<FocusIn>')
            finally:in_destroy[0]=False
        victim.bind('<Destroy>',destroying,add='+')
        dialog.show_page('columns');pump(app)
        assert not nested,nested
        assert not errors,errors
        print('PASS: real focus event during page teardown does not reenter Tk idle processing')
        dialog.cancel()
    finally:app.close_app()
