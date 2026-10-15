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
search=pfc if pfc.__name__=='pfc' else importlib.import_module('pycommander.search')

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
            assert s.advanced.winfo_ismapped(), 'Size/date must not require a Filters toggle'
            assert s.tree.bind('<Button-3>') and s.tree.bind('<Shift-F10>')
            assert all(b.instate(['disabled']) for i,b in enumerate(s.result_buttons) if i!=1)
            s.min_size_var.set('1.5');s.max_size_var.set('2');s.size_unit_var.set('MB')
            assert s.criteria()['min_size']==1.5*1024**2 and s.criteria()['max_size']==2*1024**2
            s.clear_filters()
            # Search hotkeys must not fall through to Commander bind_all and
            # act on the background file list or overwrite the clipboard.
            s.tree.selection_set((row(hidden),row(both)));s.tree.focus_force();settle(app)
            preview,compare=s.on_preview,s.on_compare
            calls=[];s.on_preview=lambda *args:calls.append('preview');s.on_compare=lambda *args:calls.append('compare')
            try:
                with patch.object(app,'_dispatch_global_hotkey') as background:
                    for key in ('<F3>','<F9>','<F11>'):
                        s.tree.event_generate(key);settle(app)
                    assert calls==['preview','compare'] and not background.called
                    assert set(s.clipboard_get().splitlines())=={str(hidden),str(both)}
            finally:s.on_preview,s.on_compare=preview,compare
            for scale,key in (('100','small'),('200','xl')):
                app.font_size_var.set(key);app.apply_font_size(save=False)
                s.geometry('1180x740+10+10');settle(app)
                s.tree.selection_set(row(hidden));s.tree.see(row(hidden));settle(app)
                assert s.tree.column('attributes','width')>=60
                assert all(b.winfo_rootx()+b.winfo_width()<=s.winfo_rootx()+s.winfo_width() for b in s.result_buttons)
                assert s.result_actions.winfo_rooty()>s.status.winfo_rooty()
                assert s.tree.winfo_rooty()>s.result_actions.winfo_rooty()+s.result_actions.winfo_height()-1
                capture(s,scale)
            # Native right-click preserves multi-selection, selects an unrelated
            # clicked result, and ignores headings/blank space. Menu uses the
            # same commands as the visible buttons, including keyboard access.
            s.tree.selection_set((row(hidden),row(both)));s.tree.see(row(hidden));settle(app)
            box=s.tree.bbox(row(hidden));x,y=box[0]+15,box[1]+box[3]//2
            with patch.object(s.results_menu,'tk_popup') as popup:
                s.tree.event_generate('<Button-3>',x=x,y=y);settle(app)
                assert popup.called and len(s.tree.selection())==2
                popup.reset_mock();s.context_menu(SimpleNamespace(x=5,y=2,keysym=''))
                assert not popup.called
                s.tree.selection_set(row(both));s.tree.event_generate('<Button-3>',x=x,y=y);settle(app)
                assert s.selected_paths()==[hidden]
                popup.reset_mock();s.context_menu(SimpleNamespace(keysym='F10'))
                assert popup.called
            # Rename cancellation/collision never changes data. Folder renames
            # must also retarget any already-listed descendants.
            s.tree.selection_set(row(nested));settle(app)
            with patch.object(search.simpledialog,'askstring',return_value=None):s.rename_selected()
            assert nested.exists()
            with patch.object(search.simpledialog,'askstring',return_value=normal.name),patch.object(search.messagebox,'showerror') as notice:
                s.rename_selected();assert notice.called and normal.exists() and nested.exists()
            with patch.object(search.simpledialog,'askstring',return_value='renamed-folder'):s.rename_selected()
            renamed=folder/'renamed-folder'
            assert renamed.exists() and not nested.exists()
            assert renamed/'nested.md' in s.results and s.tree.set(row(renamed/'nested.md'),'folder')==str(renamed)
            s.tree.selection_set(row(hidden));settle(app)
            # Invoke the actual menu command, not just the callback.
            s.results_menu.invoke(0);settle(app)
            assert s.winfo_exists() and pane.path==folder and pane.selected_paths()==[hidden]
            assert not pane.show_hidden and not pane.show_system
            assert pane.quick_filter_var.get()=='not-matching-anything'
            assert both not in pane.selected_paths()
            assert not pane.refresh_if_changed(), 'Temporary reveal caused an unchanged folder to refresh'
            relative=Path(os.path.relpath(hidden))
            assert app.go_to_search_result(relative,pane) and pane.selected_paths()==[hidden]
            pane.set_view_mode('file')
            assert not pane.refresh_if_changed(), 'Changing view mode caused repeated refreshes after locating a hidden result'
            pane.set_view_mode('list')
            assert app.go_to_search_result(hidden,pane)
            # Non-result regions do not navigate or close.
            s.double_click_result(SimpleNamespace(x=5,y=2));assert s.winfo_exists()
            # A deleted result cannot close Search or select an unrelated file.
            normal.unlink();s.tree.selection_set(row(normal))
            with patch.object(pfc.messagebox,'showerror') as notice:
                s.go_selected(close_after=True)
                assert notice.called and s.winfo_exists()
            # Real two-click mouse sequence on a different row, with another
            # stale selection: the clicked row must be the target.
            s.lift();s.tree.see(row(system));s.tree.yview_moveto(1);settle(app)
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
