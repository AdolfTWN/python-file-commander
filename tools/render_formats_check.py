"""Offline F3 render matrix: all formats, source/hex, tab races and MD isolation."""
import base64
import configparser
import importlib
import json
import os
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import time
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
module=importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')


def pump(root,seconds=.1):
    until=time.monotonic()+seconds
    while time.monotonic()<until:root.update();time.sleep(.01)


def ready(root,page,timeout=35):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        root.update();time.sleep(.01)
        if not (page._format_jobs.pending or page._format_queued or page._format_request or page.render_view._insert_job or page._format_find_job):return
    raise AssertionError('Render did not finish: '+page.path.name+' '+page.status.cget('text'))


def capture(window,name):
    window.lift();pump(window,.15)
    if os.name=='nt':
        from folder_native_test_support import capture_window
        capture_window(window,Path(__file__).parent/('evidence-render-'+name+'.bmp'))
    else:
        from PIL import ImageGrab
        x,y=window.winfo_rootx(),window.winfo_rooty()
        ImageGrab.grab((x,y,x+window.winfo_width(),y+window.winfo_height())).save('/tmp/pfc-render-'+name+'.png')


with tempfile.TemporaryDirectory() as raw:
    directory=Path(raw)
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path);self.send_response(200);self.end_headers();self.wfile.write(b'NOT ALLOWED')
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    endpoint='http://127.0.0.1:'+str(server.server_port)+'/blocked'
    secret=directory/'not-readable.txt';secret.write_text('PFC_SOURCE_SECRET_SENTINEL')
    execution_marker=directory/'must-not-execute.txt'
    old_marker=os.environ.get('PFC_PREVIEW_EXECUTION_MARKER');os.environ['PFC_PREVIEW_EXECUTION_MARKER']=str(execution_marker)
    fixtures={
        'agent.json':'{"agent":{"name":"Reviewer 測試😀","id":"001","model":"local","rate":1.2300e-9,"tools":["read","search"]}}',
        'events.jsonl':'{"event":"start","id":"001"}\n{"event":"done","tokens":123456789012345678901}\n',
        'evaluation.csv':'ID,Case,Result,Notes\n001,"unicode 測試😀",pass,"long cell '+('detail '*70)+'"\n002,regression,pass,"line one\nline two"\n',
        'table.tsv':'name\tcount\nexample\t001\n',
        'ragged.tsv':'\t'.join('c'+str(i) for i in range(200))+'\n'+'value\n'*1000,
        'agent.yaml':'agent:\n  name: Reviewer\n  id: "001"\n  tools: [read, search]\n',
        'pyproject.toml':'[tool.agent]\nname="Reviewer"\nratio=1.2300\n',
        'diagram.svg':'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 240"><rect x="20" y="40" width="240" height="100" rx="14" fill="#dceeff" stroke="#1767a0"/><text x="50" y="95" font-size="24">Source input</text><path d="M260 90 H500" stroke="#334455" stroke-width="4"/><rect x="500" y="40" width="260" height="100" rx="14" fill="#e0f3e8" stroke="#286c44"/><text x="525" y="95" font-size="24">Safe preview</text></svg>',
        'flow.mmd':'flowchart LR\n A[Source file] --> B[Bounded parser]\n B --> C[Read-only preview]',
        'sequence.mermaid':'sequenceDiagram\n User->>Preview: F3\n Preview-->>User: Static result',
        'class.mmd':'classDiagram\n class Agent {\n +run()\n }\n Agent --> Tool',
        'report.html':'<h1>Evaluation report</h1><p>Read-only <strong>static preview</strong>.</p><table><tr><th>Case</th><th>Result</th></tr><tr><td>Unicode 測試😀</td><td>Pass</td></tr></table><script>throw new Error("must not run")</script>',
        'change.patch':'diff --git a/config b/config\n--- a/config\n+++ b/config\n@@ -1 +1 @@\n-model=old\n+model=new\n',
        'notes.md':'# Existing Markdown\n\nText with **bold** and [local](other.md).\n\n```mermaid\nflowchart LR\n A-->B\n```\n\n# Later section\nStill here.\n',
        'other.md':'# Other\nlinked text',
        'invalid.json':'{"incomplete":',
        'limited.json':json.dumps({'early':list(range(15000)),'ConnectedDeviceName':'Late value','second':{'ConnectedDeviceName':'Another'}}),
        'input-limit.json':'{"padding":"'+('x'*(2*1024*1024))+'","late":"NOT_LOADED_NEEDLE"}',
        'input-limit.jsonl':'{"value":"first record"}\n{"padding":"'+('x'*(2*1024*1024))+'","late":"NOT_LOADED_NEEDLE"}\n',
        'plain.py':'print("NEVER EXECUTED")\n',
        'blocked.html':'<h1>Visible safe content</h1><img src="'+endpoint+'"><iframe src="'+secret.as_uri()+'"></iframe><script>document.body.innerText="SCRIPT RAN";fetch('+json.dumps(endpoint)+')</script><style>@import url('+endpoint+');</style>',
    }
    notebook={'nbformat':4,'nbformat_minor':5,'metadata':{},'cells':[
        {'cell_type':'markdown','source':['# Saved notebook\n','Readable explanation and **result**.'],'metadata':{}},
        {'cell_type':'code','source':['import os\nfrom pathlib import Path\nPath(os.environ["PFC_PREVIEW_EXECUTION_MARKER"]).write_text("RAN")'],'metadata':{},'execution_count':1,
         'outputs':[{'output_type':'stream','name':'stdout','text':['Stored result: PASS\n']},
                    {'output_type':'display_data','data':{'image/svg+xml':fixtures['diagram.svg']},'metadata':{}}]}]}
    fixtures['notebook.ipynb']=json.dumps(notebook)
    paths=[]
    for name,text in fixtures.items():
        path=directory/name;path.write_text(text,encoding='utf-8');paths.append(path)
    root=tk.Tk();root.geometry('1200x800');root.title('PFC isolated render check')
    errors=[];root.report_callback_exception=lambda *exc:errors.append(str(exc))
    config=configparser.ConfigParser();config.add_section('preview');config.set('preview','geometry','1160x760')
    window=module.PreviewWindow(root,config,lambda:None,paths,paths[0])
    try:
        for name,kind in (('agent.json','tree'),('events.jsonl','tree'),('evaluation.csv','grid'),('table.tsv','grid'),('ragged.tsv','grid'),
                          ('agent.yaml','tree'),('pyproject.toml','tree'),('diagram.svg','image'),('flow.mmd','image'),
                          ('sequence.mermaid','image'),('class.mmd','image'),('report.html','image'),('blocked.html','image'),('notebook.ipynb','image'),('change.patch','document')):
            path=directory/name;window.show(paths,path);page=window.active_page;ready(root,page)
            assert page.render_view.model.get('kind')==kind,(name,page.status.cget('text'),page.render_view.model.get('notice'))
            assert page.render_view.model.get('rendered'),(name,page.status.cget('text'))
            assert not page.render_view.model.get('fallback'),(name,page.status.cget('text'))
            if name=='ragged.tsv':
                assert page.render_view.model['truncated']
                assert len(page.render_view.tree.get_children())<=100
            if name in {'agent.json','evaluation.csv','diagram.svg','flow.mmd','report.html','notebook.ipynb','change.patch'}:capture(window,name.split('.')[0])
            if name=='blocked.html':
                assert 'Visible safe content' in page.render_view.model['content']
                assert 'SCRIPT RAN' not in page.render_view.model['content']
                assert 'PFC_SOURCE_SECRET_SENTINEL' not in page.render_view.model['content']
                assert not requests,requests
            if name=='agent.json':
                page.search_var.set('Reviewer');page.find_next();ready(root,page);assert page.render_view.tree.selection()
            if name=='evaluation.csv':
                shown=page.render_view.tree.item('r1','values')[-1]
                assert '↵' in shown and '\r' not in shown and '\n' not in shown,repr(shown)
                page.search_var.set('detail');page.find_next();assert page.render_view.tree.selection()
                page.render_view.copy();assert 'detail' in root.clipboard_get()
                page.render_view.choice.set('First row: data');page.render_view._choose()
                assert page.render_view._grid_rows[0][0]=='ID'
                for _ in range(3):page.render_view._choose()
                assert len([c for c in page.render_view.winfo_children() if isinstance(c,tk.Menu)])==1
            page.markdown_var.set(next(k for k,v in page.markdown_values.items() if v=='source'));page.load();ready(root,page)
            assert page.render_view.model['kind']=='document'
            assert not page.render_view.model['rendered']
            page.mode_var.set(next(k for k,v in page.mode_values.items() if v=='Hex'));page.load();pump(root)
            assert not page._format_active and '00000000' in page.text.get('1.0','end')
            page.mode_var.set(next(k for k,v in page.mode_values.items() if v=='Auto'))
        window.show(paths,directory/'invalid.json');page=window.active_page;ready(root,page)
        assert page.render_view.model.get('fallback') and 'Source fallback:' in page.status.cget('text')
        assert 'incomplete' in page.render_view.text.get('1.0','end')
        window.show(paths,directory/'limited.json');page=window.active_page;ready(root,page)
        assert page.render_view.model['kind']=='tree' and page.render_view.model['truncated']
        assert not any(r['label']=='ConnectedDeviceName' for r in page.render_view.model['rows'])
        assert not page.render_view.choice.winfo_ismapped()
        assert page.render_view.expand_button.winfo_ismapped() and page.render_view.collapse_button.winfo_ismapped()
        page.render_view.collapse_button.invoke()
        assert not any(page.render_view.tree.item(r['id'],'open') for r in page.render_view.model['rows'])
        page.render_view.expand_button.invoke()
        assert all(page.render_view.tree.item(r['id'],'open') for r in page.render_view.model['rows'])
        capture(window,'structure-controls')
        original_tree=page.render_view.tree
        page.search_var.set('ConnectedDeviceName');page.find_next();ready(root,page)
        assert page.render_view.model['kind']=='tree' and page.render_view.tree is original_tree
        assert page.markdown_values[page.markdown_var.get()]=='rendered'
        assert 'Match 1 of 2' in page.status.cget('text')
        first=page.render_view.tree.selection()
        assert page.render_view.tree.item(first[0],'text')=='ConnectedDeviceName'
        page.find_next();ready(root,page);assert 'Match 2 of 2' in page.status.cget('text')
        assert page.render_view.tree.selection()!=first
        page.find_previous();ready(root,page);assert page.render_view.tree.selection()==first
        capture(window,'structure-search')
        window.show(paths,directory/'input-limit.json');page=window.active_page;ready(root,page)
        assert page.render_view.model['truncated']
        page.search_var.set('NOT_LOADED_NEEDLE');page.find_next()
        assert 'rest of the file was not searched' in page.status.cget('text')
        assert 'No matches' not in page.status.cget('text')
        window.show(paths,directory/'input-limit.jsonl');page=window.active_page;ready(root,page)
        assert page.render_view.model['kind']=='tree' and page.render_view.model['truncated']
        page.search_var.set('NOT_LOADED_NEEDLE');page.find_next();ready(root,page)
        assert page.render_view.model['kind']=='tree'
        assert 'results are partial' in page.status.cget('text') and 'No matches in searched structure' in page.status.cget('text')
        # Starting a graph then immediately switching must cancel and ignore its results.
        window.show(paths,directory/'flow.mmd');page=window.active_page
        page.markdown_var.set(next(k for k,v in page.markdown_values.items() if v=='rendered'));page.load()
        window.show(paths,directory/'notes.md');md=window.active_page
        until=time.monotonic()+10
        while time.monotonic()<until:
            pump(root,.05)
            if md._md_model.get('rendered') and not md._md_insert:break
        assert not md._format_active and 'Existing Markdown' in md.text.get('1.0','end')
        assert md._md_model.get('diagrams') and md._md_model.get('headings'),(md.status.cget('text'),md._md_model.get('notice'),md._md_model.get('rendered'))
        assert not page._format_jobs.pending
        md._open_diagram(0);diagram=window.active_page;ready(root,diagram)
        assert diagram.render_view.model['kind']=='image'
        # Large text controls and narrow layout: no hidden cancel / search actions.
        window.show(paths,directory/'evaluation.csv');page=window.active_page
        page.markdown_var.set(next(k for k,v in page.markdown_values.items() if v=='rendered'));page.load();ready(root,page)
        originals={name:tkfont.nametofont(name).cget('size') for name in ('TkDefaultFont','TkFixedFont','TkTextFont','TkMenuFont','TkHeadingFont')}
        for name,size in originals.items():tkfont.nametofont(name).configure(size=round(size*2))
        ttk.Style(root).configure('Treeview',rowheight=44,font='TkDefaultFont')
        window.geometry('800x660');window.apply_scale(2);pump(root,.3);capture(window,'table-200')
        assert not diagram._loaded,'Inactive graphics must refresh at the new font scale'
        page.render_view.tree.event_generate('<Button-3>',x=2,y=page.render_view.tree.winfo_height()-5)
        pump(root,.05)
        assert page.find_prev_button.winfo_rooty()==page.find_next_button.winfo_rooty()
        assert page.render_view.choice.winfo_ismapped() and page.render_view.copy_button.winfo_ismapped()
        window.show(paths,directory/'agent.json');page=window.active_page
        page.markdown_var.set(next(k for k,v in page.markdown_values.items() if v=='rendered'));page.load()
        ready(root,page);page.render_view.rescale();pump(root)
        assert page.render_view.expand_button.winfo_ismapped() and page.render_view.collapse_button.winfo_ismapped()
        assert page.render_view._tree_icons[0].height()>=tkfont.nametofont('TkDefaultFont').metrics('linespace')
        capture(window,'structure-controls')
        assert not errors,errors
        assert not execution_marker.exists(), 'Notebook code must never execute'
        assert not requests,requests
        print('PASS: 8 format families, source/hex, raw identifiers, search/copy, table headers, malformed fallback, MD diagram tabs, cancellation and 200% layout',flush=True)
        print('NOTE: offline static rendering; no code execution or live cloud/network acceptance.',flush=True)
    finally:
        window.close();pump(root,.4);root.destroy();server.shutdown();server.server_close()
        if old_marker is None:os.environ.pop('PFC_PREVIEW_EXECUTION_MARKER',None)
        else:os.environ['PFC_PREVIEW_EXECUTION_MARKER']=old_marker
