"""Large single-line JSON: preserve hierarchy, bounded Tk work, responsive search."""
import configparser
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
module=importlib.import_module('pfc' if len(sys.argv)>1 and sys.argv[1]=='pfc' else 'pycommander.app')

def ready(root,page,timeout=25):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        root.update();time.sleep(.01)
        if not (page._format_jobs.pending or page._format_queued or page._format_request
                or page.render_view._insert_job or page._format_find_job):
            root.update();return
    raise AssertionError('Structure request did not finish')

def capture(window,name):
    global phase
    previous=phase;phase='capture-'+name
    window.lift();window.update();time.sleep(.15);window.update()
    if os.name=='nt':
        from folder_native_test_support import capture_window
        capture_window(window,Path(__file__).parent/('evidence-structure-'+name+'.bmp'))
    else:
        from PIL import ImageGrab
        x,y=window.winfo_rootx(),window.winfo_rooty()
        ImageGrab.grab((x,y,x+window.winfo_width(),y+window.winfo_height())).save('/tmp/pfc-structure-'+name+'.png')
    time.sleep(.03);window.update();phase=previous

with tempfile.TemporaryDirectory() as raw:
    root=tk.Tk();root.geometry('1200x800');errors=[]
    root.report_callback_exception=lambda *exc:errors.append(str(exc))
    path=Path(raw)/'large-single-line.json'
    blob='['+('{"Name":"Device","Value":"00000000-0000-0000","State":true},'*10000)+'{"Name":"AW27 first"},'+('{"Other":"000000000000000000000000"},'*8000)+'{"Name":"AW27 second"}]'
    data={'early':list(range(15000)),'nested':{'device':{'ConnectedDeviceName':'AW27','SerializedBlob':blob}}}
    source=json.dumps(data,ensure_ascii=False);path.write_text(source,encoding='utf-8')
    assert len(source.encode('utf-8'))<2*1024*1024
    config=configparser.ConfigParser();config.add_section('preview')
    config.set('preview','geometry','1160x760');config.set('preview','wrap','true')
    win=module.PreviewWindow(root,config,lambda:None,[path],path)
    page=win.active_page;ready(root,page)
    pulses=[];running=True;phase='tree'
    def pulse():
        if running:pulses.append((time.monotonic(),phase));root.after(20,pulse)
    pulse()
    try:
        view=page.render_view;tree=view.tree;initial=len(view._row_lookup)
        assert initial<=3000 and view.model['truncated'] and view.text is None
        early=next(r['id'] for r in view.model['rows'] if r['label']=='early')
        tree.item(early,open=False)
        page.wrap_var.set(True)  # Must not turn a tree search into wrapped Text.
        timings=[]
        def find(needle,direction=1):
            global phase
            phase='tree-search'
            page.search_var.set(needle);start=time.monotonic()
            page._find(direction);ready(root,page);timings.append(time.monotonic()-start)
            assert view.tree is tree and view.model['kind']=='tree' and view.text is None
            assert page.markdown_values[page.markdown_var.get()]=='rendered'
            assert not tree.item(early,'open'), 'Unrelated expansion state was lost'
            assert len(view._row_lookup)<=initial+65, 'Search accumulated unbounded Tk rows'
        find('ConnectedDeviceName')
        selected=tree.selection()[0]
        assert tree.item(selected,'text')=='ConnectedDeviceName'
        parent=tree.parent(selected)
        while parent:assert tree.item(parent,'open');parent=tree.parent(parent)
        capture(win,'late-key')
        find('AW27');assert 'Match 1 of 3' in page.status.cget('text')
        find('AW27');assert 'Match 2 of 3' in page.status.cget('text')
        assert tree.item(tree.selection()[0],'text')=='SerializedBlob'
        assert 'AW27 first' in tree.item(tree.selection()[0],'values')[0]
        view._copy_path();assert root.clipboard_get()=='/nested/device/SerializedBlob'
        find('AW27');assert 'Match 3 of 3' in page.status.cget('text')
        assert 'AW27 second' in tree.item(tree.selection()[0],'values')[0]
        find('AW27',-1);assert 'Match 2 of 3' in page.status.cget('text')
        capture(win,'long-value')
        for needle in ('ConnectedDeviceName','AW27','missing sentinel')*3:find(needle)
        assert 'No matches' in page.status.cget('text')
        page.case_var.set(True);find('aw27');assert 'No matches' in page.status.cget('text')
        page.case_var.set(False)
        # Rapid replacement must discard stale results, not navigate to the old query.
        page.search_var.set('ConnectedDeviceName');page.find_next();root.update()
        page.search_var.set('AW27');page.find_next();ready(root,page)
        assert 'of 3' in page.status.cget('text') and view.tree is tree
        page.find_next();page._cancel_format_ui();ready(root,page)
        assert view.tree is tree and 'Search canceled' in page.status.cget('text')
        path.write_text(source+' ',encoding='utf-8')
        find('AW27');assert 'reload' in page.status.cget('text').lower()
        for name,content in (('sample.yaml','nested:\n  device: AW27\n'),('sample.toml','[nested]\ndevice="AW27"\n'),('sample.jsonl','{"nested":{"device":"AW27"}}\n')):
            phase='format-switch'
            other=Path(raw)/name;other.write_text(content,encoding='utf-8')
            win.show([path,other],other);other_page=win.active_page;ready(root,other_page)
            other_page.search_var.set('AW27');other_page.find_next();ready(root,other_page)
            assert other_page.render_view.model['kind']=='tree' and 'Match 1 of 1' in other_page.status.cget('text')
            assert other_page.render_view.tree.selection()
        phase='tree-reload';win.show([path],path);page=win.active_page;page.load();ready(root,page)
        view=page.render_view
        # Explicit Source is still supported; giant physical lines must not enter
        # Tk word-wrap layout (the v0.18.36 automatic fallback's blocking path).
        phase='source-load';page.markdown_var.set(next(k for k,v in page.markdown_values.items() if v=='source'))
        page.load();ready(root,page)
        assert view.model['kind']=='document' and view.model['wrap_limited']
        assert view.text.cget('wrap')=='none' and page.wrap_check.instate(['disabled'])
        capture(win,'source-wrap')
        phase='source-search';page.search_var.set('AW27');page.find_next();ready(root,page)
        assert 'Match 1 of 3' in page.status.cget('text')
        assert view.text.bbox('format_match.first') is not None, 'Source match must be visible, not just counted'
        assert len(view.text.get('1.0','end-1c'))<=16384
        view.copy();assert root.clipboard_get()==view.model['content'], 'Copy must retain full loaded source'
        for count in (2,3):
            page.find_next();ready(root,page)
            assert f'Match {count} of 3' in page.status.cget('text')
            assert view.text.bbox('format_match.first') is not None
        view.model['sections']=[{'offset':view.model['content'].rindex('AW27'),'title':'Last match'}]
        view.choice.configure(values=('Last match',));view.choice.current(0);view._choose();root.update()
        assert 'AW27 second' in view.text.get('1.0','end-1c'), 'Section navigation must reposition the source window'
        root.update()
        by_phase={}
        for (a,_),(b,name) in zip(pulses,pulses[1:]):by_phase[name]=max(by_phase.get(name,0),b-a)
        # Screenshot capture is test I/O, not an application operation. Keep its
        # timing visible but do not attribute it to PFC responsiveness.
        gaps=[value for name,value in by_phase.items() if not name.startswith('capture-')]
        print('UI heartbeat seconds by phase:',by_phase,flush=True)
        assert max(gaps,default=0)<3, ('UI heartbeat blocked',by_phase)
        assert not errors,errors
        print('PASS: tree retained; late keys and long values revealed; next/previous, case, stale query, cancel, changed file, explicit Source guard')
        print('Search seconds:',timings,'maximum UI heartbeat gap:',max(gaps,default=0),flush=True)
    finally:
        running=False;win.close();root.destroy()
