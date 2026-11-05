"""One long-lived GUI: rapid dialogs, background cancellation and resource trends."""
import ctypes
import faulthandler
import gc
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import tracemalloc
from datetime import datetime

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')
MEMORY='--memory' in sys.argv
DURATION=int(sys.argv[sys.argv.index('--seconds')+1]) if '--seconds' in sys.argv else 80
assert 5<=DURATION<=36000
STOP_FILE=Path(sys.argv[sys.argv.index('--stop-file')+1]) if '--stop-file' in sys.argv else None


def pump(app,seconds=.06):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.update();time.sleep(.003)


def sample(app,cycle):
    result={'event':'interaction.soak.sample','cycle':cycle,'threads':len(threading.enumerate()),
            'images':len(app.tk.splitlist(app.tk.call('image','names'))),
            'timers':len(app.tk.splitlist(app.tk.call('after','info'))),
            'commands':len(app.tk.splitlist(app.tk.call('info','commands'))),
            'fonts':len(app.tk.splitlist(app.tk.call('font','names'))),
            'python_current_bytes':tracemalloc.get_traced_memory()[0] if tracemalloc.is_tracing() else None}
    if os.name=='nt':
        from ctypes import wintypes as w
        kernel=ctypes.WinDLL('kernel32');user=ctypes.WinDLL('user32')
        kernel.GetCurrentProcess.restype=w.HANDLE
        user.GetGuiResources.argtypes=[w.HANDLE,w.DWORD];user.GetGuiResources.restype=w.DWORD
        result['gdi_objects']=user.GetGuiResources(kernel.GetCurrentProcess(),0)
        result['user_objects']=user.GetGuiResources(kernel.GetCurrentProcess(),1)
        class Counters(ctypes.Structure):
            _fields_=[('cb',w.DWORD),('page_faults',w.DWORD),*[(name,ctypes.c_size_t) for name in
                      ('peak_ws','working_set','peak_paged','paged','peak_nonpaged','nonpaged',
                       'pagefile','peak_pagefile','private_bytes')]]
        psapi=ctypes.WinDLL('psapi');memory=Counters();memory.cb=ctypes.sizeof(memory)
        psapi.GetProcessMemoryInfo.argtypes=[w.HANDLE,ctypes.POINTER(Counters),w.DWORD]
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(memory),memory.cb):
            result['private_bytes']=memory.private_bytes;result['working_set_bytes']=memory.working_set
    print(json.dumps(result,sort_keys=True),flush=True)
    return result


with tempfile.TemporaryDirectory(prefix='pfc-interaction-soak-') as raw:
    root=Path(raw);folder=root/'files';folder.mkdir()
    documents={
        'notes.md':'# Report\n\nNEEDLE **bold**\n\n'+('Paragraph text\n'*60),
        'tree.json':json.dumps({'groups':[{'name':f'NEEDLE {n}','details':['detail '*30]*8} for n in range(30)]}),
        'table.csv':'name,value\n'+'\n'.join(f'item{n},NEEDLE {n}' for n in range(100)),
        'settings.toml':'[tool]\nname="NEEDLE"\nvalues=[1,2,3]\n',
        'settings.yaml':'name: NEEDLE\nitems:\n  - alpha\n  - beta\n',
        'script.reg':'Windows Registry Editor Version 5.00\n\n[HKEY_CURRENT_USER\\Software\\PFC-Fixture]\n"Name"="NEEDLE"\n',
        'events.jsonl':'{"event":"NEEDLE start"}\n{"event":"NEEDLE done"}\n',
        'table.tsv':'name\tvalue\nNEEDLE\t001\n',
        'diagram.svg':'<svg xmlns="http://www.w3.org/2000/svg" width="320" height="80"><rect width="320" height="80" fill="white"/><text x="10" y="45">NEEDLE</text></svg>',
        'flow.mmd':'flowchart LR\n A[NEEDLE] --> B[Result]',
        'report.html':'<h1>NEEDLE</h1><p>Saved static report.</p>',
        'change.patch':'--- a/sample\n+++ b/sample\n@@ -1 +1 @@\n-old\n+NEEDLE\n',
        'notebook.ipynb':json.dumps({'nbformat':4,'nbformat_minor':5,'metadata':{},'cells':[
            {'cell_type':'markdown','source':['# NEEDLE'],'metadata':{}},
            {'cell_type':'code','source':['print("never execute")'],'metadata':{},'execution_count':1,
             'outputs':[{'output_type':'stream','name':'stdout','text':['NEEDLE stored output']}]}]}),
    }
    for name,data in documents.items():(folder/name).write_text(data,encoding='utf-8')
    for n in range(120):(folder/f'{n:03} Searchable file.txt').write_text('NEEDLE')
    compare_roots=[root/'compare-left',root/'compare-right']
    for side,directory in enumerate(compare_roots):
        directory.mkdir()
        (directory/'note.txt').write_text(''.join(f'line {n}: {"changed" if side and n==64 else "same"}\n' for n in range(256)))
    review_paths=[root/'wide-left.md',root/'wide-right.md']
    review_source=''.join(f'{n:05}: '+('NEEDLE wide review '*60)+'\n' for n in range(2048))
    for side,path in enumerate(review_paths):
        path.write_text(review_source.replace('00064:','CHANGED:' if side else '00064:',1))
    review_hashes=[hashlib.sha256(path.read_bytes()).digest() for path in review_paths]
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**k:True
    pfc.Commander._start_windows_tray=lambda *a:None
    if '--inject-tcl-error' in sys.argv:
        original_log=pfc.DiagnosticLog
        pfc.DiagnosticLog=lambda version,**kwargs:original_log(version,directory=root/'diagnostics',**kwargs)
    app=pfc.Commander();failures=[];maximum_gap=[0.0];cycle=0
    if MEMORY:tracemalloc.start()
    previous_unraisable=sys.unraisablehook;previous_thread=threading.excepthook
    def unraisable(event):
        failures.append(('unraisable',event.exc_type.__name__));previous_unraisable(event)
    def thread_error(event):
        failures.append(('thread',event.exc_type.__name__));previous_thread(event)
    original_callback=app.report_callback_exception
    def callback_error(*exc):
        failures.append(('callback',exc[0].__name__));original_callback(*exc)
    sys.unraisablehook=unraisable;threading.excepthook=thread_error
    app.report_callback_exception=callback_error
    original_error=pfc.messagebox.showerror
    pfc.messagebox.showerror=lambda *a,**k:failures.append(('error-dialog',str(a[0]) if a else 'error'))
    original_exception=app.debug_log.exception
    def safe_background_records(sessions):
        records=[]
        for line in app.debug_log.snapshot(automatic=True).splitlines():
            try:record=json.loads(line)
            except ValueError:continue
            if record.get('session') in sessions and record.get('event')=='tk.background.failed':
                records.append({key:record[key] for key in
                    ('event','version','time','session','error','reason','callback','frames') if key in record})
        return records
    def diagnostic_exception(event,exc,severity='ERROR'):
        if severity in ('ERROR','CRITICAL'):failures.append(('automatic-diagnostic',event,type(exc).__name__))
        result=original_exception(event,exc,severity)
        if event=='tk.background.failed':
            print(json.dumps({'event':'interaction.safe.background','cycle':cycle,'stage':stage[0],
                              'records':safe_background_records({app.debug_log.session})}),flush=True)
        return result
    app.debug_log.exception=diagnostic_exception
    last=[time.monotonic()];beat_job=[None];stage=['initialization']
    def beat():
        now=time.monotonic();gap=now-last[0];last[0]=now
        maximum_gap[0]=max(maximum_gap[0],gap)
        if gap>1:print(json.dumps({'event':'interaction.heartbeat.slow','stage':stage[0],'seconds':gap}),flush=True)
        if gap>5 and not MEMORY:failures.append(('event-loop-stall',stage[0],gap))
        beat_job[0]=app.after(20,beat)
    started=time.monotonic();sample_count=0;resource_baseline=None;compare_cycles=0;nested_cycles=0
    review_cycles=0;review_completed=0
    resource_allowance={'commands':400,'images':512,'fonts':100,'timers':100,'threads':16,
                        'gdi_objects':512,'user_objects':256,'private_bytes':256*1024**2}
    if DURATION>180:faulthandler.dump_traceback_later(90,repeat=True)
    module_path=Path(pfc.__file__)
    source_bundle=module_path.name=='app.py'
    files=sorted(module_path.parent.glob('*.py')) if source_bundle else [module_path]
    candidate=hashlib.sha256()
    for file in files:
        if source_bundle:candidate.update(file.name.encode())
        candidate.update(file.read_bytes())
    print(json.dumps({'event':'interaction.soak.start','version':pfc.__version__,
                      'system_time':datetime.now().astimezone().isoformat(),'candidate_sha256':candidate.hexdigest(),
                      'candidate_kind':'source-bundle' if source_bundle else 'portable',
                      'python':sys.version.split()[0],'duration_target_s':DURATION,'memory_instrumented':MEMORY,
                      'fixture_formats':len(documents),'diagnostic_session':app.debug_log.session}),flush=True)
    # Only this campaign's known failed test session; no document or raw Tcl text.
    prior=safe_background_records({'4cf3c5fb5137'})
    if prior:print(json.dumps({'event':'interaction.prior.safe.background','records':prior}),flush=True)
    try:
        app.auto_font_size_var.set(False)
        for pane in app.visible_panes():pane.navigate(folder)
        pump(app,.4);beat();sample(app,0);sample_count+=1
        if '--inject-tcl-error' in sys.argv:
            app.tk.call('after','idle','pfc_fixture_deleted_callback')
        stopped=False
        while time.monotonic()-started<DURATION:
            if STOP_FILE is not None and STOP_FILE.exists():stopped=True;break
            if DURATION>180:faulthandler.dump_traceback_later(90,repeat=True)
            stage[0]='font-and-panel-layout'
            app.geometry(f'{1260 if cycle%2 else 1000}x700+0+0')
            app.font_size_var.set(('small','large','xl')[cycle%3]);app.select_manual_font_size()
            app.panel_count_var.set((1,2,3,4)[cycle%4]);app.apply_panel_count(save=False);pump(app)
            stage[0]='settings-open'
            app.show_settings();pump(app,.02);dialog=app.settings_window
            dialog.show_page(pfc.SETTINGS_CATEGORIES[cycle%len(pfc.SETTINGS_CATEGORIES)][0]);pump(app,.02)
            stage[0]='settings-close';dialog.cancel();pump(app,.02)
            paths=[folder/name for name in documents];selected=paths[cycle%len(paths)]
            # A period coprime to the format count exercises every format with
            # both rapid-close and longer-settled loads, not only odd/even ones.
            stage[0]='preview-open';app.preview_paths(paths,selected);pump(app,.03 if cycle%3 else .25)
            preview=app.preview_window
            if preview and preview.winfo_exists():
                page=preview.active_page
                if page is not None:
                    page.search_var.set('NEEDLE');page.find_next()
                    if cycle%3==0:page.find_all_matched()
                pump(app,.025);stage[0]='preview-close';preview.close()
            if cycle%5==0:
                stage[0]='compare-open'
                is_folder=cycle%10!=0
                is_review=cycle%100==0
                pair=(review_paths if is_review else compare_roots if is_folder else
                      [directory/'note.txt' for directory in compare_roots])
                app.compare_paths(*pair);pump(app,1.0 if is_review else .05 if cycle%3 else .2)
                window=app.compare_window;assert window is not None and window.winfo_exists()
                frame=window.current_comparison()
                if is_review:
                    assert type(frame).__name__=='ReviewCompare','Wide fixture did not use the large-file Review engine'
                    review_cycles+=1;review_completed+=not getattr(frame,'busy',False)
                    if not frame.busy:
                        frame.next();frame.mark_reviewed();assert frame.checked
                        frame.mark_reviewed();assert not frame.checked
                        frame.search_var.set('NEEDLE');window._shortcut('find_next')
                        frame.wrap.set(cycle%200==0);frame.render();pump(app,.02)
                if is_folder and not frame._scanning:
                    frame.open_nested_detail(*(directory/'note.txt' for directory in compare_roots),'note.txt')
                    pump(app,.02);frame.close_nested_detail();nested_cycles+=1
                stage[0]='compare-close';window.close();pump(app,.02);compare_cycles+=1
            stage[0]='search-open-run-close'
            app.search();pump(app,.02);search=app.search_window
            search.path_var.set(str(folder));search.mask_var.set('*.txt');search.start()
            pump(app,.01 if cycle%2 else .12)
            if search.search_state in ('running','cancelling'):search.cancel()
            search.close();pump(app,.04)
            if cycle%7==0:
                # Keep inputs bounded during multi-hour runs so resource trends
                # are not confused with an ever-growing number of files.
                (folder/f'download-{(cycle//7)%16}.txt').write_text('new file')
                app.active.refresh();pump(app,.04)
            cycle+=1
            if cycle%8==0:
                resources=sample(app,cycle);sample_count+=1
                # This fixture has bounded input/cache diversity. Use a warmed
                # baseline and broad regression guardrails, not production caps.
                if cycle>=64 and resource_baseline is None:resource_baseline=resources
                if resource_baseline is not None:
                    for key,allowance in resource_allowance.items():
                        if key in resources:
                            assert resources[key]<=resource_baseline[key]+allowance,('Resource growth',key,resource_baseline[key],resources[key])
            assert not failures,failures
        pump(app,1);gc.collect();pump(app,.2)
        sample(app,cycle);sample_count+=1
        assert not failures,failures
        assert [hashlib.sha256(path.read_bytes()).digest() for path in review_paths]==review_hashes,'Read-only review changed fixture bytes'
        assert cycle>=min(8,DURATION//2),('Too few completed scenarios',cycle)
        if not MEMORY:assert maximum_gap[0]<5,('Event loop stalled',maximum_gap[0])
        print(json.dumps({'event':'interaction.soak.stopped' if stopped else 'interaction.soak.passed','cycles':cycle,
                          'seconds':round(time.monotonic()-started,3),
                          'max_heartbeat_gap_s':maximum_gap[0],'samples':sample_count,
                          'timing_acceptance':not MEMORY,'target_complete':not stopped,
                          'compare_cycles':compare_cycles,'nested_compare_cycles':nested_cycles,
                          'wide_review_cycles':review_cycles,'wide_review_completed':review_completed}),flush=True)
    finally:
        if beat_job[0] is not None:app.after_cancel(beat_job[0])
        app.close_app();pfc.messagebox.showerror=original_error
        sys.unraisablehook=previous_unraisable;threading.excepthook=previous_thread
        tracemalloc.stop()
        if DURATION>180:faulthandler.cancel_dump_traceback_later()
