"""Offline native metadata smoke check + injected cloud status UI regression."""
import base64
import ctypes
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
module=importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')
cloud=module if module.__name__=='pfc' else importlib.import_module('pycommander.cloudstatus')
icons=module if module.__name__=='pfc' else importlib.import_module('pycommander.icons')

def settle(app,seconds=.2):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        app.update(); time.sleep(.01)

with tempfile.TemporaryDirectory() as raw:
    root=Path(raw)/'cloud-fixture'; root.mkdir()
    paths=[]
    for state in cloud.CLOUD_LABELS:
        path=root/(state+'.txt'); path.write_text('fixture'); paths.append(path)
    if os.name=='nt':
        hr=ctypes.windll.ole32.CoInitializeEx(None,2)
        try:
            # Ordinary local files must not be falsely labeled as synchronized.
            assert cloud.read_cloud_status(paths[0]) is None
            assert cloud.read_cloud_status(root/'absent.txt') is None
            assert not module.is_hidden(paths[0])
            assert ctypes.windll.kernel32.SetFileAttributesW(str(paths[0]),2)
            try: assert module.is_hidden(paths[0])
            finally: ctypes.windll.kernel32.SetFileAttributesW(str(paths[0]),0x80)
        finally:
            if hr>=0: ctypes.windll.ole32.CoUninitialize()
        print('PASS: native fast property store ABI, ordinary/missing file, Windows hidden attribute',flush=True)
    module.Commander._find_ini_path=staticmethod(lambda:Path(raw)/'pfc.ini')
    module.Commander._sync_auto_start=lambda self,**kw:True
    app=module.Commander(); errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False); app.geometry('1500x760')
        app.cloud_status=cloud.CloudStatusCache([root],lambda p:Path(p).stem)
        pane=app.left_tabs.current(); pane.navigate(root); app.set_active(pane)
        settle(app,.7)
        rows=pane.tree.get_children()
        assert all(app.cloud_status.get(path)==path.stem for path in paths)
        for iid in rows:
            path=Path(pane.tree.item(iid,'tags')[0])
            assert 'OneDrive:' in pane._tooltip_name(iid)
            assert cloud.CLOUD_LABELS[path.stem] in pane._tooltip_name(iid)
        images=[]
        display=tk.Toplevel(app); display.title('OneDrive badge regression fixture (not live sync)')
        for column,state in enumerate(cloud.CLOUD_LABELS):
            image=tk.PhotoImage(data=base64.b64encode(icons.cloud_badge_png(32,state)).decode(),format='png')
            images.append(image)
            tk.Label(display,image=image,text=state,compound='top').grid(row=0,column=column,padx=12,pady=12)
        settle(app)
        original_ids=pane.tree.get_children()
        app.onedrive_overlay_var.set(False); app.apply_column_settings(); settle(app)
        assert all('OneDrive:' not in pane._tooltip_name(iid) for iid in rows)
        app.onedrive_overlay_var.set(True); app.apply_column_settings(); settle(app)
        pane._drag_press_item=rows[0]
        assert not any(p is pane for p,_,_ in app._visible_cloud_rows([pane]))
        pane._drag_press_item=None
        assert pane.tree.get_children()==original_ids
        assert not errors,errors
        if '--pause' in sys.argv: settle(app,20)
        print('PASS: injected seven-state overlays, async cache, tooltip, preference, stable row IDs and drag deferral',flush=True)
        print('NOTE: offline VM does not validate real OneDrive provider sync transitions.',flush=True)
    finally: app.destroy()
