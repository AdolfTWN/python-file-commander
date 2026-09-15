"""Exercise real breadcrumb/edit/menu events in package and portable editions."""
import importlib
from pathlib import Path, PureWindowsPath
import sys
import tempfile
import time
import zipfile
import os
import threading
import ctypes

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
module = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'pycommander.app')


def settle(app):
    end = time.monotonic() + .15
    while time.monotonic() < end:
        app.update()
        time.sleep(.01)


def click_crumb(app, bar, index):
    left, right, _ = next(r for r in bar._regions if r[2] == index)
    bar.canvas.event_generate('<Button-1>', x=int((left + right) / 2), y=10)
    settle(app)


def native_menu_keys(keys):
    """Windows TrackPopupMenu blocks Tk timers; use real OS keyboard events."""
    def send():
        time.sleep(.4)
        for key in keys:
            ctypes.windll.user32.keybd_event(key, 0, 0, 0)
            ctypes.windll.user32.keybd_event(key, 0, 2, 0)
            time.sleep(.05)
    threading.Thread(target=send, daemon=True).start()


def main():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw).resolve()
        folder = root / 'Projects' / '中文工作目錄' / 'Documents'
        folder.mkdir(parents=True)
        target = folder / 'target.txt'
        target.write_text('fixture')
        (folder / 'subfolder').mkdir()
        module.Commander._find_ini_path = staticmethod(lambda: root / 'pfc.ini')
        module.Commander._sync_auto_start = lambda self, **kwargs: True
        app = module.Commander()
        errors = []
        app.report_callback_exception = lambda *exc: errors.append(str(exc))
        try:
            app.auto_font_size_var.set(False); app.set_auto_font_size()
            app.geometry('1100x700'); settle(app)
            pane = app.left_tabs.current()
            app.set_active(pane)
            pane.navigate(folder); settle(app)
            bar = pane.path_bar
            assert bar._parts[-1] == ('Documents', folder)
            assert bar._regions[-1][2] == len(bar._parts) - 1
            assert not pane.path_entry.winfo_ismapped()
            def choose_ancestor():
                menu = bar._overflow_menu
                assert menu.winfo_ismapped()
                menu.invoke(menu.index('end')); menu.unpost()
            if os.name == 'nt':
                native_menu_keys([0x1B])  # Leave the native modal loop before invoking.
            else:
                app.after(100, choose_ancestor)
            click_crumb(app, bar, None); settle(app)
            if os.name == 'nt':
                bar._overflow_menu.invoke(bar._overflow_menu.index('end')); settle(app)
            assert pane.path in folder.parents
            pane.navigate(folder); settle(app)
            for key in ('<Control-l>', '<F12>'):
                pane.tree.focus_force(); settle(app)
                pane.tree.event_generate(key); settle(app)
                assert bar.editing and pane.path_entry.selection_present()
                pane.path_var.set('unsubmitted')
                pane.path_entry.event_generate('<Escape>'); settle(app)
                assert not bar.editing and pane.path_var.get() == str(folder)
            bar.edit_button.invoke(); settle(app)
            pane.path_var.set('unsubmitted')
            pane.tree.focus_force(); settle(app)
            assert not bar.editing and pane.path_var.get() == str(folder)
            bar.begin_edit(); pane.path_var.set('unsubmitted')
            pane.up_button.invoke(); settle(app)
            assert not bar.editing and bar.committed == str(folder.parent)
            pane.navigate(folder); settle(app)
            bar.begin_edit(); settle(app)
            invalid = str(root / 'missing')
            pane.path_var.set(invalid)
            old_error = module.messagebox.showerror
            module.messagebox.showerror = lambda *args: None
            try:
                pane.path_entry.event_generate('<Return>'); settle(app)
            finally:
                module.messagebox.showerror = old_error
            assert bar.editing and pane.path_var.get() == invalid and pane.path == folder
            pane.path_var.set(str(target)); pane.path_entry.event_generate('<Return>'); settle(app)
            assert not bar.editing and pane.selected_paths() == [target]
            other_mode = app.right_tabs.current().view_mode
            for index, mode in ((1, 'folder'), (2, 'file'), (0, 'list')):
                def choose_mode(i=index):
                    assert pane._view_mode_menu.winfo_ismapped()
                    pane._view_mode_menu.invoke(i); pane._view_mode_menu.unpost()
                if os.name == 'nt':
                    native_menu_keys([0x1B])
                else:
                    app.after(100, choose_mode)
                pane.view_mode_button.invoke(); settle(app)
                if os.name == 'nt':
                    pane._view_mode_menu.invoke(index); settle(app)
                assert pane.view_mode == mode and app.right_tabs.current().view_mode == other_mode
            pane.path_var.set('[Search Results]'); settle(app)
            assert bar._parts == [('[Search Results]', None)]
            pane.navigate(folder)
            archive = folder / 'example.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('inside/deep/test.txt', 'fixture')
            app._open_special_file(pane, archive)
            deadline = time.monotonic() + 15
            while pane in app._archive_open_jobs and time.monotonic() < deadline:
                settle(app)
            session = pane.archive_session
            assert session is not None
            pane.navigate(session.root / 'inside' / 'deep'); settle(app)
            assert 'pfc-archive-' not in bar.committed
            pane.navigate(session.root); settle(app)
            # The original containing folder is directly clickable at ZIP root.
            click_crumb(app, bar, len(bar._parts) - 2)
            assert pane.path == folder and pane.archive_session is None
            pane.lock_mode = 'locked'
            pane._navigate_crumb(folder.parent); settle(app)
            assert pane.path == folder and app.active.path == folder.parent
            pane.lock_mode = 'unlocked'
            app.left_tabs.select(pane); app.set_active(pane)
            for scheme in ('light', 'light_grey', 'dark'):
                app.color_scheme_var.set(scheme); app.apply_color_scheme(save=False)
                for scale in ('small', '175', '300'):
                    app.font_size_var.set(scale); app.apply_font_size(save=False)
                    for width in (960, 1600):
                        app.geometry(f'{width}x800'); settle(app)
                        assert bar.canvas.winfo_width() > 30
                        assert bar._regions[-1][2] == len(bar._parts) - 1
                        assert bar.winfo_rootx() + bar.winfo_width() <= pane.view_mode_button.winfo_rootx()
                        assert bar.canvas.cget('background') == app.palette['entry']
            app.font_size_var.set('small'); app.apply_font_size(save=False)
            app.panel_count_var.set(4); app.apply_panel_count(save=False)
            app.geometry('1600x800'); settle(app)
            for scale in ('small', '175', '300'):
                app.font_size_var.set(scale); app.apply_font_size(save=False); settle(app)
                assert bar.canvas.winfo_width() > 30
                assert bar._regions[-1][2] == len(bar._parts) - 1
            app.panel_count_var.set(2); app.apply_panel_count(save=False)
            app.font_size_var.set('small'); app.apply_font_size(save=False)
            app.color_scheme_var.set('light'); app.apply_color_scheme(save=False)
            app.geometry('1100x700'); settle(app)
            if '--screenshot' in sys.argv:
                from PIL import ImageGrab
                ImageGrab.grab().save('/tmp/pfc-pathbar-layout.png')
            assert not errors, errors
            print('PASS: breadcrumb clicks/overflow, Ctrl+L/F12, edit cancel/error/file, view menu, ZIP exit, locked tabs, themes/zoom/layout')
            if '--interactive' in sys.argv:
                print('READY: interactive review', flush=True)
                app.mainloop()
        finally:
            try:
                if app.winfo_exists():
                    app.close_app()
            except module.tk.TclError:
                pass  # Interactive review may already have destroyed the root.


if __name__ == '__main__':
    main()
