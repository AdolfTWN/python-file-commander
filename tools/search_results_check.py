"""Real search traversal, attribute notes, mouse navigation and window lifetime."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv[1:] else 'pycommander.app')

def settle(app, condition=lambda:True):
    end=time.monotonic()+12
    while time.monotonic()<end:
        app.update();time.sleep(.02)
        if condition(): return
    raise AssertionError('Search GUI operation timed out')

def capture(win, scale):
    win.lift();win.update();time.sleep(.15);win.update()
    if os.name=='nt':
        from folder_native_test_support import capture_window
        capture_window(win,Path(__file__).parent/('evidence-search-'+scale+'.bmp'))
    else:
        from PIL import ImageGrab
        x,y=win.winfo_rootx(),win.winfo_rooty()
        ImageGrab.grab((x,y,x+win.winfo_width(),y+win.winfo_height())).save('/tmp/pfc-search-'+scale+'.png')

def main():
    with tempfile.TemporaryDirectory() as raw:
        root=Path(raw).resolve();folder=root/'search';folder.mkdir()
        hidden=folder/'.hidden.md';hidden.write_text('# Hidden\n')
        normal=folder/'ordinary.md';normal.write_text('# Normal\n')
        system=folder/'system.md';system.write_text('# System\n')
        both=folder/'.both.md';both.write_text('# Both\n')
        nested=folder/'.hidden-folder';nested.mkdir();(nested/'nested.md').write_text('# Nested\n')
        if os.name=='nt':
            import ctypes
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.SetFileAttributesW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32]
            for path,flags in ((hidden,2),(system,4),(both,6),(nested,2)):
                assert kernel.SetFileAttributesW(str(path),flags),ctypes.get_last_error()
        pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
        pfc.Commander._sync_auto_start=lambda *a,**k:True
        pfc.Commander._start_windows_tray=lambda *a:None
        app=pfc.Commander();errors=[]
        app.report_callback_exception=lambda *exc:errors.append(str(exc))
        try:
            app.auto_font_size_var.set(False)
            pane=app.active;pane.navigate(folder);pane.show_hidden=False;pane.show_system=False
            pane.set_quick_filter('not-matching-anything')
            app.search();s=app.search_window;settle(app);s.start()
            settle(app,lambda:s.worker is None)
            def row(path):
                return next(i for i in s.tree.get_children() if s.tree.item(i,'tags')[0]==str(path))
            assert {hidden,system,both,normal,nested,nested/'nested.md'} <= set(s.results)
            assert s.tree.set(row(hidden),'attributes')==pfc.tr('Hidden')
            assert s.tree.set(row(normal),'attributes')==''
            assert s.tree.set(row(system),'attributes')==(pfc.tr('System') if os.name=='nt' else '')
            assert s.tree.set(row(both),'attributes')==pfc.tr('Hidden')+(' · '+pfc.tr('System') if os.name=='nt' else '')
            assert s.tree.set(row(nested/'nested.md'),'attributes')=='', 'Parent attributes are not inherited'
            s.change_sort('attributes');s.change_sort('name')
            for scale,key in (('100','small'),('200','xl')):
                app.font_size_var.set(key);app.apply_font_size(save=False)
                s.geometry('1180x740+10+10');settle(app)
                s.tree.selection_set(row(hidden));s.tree.see(row(hidden));settle(app)
                assert s.tree.column('attributes','width')>=60
                capture(s,scale)
            # Invoke the actual menu command, not just the callback.
            s.results_menu.invoke(0);settle(app)
            assert s.winfo_exists() and pane.path==folder and pane.selected_paths()==[hidden]
            assert not pane.show_hidden and not pane.show_system
            assert pane.quick_filter_var.get()=='not-matching-anything'
            assert both not in pane.selected_paths()
            assert not pane.refresh_if_changed(), 'Temporary reveal caused an unchanged folder to refresh'
            relative=Path(os.path.relpath(hidden))
            assert app.go_to_search_result(relative,pane) and pane.selected_paths()==[hidden]
            # Non-result regions do not navigate or close.
            s.double_click_result(SimpleNamespace(x=5,y=2));assert s.winfo_exists()
            # A deleted result cannot close Search or select an unrelated file.
            normal.unlink();s.tree.selection_set(row(normal))
            with patch.object(pfc.messagebox,'showerror') as notice:
                s.go_selected(close_after=True)
                assert notice.called and s.winfo_exists()
            # Real two-click mouse sequence on a different row, with another
            # stale selection: the clicked row must be the target.
            s.lift();s.tree.see(row(system));settle(app)
            box=s.tree.bbox(row(system));x,y=box[0]+15,box[1]+box[3]//2
            for stamp in (20000,20120):
                s.tree.event_generate('<ButtonPress-1>',x=x,y=y,time=stamp)
                if s.winfo_exists():s.tree.event_generate('<ButtonRelease-1>',x=x,y=y,time=stamp+20)
                settle(app)
            assert not s.winfo_exists(), 'Double-click must close Search'
            assert pane.path==folder and pane.selected_paths()==[system]
            pane.navigate(root);pane.navigate(folder)
            assert not pane.select_path(hidden), 'Temporary reveal leaked across navigation'
            assert not pane.show_hidden and not pane.show_system
            # Locked origin opens another tab and selects in the destination.
            pane.navigate(root);pane.lock_mode='locked';app.set_active(pane)
            app.search();s=app.search_window;settle(app)
            iid=s.tree.insert('','end',text=hidden.name,tags=(str(hidden),))
            s.tree.selection_set(iid);s.go_selected();settle(app)
            assert s.winfo_exists() and app.active is not pane
            assert app.active.path==folder and app.active.selected_paths()==[hidden]
            assert pane.path==root
            assert not errors,errors
            print('PASS: real hidden/system search; notes; 100/200% layout; Go to File retained; mouse double-click closes; missing result retained; locked tab; temporary reveal')
        finally:app.close_app()

if __name__=='__main__':main()
