"""Find All -> Expand All -> Cancel: stable viewport and a genuinely idle UI."""
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

def pump(root,seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:root.update();time.sleep(.005)

def ready(root,page,timeout=20):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        root.update();time.sleep(.005);v=page.render_view
        if not (page._format_jobs.pending or page._format_queued or page._format_request or v._insert_job or getattr(v.tree,'_layout_job',None)):
            pump(root,.15)
            if not getattr(v.tree,'_layout_job',None) and not page._activity_busy:return
    raise AssertionError('Preview never became idle: '+page.status.cget('text'))

def capture(window,name):
    window.lift();window.update()
    if os.name=='nt':
        from folder_native_test_support import capture_window
        capture_window(window,Path(__file__).parent/('evidence-expand-'+name+'.bmp'))
    else:
        from PIL import ImageGrab
        x,y=window.winfo_rootx(),window.winfo_rooty()
        ImageGrab.grab((x,y,x+window.winfo_width(),y+window.winfo_height())).save('/tmp/pfc-expand-'+name+'.png')

with tempfile.TemporaryDirectory() as raw:
    path=Path(raw)/'nested.json'
    data={'PL':[{'Content':[{'SerializedBlob':{'items':[{'kind':'other','value':'readable context '*8} for j in range(12)],'name':'AW27-'+str(i) if i>=73 else 'Other','type':'device'}}]} for i in range(82)]}
    original=json.dumps(data);path.write_text(original,encoding='utf-8')
    root=tk.Tk();root.geometry('1160x800');errors=[];root.report_callback_exception=lambda *e:errors.append(str(e))
    config=configparser.ConfigParser();config.add_section('preview');config.set('preview','geometry','1100x740')
    window=app.PreviewWindow(root,config,lambda:None,[path],path)
    fonts={n:tkfont.nametofont(n).cget('size') for n in ('TkDefaultFont','TkFixedFont','TkTextFont','TkHeadingFont')}
    try:
        page=window.active_page;ready(root,page)
        for scale in (1,1.75,2):
            for n,size in fonts.items():tkfont.nametofont(n).configure(size=round(size*scale))
            window.apply_scale(scale);ready(root,page)
            page.search_var.set('AW27');page.find_all_matched();ready(root,page)
            view=page.render_view;tree=view.tree;selected=tree.selection()[0]
            count=len(view._row_lookup);view.expand_button.invoke();ready(root,page)
            assert len(view._row_lookup)==count,'Expand All fetched additional data without a bounded request'
            assert tree.exists(selected) and tree.item(tree.parent(selected),'open')
            before=(tree._revision,tree._offset,tree.winfo_height(),view.winfo_rooty())
            pump(root,.7)
            assert before==(tree._revision,tree._offset,tree.winfo_height(),view.winfo_rooty()),'Idle tree kept reflowing/jumping'
            assert not page.format_cancel.winfo_ismapped() and not page.activity_progress.winfo_ismapped()
            capture(window,'expanded-'+str(round(scale*100)))
            view.collapse_button.invoke();ready(root,page)
            saved_open={iid:bool(tree.item(iid,'open')) for iid in view._row_lookup}
            saved_rows=tuple(r[0] for r in tree._entries)
            view.expand_button.invoke()
            deadline=time.monotonic()+10;canceled=[]
            def cancel_when_busy():
                if view._insert_job or tree._layout_job:
                    page.format_cancel.invoke();canceled.append(time.monotonic())
                elif time.monotonic()<deadline:root.after(1,cancel_when_busy)
            root.after(1,cancel_when_busy)
            while not canceled:
                root.update();time.sleep(.002);assert time.monotonic()<deadline,'No cancellable expansion was observed'
            pump(root,.7)
            assert not tree._layout_job and not view._insert_job and not page._activity_busy,'Cancel restarted the operation'
            assert saved_open=={iid:bool(tree.item(iid,'open')) for iid in view._row_lookup},'Cancel did not roll back partially opened nodes'
            assert tuple(r[0] for r in tree._entries)==saved_rows,'Cancel replaced the committed view'
            assert not page.format_cancel.winfo_ismapped() and not page.activity_progress.winfo_ismapped()
            before=(tree._revision,tree._offset,tree.winfo_height());pump(root,.7)
            assert before==(tree._revision,tree._offset,tree.winfo_height()),'Canceled view was not stable'
            capture(window,str(round(scale*100)))
            # Cancel after native flags are changed but before layout commits.
            view.expand_button.invoke();canceled=[];deadline=time.monotonic()+10
            def cancel_during_layout():
                if not view._tree_revealing and tree._layout_job and view._expand_restore is not None:
                    page.format_cancel.invoke();canceled.append(True)
                elif time.monotonic()<deadline:root.after(1,cancel_during_layout)
            root.after(1,cancel_during_layout)
            while not canceled:
                root.update();time.sleep(.002);assert time.monotonic()<deadline,'Layout cancellation was not exercised'
            pump(root,.4)
            assert saved_open=={iid:bool(tree.item(iid,'open')) for iid in view._row_lookup}
            assert tuple(r[0] for r in tree._entries)==saved_rows
            assert not tree._layout_job and not page._activity_busy
            # Explicit actions can resume after cancellation.
            view.collapse_button.invoke();ready(root,page)
            page.find_all_matched();ready(root,page);assert '9 matches' in page.status.cget('text')
        assert not errors,errors
        assert path.read_text(encoding='utf-8')==original
        print('PASS: Find All/Expand All at 100/175/200%; bounded loaded nodes; stable idle geometry/offset; Cancel stays canceled; explicit retry; unchanged source',flush=True)
    finally:
        for n,size in fonts.items():tkfont.nametofont(n).configure(size=size)
        if window.winfo_exists():window.close()
        root.destroy()
