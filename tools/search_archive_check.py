"""GUI regressions for fresh searches and archive-aware parent navigation."""
import importlib
from pathlib import Path
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'pycommander.app')

def settle(app, condition=lambda: True):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        app.update()
        if condition():
            return
        time.sleep(.01)
    raise AssertionError('GUI operation timed out')

def main():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw).resolve()
        pfc.Commander._find_ini_path = staticmethod(lambda: root / 'pfc.ini')
        pfc.Commander._sync_auto_start = lambda self, **kwargs: True
        app = pfc.Commander()
        errors = []
        app.report_callback_exception = lambda *args: errors.append(str(args))
        try:
            source = app.left_tabs.current()
            source.navigate(root)
            app.set_active(source)
            archive = root / 'sample.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('folder/item.txt', 'test')
            app._open_special_file(source, archive)
            settle(app, lambda: source not in app._archive_open_jobs)
            original_session = source.archive_session
            assert original_session is not None
            app._open_folder_in_new_tab(source, original_session.root / 'folder')
            target = app.active
            settle(app, lambda: target not in app._archive_open_jobs)
            assert target.archive_session is not None, 'Archive folder tab lost its session'
            target.up(); target.up()
            assert target.path == root, (target.path, root)
            assert archive in target.selected_paths()
            assert source.archive_session is original_session and original_session.root.exists()
            app.set_active(source)
            source.lock_mode = 'locked'
            source.navigate(original_session.root / 'folder')
            locked_target = app.active
            settle(app, lambda: locked_target not in app._archive_open_jobs)
            assert locked_target is not source and locked_target.archive_session is not None
            locked_target.up(); locked_target.up()
            assert locked_target.path == root
            source.lock_mode = 'normal'
            source.up()
            assert source.path == root and source.archive_session is None
            app.set_active(source)
            app.config_data.add_section('search') if not app.config_data.has_section('search') else None
            app.config_data.set('search', 'mask', '*.old')
            app.config_data.set('search', 'content', 'old text')
            app.search(); settle(app)
            s = app.search_window
            assert s.mask_var.get() == '' and s.content_var.get() == ''
            s.mask_var.set('*.txt'); s.content_var.set('old query')
            s.min_size_var.set('123')
            s.tree.insert('', 'end', text='stale result')
            app.search(); settle(app)
            assert s.mask_var.get() == '' and s.content_var.get() == ''
            assert s.min_size_var.get() == '' and not s.tree.get_children()
            assert s.path_var.get() == str(root)
            s.start(); app.search()
            settle(app, lambda: not s.worker or not s.worker.is_alive())
            settle(app)
            assert not s.results and not s.tree.get_children()
            s.close(); app.search(); settle(app)
            assert app.search_window.mask_var.get() == ''
            assert not errors, errors
            print('PASS: archive child tabs, locked tabs, parent selection, fresh/reused/running searches')
        finally:
            app.close_app()

if __name__ == '__main__':
    main()
