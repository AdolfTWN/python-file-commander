"""Destroyed previews must not leave Tk image finalizers for a worker GC."""
import gc
import importlib
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
import traceback

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')


def pump(app,seconds=.15):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.update();time.sleep(.003)


with tempfile.TemporaryDirectory(prefix='pfc-tk-ownership-') as raw:
    folder=Path(raw);document=folder/'tree.json';document.write_text('{"key":{"value":"NEEDLE"}}')
    left=folder/'left';right=folder/'right';left.mkdir();right.mkdir()
    (left/'note.txt').write_text('left\n');(right/'note.txt').write_text('right\n')
    pfc.Commander._find_ini_path=staticmethod(lambda:folder/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**k:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();failures=[]
    original_init=tk.Image.__init__;original_del=tk.Image.__del__
    def image_init(self,*a,**kw):
        original_init(self,*a,**kw)
        self._test_origin=[f'{Path(frame.filename).name}:{frame.lineno}:{frame.name}' for frame in traceback.extract_stack(limit=7)]
    def image_del(self):
        if threading.current_thread() is not threading.main_thread() and self.name:
            failures.append(('worker-image-finalizer',self._test_origin))
        original_del(self)
    tk.Image.__init__=image_init;tk.Image.__del__=image_del
    previous=sys.unraisablehook
    sys.unraisablehook=lambda event:failures.append(('unraisable',event.exc_type.__name__,
        [(Path(frame.filename).name,frame.name,frame.lineno) for frame in traceback.extract_tb(event.exc_traceback)]))
    def close_preview():
        app.preview_paths([document],document);pump(app,.4)
        app.preview_window.close();app.preview_window=None
    def close_settings():
        app.show_settings();pump(app)
        for category,_label in pfc.SETTINGS_CATEGORIES:
            app.settings_window.show_page(category);pump(app,.04)
        app.settings_window.cancel();app.settings_window=None
    def close_tab():
        tabs=app.left_tabs
        tabs.add_tab(folder);pump(app)
        tabs.close_current();pump(app)
        app.set_active(tabs.current())
    def close_compare(left,right):
        window=pfc.CompareWindow(app,app.config_data,app.save_config)
        window.add(left,right);pump(app,.3)
        window.close()
    try:
        app.auto_font_size_var.set(False);pump(app)
        gc.collect()
        before_fonts=set(app.tk.splitlist(app.tk.call('font','names')))
        # Suppress incidental automatic GC only inside this deterministic
        # fixture, then intentionally collect destroyed widget cycles in a
        # background thread. This is not an application GC policy change.
        enabled=gc.isenabled();gc.disable()
        for scenario in (close_preview,close_settings,close_tab,
                         lambda:close_compare(left/'note.txt',right/'note.txt'),
                         lambda:close_compare(left,right)):
            scenario()
            worker=threading.Thread(target=gc.collect,name='PFC-Test-GC');worker.start()
            while worker.is_alive():pump(app,.03)
            worker.join()
        after_fonts=set(app.tk.splitlist(app.tk.call('font','names')))
        root_cached={str(font) for font in (getattr(app,'_compare_chrome_font',None),) if font is not None}
        root_cached.update(str(font) for font in getattr(app,'_settings_fonts',{}).values())
        if after_fonts-before_fonts-root_cached:failures.append(('orphaned-fonts',sorted(after_fonts-before_fonts-root_cached)))
        assert not failures,failures
        print('PASS: destroyed Preview/Settings/file-tab/Compare Tk resources released before worker collection')
    finally:
        tk.Image.__init__=original_init;tk.Image.__del__=original_del
        sys.unraisablehook=previous
        if enabled:gc.enable()
        app.close_app()
