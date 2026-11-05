"""Stage-level native GDI attribution; repeated operations use fixed inputs."""
import ctypes
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from ctypes import wintypes as w

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
if os.name!='nt':
    print('SKIP: GDI resource attribution requires Windows')
    raise SystemExit(0)
pfc=importlib.import_module('pfc')
kernel=ctypes.WinDLL('kernel32');user=ctypes.WinDLL('user32')
kernel.GetCurrentProcess.restype=w.HANDLE
user.GetGuiResources.argtypes=[w.HANDLE,w.DWORD];user.GetGuiResources.restype=w.DWORD


def pump(app,seconds=.06):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.update();time.sleep(.003)


def sample(app,cycle,stage):
    row={'cycle':cycle,'stage':stage,'gdi':user.GetGuiResources(kernel.GetCurrentProcess(),0),
         'images':len(app.tk.splitlist(app.tk.call('image','names'))),
         'fonts':len(app.tk.splitlist(app.tk.call('font','names')))}
    print(json.dumps(row),flush=True);return row


with tempfile.TemporaryDirectory(prefix='pfc-gdi-lifetime-') as raw:
    root=Path(raw);folder=root/'data';folder.mkdir()
    document=folder/'tree.json';document.write_text('{"name":"NEEDLE"}')
    compare_roots=[root/'left',root/'right']
    for directory in compare_roots:
        directory.mkdir();(directory/'note.txt').write_text(directory.name+'\n')
    review_paths=[root/'wide-left.md',root/'wide-right.md']
    content=''.join(f'{n:05}: '+('wide review '*100)+'\n' for n in range(2048))
    for side,path in enumerate(review_paths):path.write_text(content.replace('00064:','CHANGED:' if side else '00064:',1))
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**k:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander()
    try:
        app.auto_font_size_var.set(False);app.active.navigate(folder);pump(app,.3)
        sample(app,0,'initial');closed=[]
        for cycle in range(18):
            app.font_size_var.set(('small','large','xl')[cycle%3]);app.select_manual_font_size();pump(app)
            sample(app,cycle,'scaled')
            app.show_settings();pump(app,.03);app.settings_window.cancel();pump(app,.03)
            sample(app,cycle,'settings-closed')
            app.preview_paths([document],document);pump(app,.12);app.preview_window.close();pump(app,.03)
            sample(app,cycle,'preview-closed')
            app.search();pump(app,.04);app.search_window.close();pump(app,.03)
            sample(app,cycle,'search-closed')
            for pair in ([directory/'note.txt' for directory in compare_roots],compare_roots,review_paths):
                app.compare_paths(*pair);pump(app,.2 if pair is review_paths else .1)
                app.compare_window.close();pump(app,.03)
            closed.append(sample(app,cycle,'compare-closed'))
        for phase in range(3):
            counts=[row['gdi'] for row in closed if row['cycle']>=6 and row['cycle']%3==phase]
            assert max(counts)-min(counts)<=6,('Native GDI growth at the same settled scale',phase,counts)
        print('PASS: fixed-input native GDI counts bounded across repeated same-scale dialog cycles')
    finally:app.close_app()
