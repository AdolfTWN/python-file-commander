"""Verify path entry locates files and folder changes start at the top."""
import importlib
from pathlib import Path
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
module = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'pycommander.app')

def settle(app):
    end = time.monotonic() + .35
    while time.monotonic() < end:
        app.update()
        time.sleep(.01)

def main():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw).resolve()
        module.Commander._find_ini_path = staticmethod(lambda: root / 'pfc.ini')
        module.Commander._sync_auto_start = lambda self, **kwargs: True
        app = module.Commander()
        errors = []
        app.report_callback_exception = lambda *exc: errors.append(str(exc))
        try:
            app.geometry('960x600'); settle(app)
            pane = app.left_tabs.current()
            folders = [root / 'A', root / 'B']
            for folder in folders:
                folder.mkdir()
                for i in range(150):
                    (folder / f'{i:03d}.txt').write_text('fixture')
            opened = []
            pane.on_open_file = lambda *args: opened.append(args) or True
            pane.navigate(folders[0]); settle(app)
            pane.select_path(folders[0] / '149.txt'); settle(app)
            pane.navigate(folders[1]); settle(app)
            pane.select_path(folders[1] / '149.txt'); settle(app)
            pane.navigate(folders[0]); settle(app)
            assert pane.selected_paths() == [folders[0] / '000.txt'], pane.selected_paths()
            assert pane.tree.yview()[0] == 0, pane.tree.yview()
            pane.select_path(folders[0] / '100.txt'); settle(app)
            before = pane.tree.yview()
            pane.refresh(); settle(app)
            assert pane.selected_paths() == [folders[0] / '100.txt']
            assert pane.tree.yview() == before
            pane.set_quick_filter('000'); settle(app)
            target = folders[1] / '149.txt'
            pane.path_bar.begin_edit()
            pane.path_var.set('"' + str(target) + '"')
            pane.path_entry.focus_force(); settle(app)
            pane.path_entry.event_generate('<Return>'); settle(app)
            assert pane.path == target.parent
            assert pane.selected_paths() == [target], pane.selected_paths()
            assert pane.tree.bbox(pane.tree.focus()), 'Target must be visible'
            assert not opened, 'Path entry must never execute a file'
            pane.lock_mode = 'locked'
            locked_path = pane.path
            pane.path_bar.begin_edit()
            pane.path_var.set(str(folders[0] / '149.txt'))
            pane.path_entry.focus_force(); settle(app)
            pane.path_entry.event_generate('<Return>'); settle(app)
            assert pane.path == locked_path
            assert app.active is not pane
            assert app.active.selected_paths() == [folders[0] / '149.txt']
            pane.lock_mode = 'normal'
            app.left_tabs.select(pane)
            app.set_active(pane)
            archive = root / 'test.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('folder/file.txt', 'fixture')
            app._open_special_file(pane, archive)
            deadline = time.monotonic() + 10
            while pane in app._archive_open_jobs and time.monotonic() < deadline:
                settle(app)
            assert pane.archive_session is not None
            pane.path_bar.begin_edit()
            pane.path_var.set(str(archive / 'folder' / 'file.txt'))
            pane.path_entry.focus_force(); settle(app)
            pane.path_entry.event_generate('<Return>'); settle(app)
            assert pane.selected_paths() == [pane.archive_session.root / 'folder' / 'file.txt']
            assert not opened and not errors, (opened, errors)
            print('PASS: top row, scroll reset, refresh preservation, filtered file path, archive file path')
        finally:
            app.close_app()

if __name__ == '__main__':
    main()
