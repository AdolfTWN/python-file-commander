"""Populated laptop startup, zoom recovery and large-to-small display transition."""
import importlib
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')


def settle(app, seconds=.5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        time.sleep(.01)


def contained(widget, parent):
    return (widget.winfo_ismapped() and widget.winfo_width() > 5 and
            widget.winfo_height() > 5 and
            widget.winfo_rootx() >= parent.winfo_rootx() and
            widget.winfo_rooty() >= parent.winfo_rooty() and
            widget.winfo_rootx()+widget.winfo_width() <= parent.winfo_rootx()+parent.winfo_width()+1 and
            widget.winfo_rooty()+widget.winfo_height() <= parent.winfo_rooty()+parent.winfo_height()+1)


def usable(app):
    assert contained(app.actions_frame, app), 'Bottom action bar lost below client area'
    assert contained(app.zoom_combo, app), 'Zoom recovery control is inaccessible'
    for button, key, _ in app.action_buttons:
        assert contained(button, app.actions_frame), ('Shortcut clipped', key)
    for pane in app.visible_panes():
        assert contained(pane.quick_filter_entry, pane), 'Quick Filter clipped'
        assert pane.tree.winfo_height() >= 80, 'No usable file viewport'
        assert pane.tree.column('#0', 'width') >= 190, 'Filename crushed by detail columns'


def capture(app, name):
    if os.name == 'nt':
        from folder_native_test_support import capture_window
        capture_window(app, Path(__file__).parent / ('evidence-laptop-'+name+'.bmp'))
    else:
        from PIL import ImageGrab
        x, y = app.winfo_rootx(), app.winfo_rooty()
        prefix = '/tmp/pfc-laptop-before-' if '--expect-old-failure' in sys.argv else '/tmp/pfc-laptop-'
        ImageGrab.grab((x, y, x+app.winfo_width(), y+app.winfo_height())).save(prefix+name+'.png')


if '--restart' in sys.argv:
    directory = Path(sys.argv[sys.argv.index('--restart')+1])
    pfc.Commander._find_ini_path = staticmethod(lambda: directory / 'pfc.ini')
    pfc.Commander._sync_auto_start = lambda *a, **k: True
    pfc.Commander._start_windows_tray = lambda *a: None
    if os.name == 'nt':
        placement = pfc if pfc.__name__ == 'pfc' else importlib.import_module('pycommander.windowplacement')
        original_snapshot = placement.WindowsWindowPlacement.snapshot
        def small_screen(self):
            state = original_snapshot(self)
            return (state[0], ((0, 0, 1280, 720),), state[2]) if state else None
        placement.WindowsWindowPlacement.snapshot = small_screen
    app = pfc.Commander()
    try:
        settle(app, 2.7)
        assert app.zoom_percent_var.get() == '150%'
        limit = (1280, 720) if os.name == 'nt' else (app.winfo_screenwidth(), app.winfo_screenheight())
        assert app.winfo_width() <= limit[0] and app.winfo_height() <= limit[1], app.geometry()
        usable(app)
        print('PASS: new process restores enlarged saved geometry on smaller work area')
    finally:
        app.close_app()
    sys.exit(0)


with tempfile.TemporaryDirectory(prefix='pfc-laptop-') as raw:
    directory = Path(raw)
    for n in range(40):
        (directory / f'Engineering report {n:02} release.xlsx').write_bytes(b'fixture')
    ini = directory / 'pfc.ini'
    ini.write_text('[window]\ngeometry=1800x1050+0+0\n[view]\nfont_size=xl\nauto_font_size=false\n', encoding='utf-8')
    pfc.Commander._find_ini_path = staticmethod(lambda: ini)
    pfc.Commander._sync_auto_start = lambda *a, **k: True
    pfc.Commander._start_windows_tray = lambda *a: None
    app = pfc.Commander()
    errors = []
    observed_old_failure = False
    app.report_callback_exception = lambda *exc: errors.append(str(exc))
    try:
        for pane in app.visible_panes(): pane.navigate(directory)
        # Exact client size: unlike screenshots of empty/default-size windows,
        # this must retain the recovery control at the owner's laptop scale.
        app.geometry('1260x650+0+0')
        app.font_size_var.set('xl'); app.select_manual_font_size()
        settle(app)
        capture(app, '200')
        usable(app)
        app.zoom_minus.invoke(); app.zoom_minus.invoke(); settle(app)
        assert app.zoom_percent_var.get() == '150%'
        usable(app); capture(app, '150')
        for level in ('medium', '175', 'xl', 'large'):
            app.font_size_var.set(level); app.select_manual_font_size(); settle(app)
            usable(app)
        # Use a real native frame and simulated work-area reporting only. Do not
        # change the shared VM display or reboot Windows under other tasks.
        guard = app._window_visibility
        if os.name == 'nt':
            app.state('zoomed'); settle(app)
            guard.recover(); settle(app)
            assert app.state() == 'zoomed', 'Recovery must preserve valid maximization'
            app.state('normal'); settle(app)
            app.iconify(); settle(app, 1.3)
            assert app.state() == 'iconic', 'Recovery must preserve intentional minimization'
            app.deiconify(); settle(app)
            usable(app)
            original = guard.backend.snapshot
            area = [(0, 0, 1920, 1080)]
            def snapshot():
                state = original()
                return (state[0], tuple(area), state[2]) if state else None
            guard.backend.snapshot = snapshot
            app.geometry('1800x950+0+0'); settle(app)
            guard.recover(); settle(app)
            area[:] = [(0, 0, 1280, 720)]
            settle(app, 2.6)
            rect, _, margin = snapshot()
            assert rect[2] <= 1280+margin and rect[3] <= 720+margin, rect
            usable(app)
            # Restart restoration uses saved large geometry on a small display.
            app.geometry('1800x1050+0+0'); settle(app)
            guard.work_areas = None; guard.previous = None
            settle(app, 2.6)
            rect, _, margin = snapshot()
            assert rect[2] <= 1280+margin and rect[3] <= 720+margin, rect
            usable(app)
        geometry = app.geometry()
        settle(app, 1.2)
        assert app.geometry() == geometry, 'Layout keeps moving after recovery'
        assert not errors, errors
        print('PASS: populated laptop 200/150%, visible zoom/actions/filter, display shrink and stable recovery')
        # Save a large-display geometry, then actually relaunch the application
        # in a new Python process (no host/guest reboot or startup-task changes).
        app.geometry('1800x1050+0+0'); app.update_idletasks(); app.save_config()
    except AssertionError as exc:
        if '--expect-old-failure' not in sys.argv or str(exc) != 'Bottom action bar lost below client area': raise
        observed_old_failure = True
        print('PASS negative control: released portable reproduces missing bottom controls')
    finally:
        app.close_app()
    if '--expect-old-failure' in sys.argv:
        assert observed_old_failure, 'Negative control did not reproduce the released defect'
    else:
        subprocess.run([sys.executable, __file__, pfc.__name__, '--restart', str(directory)], check=True)
