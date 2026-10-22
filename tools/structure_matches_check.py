"""Retained JSON matches and cancellable bulk path expansion, source/portable."""
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
from tkinter import ttk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
app=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')


def ready(root,page,timeout=35):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        root.update();time.sleep(.005)
        if not (page._format_jobs.pending or page._format_queued or page._format_request or page.render_view._insert_job or getattr(page.render_view.tree,'_layout_job',None)):
            root.update();return
    raise AssertionError('Search did not settle: '+page.status.cget('text'))


def capture(window,name):
    window.lift();window.update();time.sleep(.15);window.update()
    if os.name=='nt':
        from folder_native_test_support import capture_window
        capture_window(window,Path(__file__).parent/('evidence-matches-'+name+'.bmp'))
    else:
        from PIL import ImageGrab
        x,y=window.winfo_rootx(),window.winfo_rooty()
        ImageGrab.grab((x,y,x+window.winfo_width(),y+window.winfo_height())).save('/tmp/pfc-matches-'+name+'.png')


with tempfile.TemporaryDirectory() as raw:
    folder=Path(raw);path=folder/'devices.json'
    def data(count):
        return {'unrelated':list(range(4000)),'PL':[{'Content':[{'SerializedBlob':{'PortInfoItems':[{'ConnectedDeviceName':'AW27-'+str(i)}]}}]} for i in range(count)]}
    original=json.dumps(data(9));path.write_text(original,encoding='utf-8')
    root=tk.Tk();root.geometry('1180x800');errors=[]
    pulses=[];measuring=False;running=True
    def pulse():
        if running:pulses.append((time.monotonic(),measuring));root.after(20,pulse)
    pulse()
    root.report_callback_exception=lambda *exc:errors.append(str(exc))
    config=configparser.ConfigParser();config.add_section('preview');config.set('preview','geometry','1160x760')
    window=app.PreviewWindow(root,config,lambda:None,[path],path)
    page=window.active_page;ready(root,page);view=page.render_view;tree=view.tree
    unrelated=next(r['id'] for r in view.model['rows'] if r['label']=='unrelated')
    tree.item(unrelated,open=False)
    def search(needle,bulk=False,direction=1):
        page.search_var.set(needle)
        if bulk:page.find_all_matched_button.invoke()
        else:page._find(direction)
        ready(root,page)
        assert page.render_view.tree is tree and page.markdown_values[page.markdown_var.get()]=='rendered'
        assert not tree.item(unrelated,'open'),'Unrelated branch was expanded'
    try:
        assert page.find_all_matched_button.winfo_ismapped()
        retained=[]
        for index in range(9):
            search('AW27');iid=tree.selection()[0];retained.append(iid)
            assert f'Match {index+1} of 9' in page.status.cget('text')
            for previous in retained:
                assert tree.exists(previous),'Previously found row disappeared'
                assert 'AW27' in tree.item(previous,'values')[0]
                parent=tree.parent(previous)
                while parent:assert tree.item(parent,'open');parent=tree.parent(parent)
        search('AW27',direction=-1);assert tree.selection()[0]==retained[-2]
        capture(window,'retained')
        page.load();ready(root,page);tree=view.tree
        unrelated=next(r['id'] for r in view.model['rows'] if r['label']=='unrelated');tree.item(unrelated,open=False)
        search('AW27',bulk=True)
        assert '9 matching rows' in page.status.cget('text')
        assert len(view._tree_search_rows)==9
        assert len(view._search_extra)<100
        all_rows=set(view._tree_search_rows)
        search('AW27');assert set(view._tree_search_rows)==all_rows
        page.search.focus_set();page.search.event_generate('<Control-Return>');ready(root,page)
        assert '9 matching rows' in page.status.cget('text')
        capture(window,'all')
        search('AW27-1');assert len(view._tree_search_rows)==1 and len(view._search_extra)<15
        page.case_var.set(True);search('aw27',bulk=True);assert 'No matches' in page.status.cget('text')
        assert not view._search_extra
        page.case_var.set(False)
        page.search_var.set('AW27');page.find_all_matched();root.update()
        page.search_var.set('missing');page.find_next();ready(root,page)
        assert 'No matches' in page.status.cget('text') and not view._search_extra
        # Expanded paths remain per-tab; unrelated Source views have no bulk button.
        other=folder/'note.md';other.write_text('# Other\ntext',encoding='utf-8')
        search('AW27',bulk=True);old_rows=set(view._tree_search_rows)
        window.show([path,other],other);root.update();assert not window.active_page.find_all_matched_button.winfo_manager()
        window.show([path,other],path);ready(root,page);assert set(view._tree_search_rows)==old_rows
        # Full-size and compact labels remain on the same search row at 200%.
        fonts={n:tkfont.nametofont(n).cget('size') for n in ('TkDefaultFont','TkFixedFont','TkTextFont','TkHeadingFont')}
        for n,size in fonts.items():tkfont.nametofont(n).configure(size=round(size*2))
        ttk.Style(root).configure('Treeview',rowheight=44,font='TkDefaultFont')
        window.geometry('800x660');window.apply_scale(2);root.update();ready(root,page)
        tree=view.tree
        unrelated=next(r['id'] for r in view.model['rows'] if r['label']=='unrelated');tree.item(unrelated,open=False)
        search('AW27',bulk=True)
        assert page.find_all_matched_button.winfo_rooty()==page.find_next_button.winfo_rooty()
        assert page.search.winfo_width()>25
        assert page.case_check.winfo_rootx()+page.case_check.winfo_width()<=window.winfo_rootx()+window.winfo_width()
        capture(window,'200')
        for n,size in fonts.items():tkfont.nametofont(n).configure(size=size)
        ttk.Style(root).configure('Treeview',rowheight=24)
        window.geometry('1160x760');window.apply_scale(1);root.update()
        # Bulk rendering yields to the event loop and can be canceled mid-insert.
        large=folder/'many.json';large.write_text(json.dumps(data(1600)),encoding='utf-8')
        window.show([large],large);page=window.active_page;ready(root,page);view=page.render_view
        page.search_var.set('AW27');page.find_all_matched()
        canceled=[];deadline=time.monotonic()+15
        def cancel_when_inserting():
            if view._tree_revealing:
                page._cancel_format_ui();canceled.append(len(view._row_lookup))
            elif time.monotonic()<deadline:root.after(1,cancel_when_inserting)
        root.after(1,cancel_when_inserting)
        while not canceled:
            root.update();time.sleep(.002);assert time.monotonic()<deadline,(page.status.cget('text'),errors)
        before=canceled[0]
        for _ in range(5):root.update();time.sleep(.01)
        assert not view._tree_revealing and view._insert_job is None and len(view._row_lookup)==before
        assert 'Search canceled' in page.status.cget('text')
        # Deferred Tk failures must clear busy state and allow a clean retry.
        original_insert=view.tree.insert;insertions=[]
        def failing_insert(*args,**kwargs):
            insertions.append(1)
            if len(insertions)==201:raise tk.TclError('Synthetic deferred insertion failure')
            return original_insert(*args,**kwargs)
        view.tree.insert=failing_insert
        try:
            page.find_all_matched();ready(root,page)
            assert len(insertions)==201
            assert 'Structure search failed' in page.status.cget('text')
            assert not view._tree_revealing and view._insert_job is None
            assert not errors,errors
        finally:view.tree.insert=original_insert
        measuring=True;page.find_all_matched();ready(root,page);measuring=False
        assert 'Expansion limit reached' in page.status.cget('text')
        assert len(view._search_extra)<=9000
        gaps=[b[0]-a[0] for a,b in zip(pulses,pulses[1:]) if a[1] and b[1]]
        assert max(gaps,default=0)<1,('Bulk expansion blocked UI',max(gaps))
        print('Bulk expansion maximum UI heartbeat gap:',max(gaps,default=0),flush=True)
        page.find_all_matched();root.update();window.close();root.update()
        assert not errors,errors
        assert path.read_text(encoding='utf-8')==original,'Preview modified the source'
        print('PASS: retained next/previous paths; bulk matched-only expansion; query reset; stale/case/tab isolation; 200% compact controls; bounded/cancellable batches; unchanged source',flush=True)
    finally:
        running=False
        if window.winfo_exists():window.close()
        root.destroy()
