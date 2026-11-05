"""One long-lived GUI: rapid dialogs, background cancellation and resource trends."""
import ctypes
import gc
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import tracemalloc

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
    }
    for name,data in documents.items():(folder/name).write_text(data,encoding='utf-8')
    for n in range(120):(folder/f'{n:03} Searchable file.txt').write_text('NEEDLE')
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**k:True
    pfc.Commander._start_windows_tray=lambda *a:None
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
    last=[time.monotonic()];beat_job=[None];stage=['initialization']
    def beat():
        now=time.monotonic();gap=now-last[0];last[0]=now
        maximum_gap[0]=max(maximum_gap[0],gap)
        if gap>1:print(json.dumps({'event':'interaction.heartbeat.slow','stage':stage[0],'seconds':gap}),flush=True)
        if gap>5 and not MEMORY:failures.append(('event-loop-stall',stage[0],gap))
        beat_job[0]=app.after(20,beat)
    started=time.monotonic();sample_count=0
    print(json.dumps({'event':'interaction.soak.start','version':pfc.__version__,
                      'python':sys.version.split()[0],'duration_target_s':DURATION,'memory_instrumented':MEMORY}),flush=True)
    try:
        app.auto_font_size_var.set(False)
        for pane in app.visible_panes():pane.navigate(folder)
        pump(app,.4);beat();sample(app,0);sample_count+=1
        stopped=False
        while time.monotonic()-started<DURATION:
            if STOP_FILE is not None and STOP_FILE.exists():stopped=True;break
            stage[0]='font-and-panel-layout'
            app.geometry(f'{1260 if cycle%2 else 1000}x700+0+0')
            app.font_size_var.set(('small','large','xl')[cycle%3]);app.select_manual_font_size()
            app.panel_count_var.set((1,2,3,4)[cycle%4]);app.apply_panel_count(save=False);pump(app)
            stage[0]='settings-open'
            app.show_settings();pump(app,.02);dialog=app.settings_window
            dialog.show_page(pfc.SETTINGS_CATEGORIES[cycle%len(pfc.SETTINGS_CATEGORIES)][0]);pump(app,.02)
            stage[0]='settings-close';dialog.cancel();pump(app,.02)
            paths=[folder/name for name in documents];selected=paths[cycle%len(paths)]
            stage[0]='preview-open';app.preview_paths(paths,selected);pump(app,.03 if cycle%2 else .2)
            preview=app.preview_window
            if preview and preview.winfo_exists():
                page=preview.active_page
                if page is not None:
                    page.search_var.set('NEEDLE');page.find_next()
                    if cycle%3==0:page.find_all_matched()
                pump(app,.025);stage[0]='preview-close';preview.close()
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
            if cycle%8==0:sample(app,cycle);sample_count+=1
            assert not failures,failures
        pump(app,1);gc.collect();pump(app,.2)
        sample(app,cycle);sample_count+=1
        assert not failures,failures
        assert cycle>=min(8,DURATION//2),('Too few completed scenarios',cycle)
        if not MEMORY:assert maximum_gap[0]<5,('Event loop stalled',maximum_gap[0])
        print(json.dumps({'event':'interaction.soak.stopped' if stopped else 'interaction.soak.passed','cycles':cycle,
                          'seconds':round(time.monotonic()-started,3),
                          'max_heartbeat_gap_s':maximum_gap[0],'samples':sample_count,
                          'timing_acceptance':not MEMORY,'target_complete':not stopped}),flush=True)
    finally:
        if beat_job[0] is not None:app.after_cancel(beat_job[0])
        app.close_app();pfc.messagebox.showerror=original_error
        sys.unraisablehook=previous_unraisable;threading.excepthook=previous_thread
        tracemalloc.stop()
