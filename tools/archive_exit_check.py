"""Regression: one parent click must work even when temp cleanup is denied."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'pycommander.app')

def pump(app, condition=lambda: True):
    end = time.monotonic() + 10
    while time.monotonic() < end:
        app.update()
        if condition(): return
        time.sleep(.02)
    raise AssertionError('Timed out')

def main():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw).resolve()
        pfc.Commander._find_ini_path = staticmethod(lambda: root / 'pfc.ini')
        pfc.Commander._sync_auto_start = lambda self, **kw: True
        app = pfc.Commander()
        errors = []
        app.report_callback_exception = lambda *exc: errors.append(str(exc))
        held = None
        session = None
        try:
            pane = app.left_tabs.current()
            pane.navigate(root)
            archive = root / 'project.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('project/file.txt', 'disposable fixture')
            app._open_special_file(pane, archive)
            pump(app, lambda: pane not in app._archive_open_jobs)
            session = pane.archive_session
            assert session is not None
            workspace = session.root
            real_close = session.close
            if os.name == 'nt':
                # Windows denies unlinking a file opened without delete sharing.
                held = (workspace / 'project' / 'file.txt').open('rb')
                mode = 'real Windows open-file handle'
            else:
                def denied():
                    raise PermissionError('simulated Windows sharing violation')
                session.close = denied
                mode = 'injected cleanup PermissionError'
            up = next(w for frame in pane.winfo_children() for w in frame.winfo_children()
                      if isinstance(w, pfc.ttk.Button) and w.cget('text') == '↑')
            up.invoke(); pump(app)
            print(json.dumps({'mode':mode,'after_one_click':str(pane.path),
                              'expected':str(root),'session_cleared':pane.archive_session is None,
                              'callback_errors':errors}))
            if '--expect-bug' in sys.argv:
                assert pane.path == workspace and pane.archive_session is None
                up.invoke(); pump(app)
                assert pane.path == workspace.parent
                print('REPRODUCED: first click stuck; second click enters Temp')
                return
            assert pane.path == root, 'First parent click did not leave archive'
            assert pane.selected_paths() == [archive]
            assert not errors, errors
            assert session in app._archive_sessions, 'Failed cleanup must stay tracked'
            if held:
                held.close(); held = None
            else:
                session.close = real_close
            pump(app, lambda: not workspace.exists())
            assert session not in app._archive_sessions
            app._open_special_file(pane, archive)
            pump(app, lambda: pane not in app._archive_open_jobs)
            session = pane.archive_session
            real_close = session.close
            pane.navigate(session.root / 'project')
            up.invoke(); pump(app)
            assert pane.path == session.root, 'Nested Up must remain inside archive'
            real_navigate = pane.navigate
            pane.navigate = lambda *args, **kwargs: False
            try:
                up.invoke(); pump(app)
                assert pane.archive_session is session and pane.path == session.root
            finally:
                pane.navigate = real_navigate
            up.invoke(); pump(app)
            assert pane.path == root and pane.selected_paths() == [archive]
            assert not errors, errors
            print('PASS: one parent click, ZIP selection, no callback error, deferred cleanup succeeds')
        finally:
            if held: held.close()
            if session is not None: session.close = real_close
            app.close_app()
            if session is not None: real_close()

if __name__ == '__main__':
    main()
