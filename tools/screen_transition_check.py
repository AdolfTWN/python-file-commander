"""Populated interactive tasks across real client sizes; separate from native modes."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')


def pump(app,seconds=.12):
    until=time.monotonic()+seconds
    while time.monotonic()<until:app.update();time.sleep(.004)


def within(widget,owner):
    return (widget.winfo_ismapped() and widget.winfo_width()>5 and widget.winfo_height()>5 and
            widget.winfo_rootx()>=owner.winfo_rootx() and widget.winfo_rooty()>=owner.winfo_rooty() and
            widget.winfo_rootx()+widget.winfo_width()<=owner.winfo_rootx()+owner.winfo_width()+1 and
            widget.winfo_rooty()+widget.winfo_height()<=owner.winfo_rooty()+owner.winfo_height()+1)


def capture(app,name):
    if os.name=='nt':
        from folder_native_test_support import capture_window
        capture_window(app,Path(__file__).parent/('evidence-screen-'+name+'.bmp'))
    else:
        from PIL import ImageGrab
        x,y=app.winfo_rootx(),app.winfo_rooty()
        ImageGrab.grab((x,y,x+app.winfo_width(),y+app.winfo_height())).save('/tmp/pfc-screen-'+name+'.png')


with tempfile.TemporaryDirectory(prefix='pfc-screen-flow-') as raw:
    folder=Path(raw);ini=folder/'pfc.ini'
    ini.write_text('[window]\ngeometry=3800x2100+5000+0\n[view]\nauto_font_size=false\n',encoding='utf-8')
    for n in range(80):(folder/f'{n:03} Engineering 文件.txt').write_text('Task fixture')
    pfc.Commander._find_ini_path=staticmethod(lambda:ini)
    pfc.Commander._sync_auto_start=lambda *a,**k:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();errors=[];cases=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        pump(app,.6);app.auto_font_size_var.set(False)
        for pane in app.visible_panes():pane.navigate(folder)
        for width,height in ((1260,650),(1000,680),(800,600),(1260,650)):
            app.geometry(f'{width}x{height}+0+0');pump(app)
            for level in ('small','large','xl','300'):
                app.font_size_var.set(level);app.select_manual_font_size();pump(app)
                assert within(app.zoom_combo,app),('Zoom inaccessible',width,height,level)
                for button,key,_ in app.action_buttons:
                    assert within(button,app.actions_frame),('Shortcut clipped',width,height,level,key)
                for pane in app.visible_panes():
                    assert within(pane.quick_filter_entry,pane),('Filter clipped',width,height,level)
                if (width,level) in ((800,'300'),(1260,'xl')):capture(app,f'{width}-{level}')
                cases.append((app.winfo_width(),app.winfo_height(),level))
                # At physically insufficient extreme combinations, access to
                # recovery is not equivalent to usable file content. Exercise
                # the actual minus control until a complete row is visible.
                def has_row(pane):
                    children=pane.tree.get_children()
                    box=pane.tree.bbox(children[0]) if children else ()
                    return bool(box and box[1]+box[3]<=pane.tree.winfo_height())
                if not all(has_row(p) for p in app.visible_panes()):
                    for _ in range(len(app._font_scales)):
                        app.zoom_minus.invoke();pump(app)
                        if all(has_row(p) for p in app.visible_panes()):break
                    assert all(has_row(p) for p in app.visible_panes()),'Cannot recover file content using visible zoom control'
                    print(json.dumps({'event':'screen.degraded.recovered','size':[width,height],
                                      'requested':level,'recovered':app.font_size_var.get()}),flush=True)
        app.font_size_var.set('large');app.select_manual_font_size();pump(app)
        for count in (1,2,3,4,2):
            app.panel_count_var.set(count);app.apply_panel_count(save=False);pump(app)
            assert len(app.visible_panes())==count
            assert within(app.zoom_combo,app),('Zoom lost after layout',count)
        app.search();pump(app);s=app.search_window
        s.geometry('1000x650+5000+0');s.activate();pump(app,.5)
        assert within(s.mask_entry,s)
        s.close()
        app.show_settings();pump(app);d=app.settings_window
        assert d.footer.winfo_ismapped()
        d.cancel();pump(app)
        assert not errors,errors
        print(json.dumps({'event':'screen.transitions.passed','desktop':[app.winfo_screenwidth(),app.winfo_screenheight()],
                          'cases':cases,'platform':os.name}),flush=True)
    finally:app.close_app()
