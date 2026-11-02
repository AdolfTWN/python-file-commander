"""F4 lost-display recovery with real windows and synthetic search results."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')


def until(app,predicate,timeout=6):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        app.update();time.sleep(.02)
        if predicate():return
    raise AssertionError('Search window did not reach expected state')


def settle(app,seconds=.2):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.update();time.sleep(.02)


def frame(window):
    guard=getattr(window,'_window_visibility',None)
    if os.name=='nt' and guard is not None:return guard.backend.snapshot()
    x,y=window.winfo_rootx(),window.winfo_rooty()
    return ((x,y,x+window.winfo_width(),y+window.winfo_height()),
            ((0,0,window.winfo_screenwidth(),window.winfo_screenheight()),),0)


def visible(window):
    snapshot=frame(window)
    if not snapshot:return False
    (l,t,r,b),areas,margin=snapshot
    return any(l>=x1-margin and t>=y1-margin and r<=x2+margin and b<=y2+margin
               for x1,y1,x2,y2 in areas)


def move_offscreen(window,x=5000):
    if os.name=='nt':window._window_visibility.backend.move((x,120,1100,650))
    else:window.geometry(f'1100x650+{x}+120')


def capture(window,name):
    window.lift();settle(window,.2)
    path=Path(__file__).parent/('evidence-search-visibility-'+name+'.bmp')
    if os.name=='nt':
        from folder_native_test_support import capture_window
        capture_window(window,path)
    else:
        from PIL import ImageGrab
        x,y=window.winfo_rootx(),window.winfo_rooty()
        ImageGrab.grab((x,y,x+window.winfo_width(),y+window.winfo_height())).save('/tmp/pfc-search-visibility-'+name+'.png')


with tempfile.TemporaryDirectory(prefix='pfc-search-visible-') as raw:
    directory=Path(raw).resolve();ini=directory/'pfc.ini'
    ini.write_text('[window]\ngeometry=1000x650+20+20\n[search]\ngeometry=1800x1050+5000+120\n',encoding='utf-8')
    for n in range(25):(directory/f'note-{n:02}.txt').write_text('Synthetic searchable content',encoding='utf-8')
    pfc.Commander._find_ini_path=staticmethod(lambda:ini)
    pfc.Commander._sync_auto_start=lambda *a,**k:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False);app.active.navigate(directory)
        app.search();s=app.search_window
        until(app,lambda:visible(s))
        assert s.winfo_ismapped() and s.mask_entry.winfo_ismapped()
        capture(s,'startup')
        s.mask_var.set('*.txt');s.start();until(app,lambda:s.worker is None)
        assert len(s.results)==25
        row=s.tree.get_children()[0];s.tree.selection_set(row)
        results=list(s.results)
        move_offscreen(s);settle(app,.15)
        assert s.winfo_rootx()>s.winfo_screenwidth(),'Fixture was not offscreen'
        until(app,lambda:visible(s))
        assert s.results==results and row in s.tree.selection(),'Recovery reset search results/selection'
        capture(s,'results')
        if os.name=='nt':
            s.state('zoomed');settle(app);s._window_visibility.recover();settle(app)
            assert s.state()=='zoomed','Valid maximized search was restored unnecessarily'
            s.state('normal');settle(app)
            s.iconify();settle(app,2.5)
            assert s.state()=='iconic','Recovery reopened minimized Search'
            s.deiconify();settle(app)
        # Reusing an existing Search window must also rescue it immediately.
        move_offscreen(s);app.search();until(app,lambda:visible(s))
        for key,value in app._font_scales.items():
            if value==2.0:
                app.font_size_var.set(key);app.apply_font_size(save=False);break
        s.geometry('2200x1400+50+50');s.activate();until(app,lambda:visible(s))
        assert s.find_button.winfo_ismapped() and s.mask_entry.winfo_ismapped()
        assert s.tree.winfo_height()>=60,'Fitted search has no usable results area'
        capture(s,'zoom200')
        before=(s.winfo_rootx(),s.winfo_rooty(),s.winfo_width(),s.winfo_height())
        settle(app,2.5)
        assert before==(s.winfo_rootx(),s.winfo_rooty(),s.winfo_width(),s.winfo_height()),'Recovered placement oscillated'
        s.close();settle(app)
        assert not s.winfo_exists()
        assert '+5000' not in app.config_data.get('search','geometry')
        app.search();reopened=app.search_window
        until(app,lambda:visible(reopened));assert reopened is not s
        assert not errors,errors
        print('PASS: F4 saved offscreen/oversized, live recovery retains results, reuse, 200% fitting, minimize/maximize and close/reopen',flush=True)
    finally:app.close_app()
