"""F3 saved/live offscreen recovery, smaller laptop work area and photo diagnostics."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')


def settle(app, seconds=.15):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.update();time.sleep(.01)


def until(app,predicate,timeout=6):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        app.update()
        if predicate():return
        time.sleep(.02)
    raise AssertionError('Preview did not become reachable')


def visible(window):
    guard=window._window_visibility
    if os.name=='nt':state=guard.backend.snapshot()
    else:
        x,y=window.winfo_rootx(),window.winfo_rooty()
        state=((x,y,x+window.winfo_width(),y+window.winfo_height()),
               ((0,0,window.winfo_screenwidth(),window.winfo_screenheight()),),0)
    if not state:return False
    (l,t,r,b),areas,margin=state
    return any(l>=a-margin and t>=c-margin and r<=d+margin and b<=e+margin
               for a,c,d,e in areas)


def move(window):
    if os.name=='nt':window._window_visibility.backend.move((5000,120,1100,650))
    else:window.geometry('1100x650+5000+120')


def capture(window,name):
    window.lift();settle(window,.15)
    if os.name=='nt':
        from folder_native_test_support import capture_window
        capture_window(window,Path(__file__).parent/('evidence-preview-visibility-'+name+'.bmp'))
    elif os.environ.get('PFC_PREVIEW_SCREENSHOT_DIR'):
        from PIL import ImageGrab
        x,y=window.winfo_rootx(),window.winfo_rooty()
        ImageGrab.grab((x,y,x+window.winfo_width(),y+window.winfo_height())).save(
            str(Path(os.environ['PFC_PREVIEW_SCREENSHOT_DIR'])/(name+'.png')))


with tempfile.TemporaryDirectory(prefix='pfc-preview-placement-') as raw:
    folder=Path(raw);ini=folder/'pfc.ini';document=folder/'fixture.json'
    document.write_text('{"parent":{"ConnectedDeviceName":"fixture AW27"}}',encoding='utf-8')
    ini.write_text('[window]\ngeometry=1000x650+20+20\n[preview]\ngeometry=1800x1050+5000+120\n',encoding='utf-8')
    pfc.Commander._find_ini_path=staticmethod(lambda:ini)
    pfc.Commander._sync_auto_start=lambda *a,**k:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False)
        app.preview_paths([document],document)
        window=app.preview_window
        until(app,lambda:visible(window))
        until(app,lambda:window.active_page._format_active)
        page=window.active_page
        capture(window,'startup')
        # Move the actual frame away; the timer must recover it without a
        # second F3 invocation, keyboard shortcut or document reload.
        move(window);settle(app,.1)
        assert window.winfo_rootx()>window.winfo_screenwidth()
        until(app,lambda:visible(window))
        assert window.active_page is page and page._loaded
        records=pfc.diagnostic_records(app.debug_log.snapshot(automatic=True))
        recovered=[r for r in records if r['event']=='window.placement.recovery'
                   and r.get('window',{}).get('role')=='F3 Preview']
        assert recovered and any(r['window']['before'][0]>=5000 for r in recovered)
        card=pfc.diagnostic_summary(recovered[-1])
        assert 'F3 Preview' in card and 'Available work areas:' in card
        assert all('fixture.json' not in repr(r['window']) for r in recovered)
        if os.name=='nt':
            window.state('zoomed');settle(app);window._window_visibility.recover();settle(app)
            assert window.state()=='zoomed'
            window.state('normal');settle(app)
            window.iconify();settle(app,2.2)
            assert window.state()=='iconic'
            window.deiconify();settle(app)
        move(window);app.preview_paths([document],document)
        until(app,lambda:visible(window))
        assert app.preview_window is window
        for key,value in app._font_scales.items():
            if value==2.0:
                app.font_size_var.set(key);app.apply_font_size(save=False);break
        if os.name=='nt':
            backend=window._window_visibility.backend;original=backend.snapshot
            def laptop():
                state=original()
                return (state[0],((0,0,1280,680),),state[2]) if state else None
            backend.snapshot=laptop
        window.geometry('2200x1400+40+40');window.activate()
        until(app,lambda:visible(window))
        capture(window,'laptop200')
        before=window.geometry();settle(app,2.3)
        assert window.geometry()==before,'Placement oscillated'
        window.close();settle(app)
        assert '+5000' not in app.config_data.get('preview','geometry')
        app.preview_paths([document],document);window=app.preview_window
        until(app,lambda:visible(window))
        window.close();settle(app)
        # The evidence viewer must also be reachable and show the geometry
        # card without requiring a file export or seeing the lost window.
        app.show_debug_log();settle(app)
        log=next(w for w in app.winfo_children() if isinstance(w,tk.Toplevel)
                 and w.title()==pfc.tr('Error / Warning log'))
        until(app,lambda:visible(log))
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        table=next(w for w in descendants(log) if isinstance(w,ttk.Treeview))
        rows=list(reversed(pfc.diagnostic_incidents(app.debug_log.snapshot(automatic=True),app.debug_log.snapshot())))
        index=next(i for i,r in enumerate(rows) if r['event']=='window.placement.recovery'
                   and r.get('window',{}).get('role')=='F3 Preview')
        table.selection_set(str(index));table.event_generate('<<TreeviewSelect>>');settle(app)
        text=next(w for w in descendants(log) if isinstance(w,tk.Text))
        assert 'F3 Preview' in text.get('1.0','end-1c')
        capture(log,'diagnostics')
        assert not errors,errors
        print('PASS: F3 saved/live/reused offscreen recovery, document retained, laptop fitting at 200%, no oscillation, automatic photo diagnostics and close/reopen',flush=True)
    finally:app.close_app()
