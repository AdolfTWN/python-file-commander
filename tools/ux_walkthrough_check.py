"""Isolated user-task checks for visible waiting and truthful terminal states."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')
search=pfc if pfc.__name__=='pfc' else importlib.import_module('pycommander.search')

def pump(app,condition=lambda:True):
    end=time.monotonic()+15
    while time.monotonic()<end:
        app.update();time.sleep(.02)
        if condition():return
    raise AssertionError('UX walkthrough timed out')

def capture(window,name):
    window.lift();window.update();time.sleep(.12);window.update()
    if os.name=='nt':
        from folder_native_test_support import capture_window
        capture_window(window,Path(__file__).parent/('evidence-ux-'+name+'.bmp'))
    else:
        from PIL import ImageGrab
        x,y=window.winfo_rootx(),window.winfo_rooty()
        ImageGrab.grab((x,y,x+window.winfo_width(),y+window.winfo_height())).save('/tmp/pfc-ux-'+name+'.png')

def above(label,content):
    assert label.winfo_ismapped()
    assert label.winfo_rooty()+label.winfo_height()<=content.winfo_rooty()+2
    top=label.winfo_toplevel()
    assert label.winfo_rootx()+label.winfo_width()<=top.winfo_rootx()+top.winfo_width()+2

with tempfile.TemporaryDirectory(prefix='pfc-ux-') as raw:
    root=Path(raw).resolve();md=root/'notes.md';md.write_text('# Notes\n\nSample text\n')
    if os.name=='nt':
        # Reproduce an actual Windows reader denying delete-share while the
        # worker publishes a result. This must retry rather than die silently.
        import ctypes
        from ctypes import wintypes as w
        import pfc_windows_worker as worker
        report=root/'result.json';worker.atomic_report(report,{'status':'running'})
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,ctypes.c_void_p,w.DWORD,w.DWORD,w.HANDLE]
        kernel.CreateFileW.restype=w.HANDLE;kernel.CloseHandle.argtypes=[w.HANDLE]
        handle=kernel.CreateFileW(str(report),0x80000000,3,None,3,0,None)
        assert handle not in (None,ctypes.c_void_p(-1).value)
        tmp=report.with_suffix('.tmp');tmp.write_text('{}')
        try:tmp.replace(report)
        except PermissionError:pass
        else:
            kernel.CloseHandle(handle)
            raise AssertionError('Fixture did not reproduce a Windows sharing violation')
        timer=threading.Timer(.15,lambda:kernel.CloseHandle(handle));timer.start()
        try:worker.atomic_report(report,{'status':'passed'})
        finally:timer.join()
        import json
        assert json.loads(report.read_text())['status']=='passed'
    folder=root/'folder';folder.mkdir();(folder/'report.txt').write_text('sample')
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**kw:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();errors=[];gate=threading.Event()
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False);app.active.navigate(root)
        for panels in (1,2,3,4):
            app.panel_count_var.set(panels);app.apply_panel_count(save=False);pump(app)
            assert len(app.visible_panes())==panels
        app.show_settings();pump(app);settings=app.settings_window
        for key,_ in pfc.SETTINGS_CATEGORIES:
            settings.show_page(key);pump(app);assert settings.footer.winfo_ismapped()
        settings.cancel()
        app.search();pump(app);s=app.search_window;s.path_var.set(str(root));original=s._search
        def slow(criteria):
            s.messages.put(('progress',1,100))
            while not gate.wait(.02):
                if s.cancel_event.is_set():
                    s.messages.put(('done',0,True,False));return
            s.messages.put(('done',0,False,False))
        for scale,key,width,language,theme in (('100','small',1180,'en','light'),('200','xl',1180,'zh_TW','dark'),('narrow','175',760,'zh_CN','light')):
            app.ui_language_var.set(language);app.apply_ui_language();pump(app)
            app.color_scheme_var.set(theme);app.apply_color_scheme(save=False);pump(app)
            app.font_size_var.set(key);app.apply_font_size(save=False)
            s.geometry(f'{width}x740+0+0');pump(app);gate.clear();s._search=slow;s.start();pump(app)
            face=pfc.tkfont.nametofont('TkDefaultFont')
            for button in s.result_buttons:
                assert button.winfo_width()>=face.measure(button.cget('text'))+12, (language,button.cget('text'))
            assert s.results_menu.entrycget(0,'label')==pfc.tr('Go to File')
            assert s.search_state=='running' and s.empty_hint.winfo_ismapped()
            above(s.status,s.tree)
            assert str(s.progress.cget('mode'))=='indeterminate'
            value=float(s.progress.cget('value'));time.sleep(.15);pump(app)
            assert float(s.progress.cget('value'))!=value,'No visible activity during wait'
            assert s.mask_entry.instate(['disabled']) and s.depth_combo.instate(['disabled'])
            assert s.days_controls.winfo_ismapped() and s.size_controls.winfo_ismapped()
            capture(s,'search-running-'+scale)
            s.cancel();pump(app,lambda:s.worker is None)
            assert s.search_state=='cancelled' and float(s.progress.cget('value'))!=100
            assert s.mask_entry.instate(['!disabled']) and s.depth_combo.instate(['readonly'])
        s._search=original;s.mask_var.set('no-such-result');s.start();pump(app,lambda:s.worker is None)
        assert s.search_state=='complete' and not s.results and s.empty_hint.winfo_ismapped()
        assert s.status.cget('text')==pfc.tr('Search complete — {count} found',count=0)
        assert not s.progress.winfo_ismapped()
        capture(s,'search-empty')
        with patch.object(search.os,'walk',side_effect=RuntimeError('isolated fixture failure')):
            with patch.object(search.messagebox,'showerror') as notice:
                s.start();pump(app,lambda:s.worker is None)
                assert notice.called and s.search_state=='failed'
        capture(s,'search-failed')
        def unreadable(root,**kwargs):
            kwargs['onerror'](PermissionError('isolated fixture'));return iter(())
        with patch.object(search.os,'walk',unreadable):
            s.start();pump(app,lambda:s.worker is None)
        assert s.search_state=='partial' and s._skipped==1
        gate.clear()
        def partial(criteria):
            s.messages.put(('item',md,md.stat()))
            while not gate.wait(.02):
                if s.cancel_event.is_set():
                    s.messages.put(('done',1,True,False));return
            s.messages.put(('done',1,False,True))
        s._search=partial;s.start();pump(app,lambda:bool(s.results))
        assert s.search_state=='running' and not s.empty_hint.winfo_ismapped()
        gate.set();pump(app,lambda:s.worker is None)
        assert s.search_state=='limited' and float(s.progress.cget('value'))!=100
        # Reopen before a cancelled worker has returned: show the reason Find waits.
        gate.clear()
        def winding_down(criteria):
            gate.wait(5);s.messages.put(('done',0,True,False))
        s._search=winding_down;s.start();pump(app);s.reset_for_open();pump(app)
        assert s.search_state=='resetting' and s.find_button.instate(['disabled'])
        gate.set();pump(app,lambda:s._reset_job is None)
        assert s.search_state=='ready' and not s.results
        s._search=original;s.close()
        app.preview_paths([md],md);page=app.preview_window.active_page
        assert str(page.text.cget('state'))=='disabled','Loading Preview is editable'
        before=page.text.get('1.0','end');page.text.insert('1.0','must not appear')
        assert page.text.get('1.0','end')==before
        pump(app)
        above(page.status,page.text);capture(app.preview_window,'preview')
        app.preview_window.close();app.preview_window=None
        app.compare_paths(root,folder);pump(app);cw=app.compare_window;fc=cw.current_comparison()
        pump(app,lambda:not fc._scanning);above(fc.scan_status,fc.left_tree)
        assert fc.scan_cancel_button.instate(['disabled'])
        fc.start_scan();assert fc.scan_cancel_button.instate(['!disabled'])
        fc.cancel_scan();assert fc.scan_cancel_button.instate(['disabled'])
        capture(cw,'folder');cw.close();app.compare_window=None
        rename=pfc.MultiRenameWindow(app,[md],[],lambda:None);pump(app)
        assert rename.tree.item(rename.tree.get_children()[0],'tags')==('unchanged',)
        assert str(rename.tree.tag_configure('unchanged','foreground'))==app.palette['text']
        rename.destroy()
        assert not errors,errors
        print('PASS: waiting/zero/complete/cancel/error/limit/unreadable; 100/200/narrow; 1–4 panels; Settings pages; Preview/Folder status')
    finally:
        gate.set();app.close_app()
