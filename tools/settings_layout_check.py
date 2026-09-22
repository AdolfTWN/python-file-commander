"""Whole-workspace Before/After: topology, draft isolation and readable geometry."""
import importlib
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')


def settle(app):
    end=time.monotonic()+.08
    while time.monotonic()<end:
        app.update();time.sleep(.01)


def topology(sample, count):
    c=sample.canvas
    assert len(c.find_withtag('file-panel'))==count
    assert len(c.find_withtag('tab-group'))==count
    assert len(c.find_withtag('folder-tree'))==int(count==1)
    assert bool(c.find_withtag('tree-branch'))==(count==1)
    assert str(count) in sample.title.cget('text')
    width=c.winfo_width();height=c.winfo_height()
    for item in c.find_all():
        x1,y1,x2,y2=c.bbox(item)
        assert -2<=x1<=x2<=width+2,(count,'width',c.type(item),c.itemcget(item,'text') if c.type(item)=='text' else '',(x1,x2),width)
        assert -2<=y1<=y2<=height+2,(count,'height',(y1,y2),height)
    if count==1:
        tree=c.coords(c.find_withtag('folder-tree')[0])
        files=c.coords(c.find_withtag('file-panel')[0])
        assert .28<(tree[2]-tree[0])/(width-10)<.35
        assert files[0]>tree[2]
        tabs=c.coords(c.find_withtag('tab-group')[0])
        assert tabs[0]<=tree[0] and tabs[2]>=files[2]


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


with tempfile.TemporaryDirectory(prefix='pfc-layout-preview-') as raw:
    root=Path(raw)
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**kw:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False)
        app.font_size_var.set('300');app.apply_font_size(save=False)
        app.panel_count_var.set(1);app.apply_panel_count(save=False)
        for language in ('en','zh_TW','zh_CN','ko'):
            app.ui_language_var.set(language);app._apply_ui_language_now()
            for theme in ('light','light_grey','dark'):
                app.color_scheme_var.set(theme);app.apply_color_scheme(save=False)
                app.save_config();saved=(root/'pfc.ini').read_bytes()
                app.show_settings('layout');d=app.settings_window
                for geometry in ('1180x720+0+0','780x560+0+0'):
                    d.geometry(geometry);settle(app)
                    for count in (1,2,3,4):
                        d.vars['panel_count'].set(count);settle(app)
                        before,after=[w for w,_ in d.layout_examples]
                        topology(before,1);topology(after,count)
                        assert not d.preview_labels,'Layout must not reuse an unrelated single-pane screenshot'
                        assert app.panel_count_var.get()==1,'Preview cannot apply a layout'
                        assert before.winfo_rooty()+before.winfo_height()<=d.canvas.winfo_rooty()
                        assert d.canvas.winfo_height()>=65,(language,geometry,d.canvas.winfo_height())
                        assert d.footer.winfo_rooty()+d.footer.winfo_height()<=d.winfo_rooty()+d.winfo_height()+1
                        ids=after.canvas.find_all()
                        for _ in range(5):d._changed()
                        assert ids==after.canvas.find_all(),'Unchanged state must not repaint'
                        if '--screenshots' in sys.argv and language=='en' and theme=='light':
                            from PIL import ImageGrab
                            x,y=d.winfo_rootx(),d.winfo_rooty()
                            ImageGrab.grab((x,y,x+d.winfo_width(),y+d.winfo_height())).save(
                                f'/tmp/pfc-layout-1-to-{count}'+('-compact' if '780' in geometry else '')+'.png')
                    before_ids=before.canvas.find_all()
                    shapes=[]
                    for style in ('right_skirt','rounded','squarish'):
                        d.vars['tab_style'].set(style);settle(app)
                        shapes.append(after.canvas.coords(after.canvas.find_withtag('tab-shape')[0]))
                    assert len({tuple(points) for points in shapes})==3
                    assert before_ids==before.canvas.find_all(),'Draft style must not alter Before'
                    top=d.comparison.winfo_rooty();d.canvas.yview_moveto(1);settle(app)
                    assert d.comparison.winfo_rooty()==top
                if theme=='light':
                    d._enlarge(None);settle(app);popup=app.grab_current()
                    samples=[w for w in descendants(popup) if type(w).__name__=='SettingsLayoutPreview']
                    assert len(samples)==2
                    topology(samples[0],1);topology(samples[1],4)
                    popup.event_generate('<Escape>');settle(app)
                    assert app.grab_current() is d
                d.cancel()
                assert (root/'pfc.ini').read_bytes()==saved
            print('PASS: 1→1/2/3/4 topology, shared/independent tabs, styles, compact fixed previews, no draft effects: '+language,flush=True)
        app.show_settings('layout');d=app.settings_window
        d.vars['panel_count'].set(3);d.apply();settle(app)
        assert app.panel_count_var.get()==3
        before,after=[w for w,_ in d.layout_examples]
        topology(before,3);topology(after,3)
        d.vars['panel_count'].set(1);settle(app)
        topology(before,3);topology(after,1)
        d.cancel();assert app.panel_count_var.get()==3
        assert not errors,errors
        print('PASS: Apply advances Before baseline; 3→1 draft and Cancel preserve applied layout',flush=True)
    finally:
        dialog=getattr(app,'settings_window',None)
        if dialog is not None and dialog.winfo_exists():dialog.cancel()
        app.close_app()
