"""Exercise complete multiline values, real header drags and stable widths."""
import configparser
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
import tkinter.font as tkfont

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
app=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')

def ready(root,page,timeout=35):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        root.update();time.sleep(.005)
        view=page.render_view
        if not (page._format_jobs.pending or page._format_request or page._format_queued or view._insert_job or getattr(view.tree,'_layout_job',None)):
            root.update();return
    raise AssertionError('Preview/reflow did not settle')

def capture(window,name):
    window.lift();window.update();time.sleep(.1);window.update()
    if os.name=='nt':
        from folder_native_test_support import capture_window
        capture_window(window,Path(__file__).parent/('evidence-wrap-'+name+'.bmp'))
    else:
        from PIL import ImageGrab
        x,y=window.winfo_rootx(),window.winfo_rooty()
        ImageGrab.grab((x,y,x+window.winfo_width(),y+window.winfo_height())).save('/tmp/pfc-wrap-'+name+'.png')

with tempfile.TemporaryDirectory() as raw:
    directory=Path(raw);path=directory/'devices.json'
    value='Product name: AW2725Q, Product ID: DEL A27F. '+('完整顯示 long device details / '+('x'*28)+'; ')*8+'TAIL-END'
    source=json.dumps({'devices':[{'ConnectedDeviceName':value},{'ConnectedDeviceName':value+' second'}],'multiline':'first line\nsecond line\n第三行','short':'one line'})
    path.write_text(source,encoding='utf-8')
    root=tk.Tk();root.geometry('1160x800');errors=[];pulses=[];running=True
    root.report_callback_exception=lambda *exc:errors.append(str(exc))
    def pulse():
        if running:pulses.append(time.monotonic());root.after(20,pulse)
    pulse()
    config=configparser.ConfigParser();config.add_section('preview');config.set('preview','geometry','1100x740')
    window=app.PreviewWindow(root,config,lambda:None,[path],path)
    try:
        page=window.active_page;ready(root,page);view=page.render_view;tree=view.tree
        page.search_var.set('AW2725Q');page.find_all_matched();ready(root,page)
        rows=[r for r in view._row_lookup.values() if r['label']=='ConnectedDeviceName']
        assert len(rows)==2
        def height(iid):return tree.bbox(iid)[3]
        row=rows[0];iid=row['id'];font=tkfont.nametofont('TkDefaultFont')
        assert tree.item(iid,'values')[0]==value,'Raw display value was excerpted'
        assert ''.join(tree._layouts[iid][1][1])==value,'Wrapped text lost data'
        assert height(iid)>font.metrics('linespace')*2
        assert all(tree.item(tree.parent(r['id']),'open') for r in rows)
        multi=next(r for r in view.model['rows'] if r['label']=='multiline')
        assert tree._layouts[multi['id']][1][1]==['first line','second line','第三行']
        # Exercise native heading drag, not just a programmatic width assignment.
        old=tree.column('#0','width');tree.event_generate('<ButtonPress-1>',x=old-1,y=10)
        tree.event_generate('<B1-Motion>',x=old+100,y=10,state=256)
        tree.event_generate('<ButtonRelease-1>',x=old+100,y=10);ready(root,page)
        dragged=tree.column('#0','width');assert dragged>old+40,(old,dragged)
        old_height=height(iid)
        for _ in range(3):view.rescale();root.update()
        ready(root,page);assert tree.column('#0','width')==dragged,'Rescale reset user width'
        window.geometry('1000x740');ready(root,page)
        assert tree.column('#0','width')==dragged,'Window resize reset key width'
        tree.column('#0',width=130);ready(root,page)
        assert tree.column('#0','width')==130,'Minimum width forces a rebound'
        assert ''.join(tree._layouts[iid][1][1])==value
        tree.column('#0',width=300);ready(root,page)
        tree.see(iid);ready(root,page);capture(window,'multiline')
        # Copy remains lossless, selection and keyboard navigation share one tree.
        tree.selection_set(iid);tree.focus(iid);view.copy();assert root.clipboard_get()==value
        tree.focus_set();tree.event_generate('<Down>');root.update();assert tree.selection()[0]!=iid
        tree.selection_set(iid);tree.focus(iid);tree.see(iid);ready(root,page)
        # A scalar larger than a source text window still renders completely.
        big=directory/'large.json';large='0123456789 '*5000+'END-OF-LONG-VALUE'
        big.write_text(json.dumps({'long':large}),encoding='utf-8')
        window.show([path,big],big);page=window.active_page;ready(root,page)
        tree=page.render_view.tree;iid=next(r['id'] for r in page.render_view.model['rows'] if r['label']=='long')
        assert ''.join(tree._layouts[iid][1][1])==large
        tree.focus_set();tree.event_generate('<Next>');root.update()
        assert 0<tree.yview()[0]<.5,'Page Down skipped a long variable-height cell'
        tree.event_generate('<Prior>');root.update();assert tree.yview()[0]==0
        page.search_var.set('END-OF-LONG-VALUE');page.find_next();ready(root,page)
        assert tree.yview()[0]>.5,'Long-cell search did not reveal the matching lines'
        tree.yview_moveto(1);root.update();assert tree.yview()[1]==1
        capture(window,'long-tail')
        # Font changes preserve the chosen key width and reflow variable rows.
        fonts={name:tkfont.nametofont(name).cget('size') for name in ('TkDefaultFont','TkFixedFont','TkTextFont','TkHeadingFont')}
        for name,size in fonts.items():tkfont.nametofont(name).configure(size=round(size*2))
        tree.column('#0',width=210);window.apply_scale(2);ready(root,page)
        assert tree.column('#0','width')==210
        assert tree.yview()[0]>.5,'Font reflow lost the matching line'
        capture(window,'200')
        for name,size in fonts.items():tkfont.nametofont(name).configure(size=size)
        assert max((b-a for a,b in zip(pulses,pulses[1:])),default=0)<1,'Reflow blocked event loop'
        assert not errors,errors
        assert path.read_text(encoding='utf-8')==source
        page.load();ready(root,page);assert page.render_view.tree.column('#0','width')==210,'Reload reset column width'
        page.load();root.update();window.close();root.update()
        assert not errors,errors
        print('PASS: complete width-wrapped variable-height values; native header drag; stable resize/scale widths; keyboard/copy; long scalar/tail search; responsive reflow; close cleanup',flush=True)
    finally:
        running=False
        if window.winfo_exists():window.close()
        root.destroy()
