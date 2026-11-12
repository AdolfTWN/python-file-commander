"""Real Tk response, stale folder cancellation, audit cadence and large Preview styles."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')


def pump(app, predicate=lambda:False, timeout=.2):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        app.update()
        if predicate():return True
        time.sleep(.005)
    return bool(predicate())


def capture(window):
    if os.name=='nt':
        from folder_native_test_support import capture_window
        capture_window(window,Path(__file__).parent/'evidence-responsive-preview.bmp')
    elif os.environ.get('PFC_RESPONSIVE_SCREENSHOT'):
        from PIL import ImageGrab
        x,y=window.winfo_rootx(),window.winfo_rooty()
        ImageGrab.grab((x,y,x+window.winfo_width(),y+window.winfo_height())).save(
            os.environ['PFC_RESPONSIVE_SCREENSHOT'])


with tempfile.TemporaryDirectory() as raw:
    base=Path(raw);slow=base/'slow';fast=base/'fast'
    slow.mkdir();fast.mkdir()
    (slow/'lag.txt').write_text('slow',encoding='utf-8')
    (fast/'ready.txt').write_text('ready',encoding='utf-8')
    pfc.Commander._find_ini_path=staticmethod(lambda:base/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda self,**kwargs:True
    app=pfc.Commander();errors=[]
    data=sys.modules[pfc.DirectoryReads.__module__]
    app.report_callback_exception=lambda *args:errors.append(str(args))
    reader=app._directory_reader
    try:
        app.config_data.set('refresh','auto_refresh','false')
        if app._auto_refresh_job is not None:
            app.after_cancel(app._auto_refresh_job);app._auto_refresh_job=None
        app.vcs_overlay_var.set(False);app.onedrive_overlay_var.set(False)
        app.auto_font_size_var.set(False)
        pane=app.active
        main_thread=threading.get_ident();threads=set();ticks=[];running=[True]
        responsive_while_reading=[]
        def tick():
            ticks.append(time.monotonic())
            if (pane._directory_request is not None and entered.is_set()
                    and not pane._directory_request.done.is_set()):
                responsive_while_reading.append(True)
            if running[0]:app.after(10,tick)
        stat=data._listing_stat;entered=threading.Event()
        tick()
        def delayed(path,*args,**kwargs):
            if path==slow/'lag.txt':
                threads.add(threading.get_ident());entered.set();time.sleep(.5)
            return stat(path,*args,**kwargs)
        with patch.object(data,'_listing_stat',delayed):
            started=time.monotonic()
            assert pane.navigate(slow)
            assert time.monotonic()-started>=.5
            assert responsive_while_reading and threads and main_thread not in threads, (
                len(ticks), len(responsive_while_reading), threads, main_thread)
            assert pane.navigate(fast)
            # A newer navigation occurs while an older synchronous caller waits.
            newest=[]
            app.after(80,lambda:newest.append(pane.navigate(fast)))
            assert pane.navigate(slow) is False
            assert newest==[True] and pane.path==fast
            assert pane.selected_paths()==[fast/'ready.txt']
            pump(app,timeout=.6)
            assert pane.path==fast

            assert pane.navigate(slow)
            app._directory_audits.clear();app._network_refresh_due.clear()
            entered.clear()
            start=time.monotonic();app._audit_visible_panes([pane])
            assert time.monotonic()-start<.1
            job=next(iter(app._directory_audits.values()))
            assert pump(app,lambda:entered.is_set(),timeout=1)
            for _ in range(20):app._audit_visible_panes([pane])
            assert next(iter(app._directory_audits.values())) is job
            assert pump(app,lambda:job.done.is_set(),timeout=2)
            app._audit_visible_panes([pane])
            assert not app._directory_audits
            assert min(app._network_refresh_due.values())>time.monotonic()+.8
            app._audit_visible_panes([pane])
            assert not app._directory_audits
        print('PASS: slow metadata never runs on Tk, input heartbeat continues, latest navigation wins, no immediate audit repeat',flush=True)

        # A document matching the reported styling bottleneck, plus astral
        # characters before matches to protect Unicode index semantics.
        window=tk.Toplevel(app);window.title('PFC Preview — responsiveness fixture')
        window.geometry('1100x700+10+10')
        view=pfc.FormatRenderView(window) if hasattr(pfc,'FormatRenderView') else None
        if view is None:
            from pycommander.renderui import FormatRenderView
            view=FormatRenderView(window)
        view.pack(fill='both',expand=True)
        content=('😀 sample alpha beta gamma delta '+('word '*18)+'\n')*2500
        spans=[]
        pos=0
        while True:
            pos=content.find('alpha',pos)
            if pos<0:break
            spans.append((pos,pos+5,'render_heading'))
            spans.extend((pos+i,pos+i+1,'render_hunk') for i in (6,8,10,12))
            pos+=5
        before=len(ticks);started=time.monotonic()
        view.show(dict(kind='document',content=content,spans=spans))
        assert pump(app,lambda:view._insert_job is None,timeout=10)
        elapsed=time.monotonic()-started
        assert view.text.get('1.0','end-1c')==content
        assert len(ticks)>before+1
        ranges=view.text.tag_ranges('render_heading')
        assert len(ranges)==5000
        for index in (0,2,100,4998):
            assert view.text.get(ranges[index],ranges[index+1])=='alpha'
        view.show(dict(kind='document',content=content,spans=spans))
        assert view._insert_job is not None
        view.cancel_document_work();partial=view.text.get('1.0','end-1c')
        pump(app)
        assert view._insert_job is None and view.text.get('1.0','end-1c')==partial
        assert view.find('alpha',False)==pfc.tr('Preview canceled; press F5 to retry')
        view.show(dict(kind='document',content='Latest document\nneedle',spans=[]))
        assert pump(app,lambda:view._insert_job is None,timeout=2)
        assert 'Match' in view.find('needle',False)
        assert view.text.get('1.0','end-1c')=='Latest document\nneedle'
        view.show(dict(kind='document',content=content,spans=spans))
        assert pump(app,lambda:view._insert_job is None,timeout=10)
        capture(window)
        window.destroy()
        print(f'PASS: {len(content)} characters / {len(spans)} styles in {elapsed:.3f}s; heartbeat, Unicode, cancel, replacement and Find verified',flush=True)
        assert not errors,errors
        # Root closure must wake the navigation waiter and drop all UI callbacks.
        with patch.object(data,'_listing_stat',delayed):
            app.after(80,app.destroy)
            assert pane.navigate(slow) is False
        running[0]=False
    finally:
        running[0]=False
        try:
            if app.winfo_exists():app.destroy()
        except tk.TclError:pass
        reader.close()
        for worker in reader._threads:worker.join(2)
        assert not any(w.is_alive() for w in reader._threads)
