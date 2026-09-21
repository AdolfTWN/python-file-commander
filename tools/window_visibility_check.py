"""Main-window offscreen startup and live recovery; runs on Linux or Windows."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'pycommander.app')


def settle(app, seconds=2.5):
    until = time.monotonic()+seconds
    while time.monotonic() < until:
        app.update()
        time.sleep(.02)


with tempfile.TemporaryDirectory(prefix='pfc-window-') as raw:
    ini = Path(raw)/'pfc.ini'
    ini.write_text('[window]\ngeometry = 1000x650+5000+100\n', encoding='utf-8')
    pfc.Commander._find_ini_path = staticmethod(lambda: ini)
    pfc.Commander._sync_auto_start = lambda self, **kw: True
    pfc.Commander._start_windows_tray = lambda self: None
    app = pfc.Commander()
    errors = []
    app.report_callback_exception = lambda *exc: errors.append(str(exc))
    try:
        settle(app, 3)
        assert 0 <= app.winfo_rootx() < app.winfo_screenwidth(), app.geometry()
        assert 0 <= app.winfo_rooty() < app.winfo_screenheight(), app.geometry()
        # Native SetWindowPos recreates Windows leaving the frame on a removed
        # display. This exercises the production timer, not a direct check call.
        backend = app._window_visibility.backend
        if os.name == 'nt':
            backend.move((5000, 100, 1000, 650))
        else:
            app.geometry('1000x650+5000+100')
        settle(app, .15)
        assert app.winfo_rootx() > app.winfo_screenwidth(), 'Fixture must be genuinely offscreen'
        settle(app, 3)
        assert 0 <= app.winfo_rootx() < app.winfo_screenwidth(), app.geometry()
        assert 0 <= app.winfo_rooty() < app.winfo_screenheight(), app.geometry()
        before = (app.winfo_rootx(), app.winfo_rooty())
        settle(app)
        assert (app.winfo_rootx(), app.winfo_rooty()) == before, 'Visible placement must not oscillate'
        if os.name == 'nt':
            app.state('zoomed'); settle(app)
            assert app.state() == 'zoomed', 'Valid maximized window must stay maximized'
            app.state('normal'); settle(app, .2)
            backend.move((-5000, -500, 1000, 650)); settle(app, 3)
            assert 0 <= app.winfo_rootx() < app.winfo_screenwidth(), app.geometry()
            app.iconify(); settle(app)
            assert app.state() == 'iconic', 'Do not reopen an intentionally minimized app'
            app.deiconify(); settle(app)
        app.save_config()
        assert '+5000' not in ini.read_text(encoding='utf-8'), 'Corrected position must be persisted'
        assert not errors, errors
        print('PASS: offscreen INI startup, live offscreen recovery, stable visible placement, saved geometry', flush=True)
    finally:
        app.close_app()
