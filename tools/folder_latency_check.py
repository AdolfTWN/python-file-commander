"""Exercise an actual Tk folder switch with controlled I/O delays and no private files."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'pycommander.app')


def until(predicate, pump=None, timeout=9):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        if pump is not None:
            pump()
        result = predicate()
        if result:
            return result
        time.sleep(.02)
    raise AssertionError('Timed out waiting for diagnostic evidence')


def widgets(parent, cls):
    for widget in parent.winfo_children():
        if isinstance(widget, cls):
            yield widget
        yield from widgets(widget, cls)


with tempfile.TemporaryDirectory() as raw:
    root = Path(raw)
    fast, repeated, blocked = [root/name for name in ('fast', 'repeated', 'PRIVATE_FOLDER_MARKER')]
    for folder in (fast, repeated, blocked):
        folder.mkdir()
    (fast/'fast.txt').write_text('fast', encoding='utf-8')
    slow_file = blocked/'PRIVATE_FILENAME_MARKER.lnk'
    slow_file.write_text('synthetic; not a real shortcut', encoding='utf-8')
    for i in range(5):
        (repeated/f'PRIVATE_{i}.json').write_text('{}', encoding='utf-8')
    pfc.Commander._find_ini_path = staticmethod(lambda: root/'pfc.ini')
    pfc.Commander._sync_auto_start = lambda self, **kwargs: True
    original_init = pfc.DiagnosticLog.__init__

    def isolated_log(log, version, **kwargs):
        original_init(log, version, directory=root/'logs', **kwargs)

    with patch.object(pfc.DiagnosticLog, '__init__', isolated_log):
        app = pfc.Commander()
    monitor = app._ui_latency
    try:
        app.config_data.set('refresh', 'auto_refresh', 'false')
        app.vcs_overlay_var.set(False)
        app.onedrive_overlay_var.set(False)
        app.auto_font_size_var.set(False)
        app.update()
        pane = app.panes()[0]
        data=sys.modules[pfc.DirectoryReads.__module__]
        original_stat = data._listing_stat
        original_icon = type(pane.icons)._load
        original_get = pane.icons.get
        seen_pending = []

        def records():
            return [r for r in pfc.diagnostic_records(app.debug_log.snapshot(automatic=True))
                    if r['event'].startswith('ui.')]

        def find(event, phase=None):
            return next((r for r in records() if r['event']==event and (
                phase is None or r['latency'].get('pending_phase')==phase)), None)

        def stall(phase):
            row = until(lambda: find('ui.stall.detected', phase), timeout=9)
            assert not any(r['incident']==row['incident'] and r['event']=='ui.operation.slow'
                           for r in records()), 'Watchdog must write before the blocked function returns'
            seen_pending.append(row)

        def controlled_stat(path, *args, **kwargs):
            if path.parent == repeated and path.suffix == '.json':
                time.sleep(.115)
            return original_stat(path, *args, **kwargs)

        def controlled_get(path, is_dir, *args, **kwargs):
            if path == slow_file and os.name != 'nt' and not seen_pending:
                app._ui_latency.measure('Synthetic UI callback',
                                       lambda:stall('Synthetic UI callback'),item=path)
            return original_get(path,is_dir,*args,**kwargs)

        def controlled_icon(provider, path, is_dir):
            if path == slow_file and not seen_pending:
                stall('Load Windows Shell icon')
                return None  # Use PFC's real fallback, not a broken native shortcut.
            return original_icon(provider, path, is_dir)

        assert pane.navigate(fast)
        app.update()
        assert not records()
        with patch.object(data, '_listing_stat', controlled_stat):
            assert pane.navigate(repeated)
        slow = until(lambda: find('ui.operation.slow'), app.update)
        phase = next(p for p in slow['latency']['phases'] if p['phase']=='Read file metadata')
        assert phase['slow_calls'] == 5 and phase['file_type'] == '.json', phase
        assert slow['latency']['rows'] == 5
        assert not find('ui.stall.detected')

        app._ui_latency.heartbeat()
        with patch.object(data, '_listing_stat', controlled_stat), patch.object(type(pane.icons), '_load', controlled_icon), patch.object(pane.icons,'get',controlled_get):
            assert pane.navigate(blocked)
        assert len(seen_pending)==1 and seen_pending[0]['latency']['stalled_ms'] >= 5000
        incident = seen_pending[0]['incident']
        until(lambda: find('ui.stall.recovered'), app.update)

        def combined():
            return next((r for r in pfc.diagnostic_incidents(app.debug_log.snapshot(automatic=True))
                         if r.get('incident')==incident and 'duration_ms' in r['latency']), None)

        row = until(combined, app.update)
        assert row['latency']['action']=='Open folder'
        assert row['latency']['pending_type']=='.lnk'
        assert row['latency']['rows']==1 and row['version']==pfc.__version__
        assert 'PRIVATE_' not in repr(records()), 'Private marker leaked into automatic diagnostics'
        assert all('context' not in r for r in records())
        assert row['latency']['resumed_ms'] >= 5000
        app.font_size_var.set('large')
        app.apply_font_size(save=False)
        app.show_debug_log()
        app.update()
        dialog = next(w for w in app.winfo_children() if isinstance(w, tk.Toplevel)
                      and w.title()==pfc.tr('Error / Warning log'))
        table = next(widgets(dialog, ttk.Treeview))
        iid = next(i for i in table.get_children() if table.set(i, 'event')=='ui.stall.detected')
        table.selection_set(iid)
        app.update()
        details = next(widgets(dialog, tk.Text))
        summary = details.get('1.0','end-1c')
        for expected in ('Action: Open folder', 'Waiting at capture:', 'Operation finished:',
                         'UI responded again', '.lnk'):
            assert expected in summary, summary
        assert details.bbox('5.0') is not None
        dialog.lift()
        app.update()
        if os.name=='nt':
            from folder_native_test_support import capture_window
            capture_window(dialog, Path(__file__).parent/'evidence-folder-latency.bmp')
        elif os.environ.get('PFC_LATENCY_SCREENSHOT'):
            from PIL import ImageGrab
            x,y = dialog.winfo_rootx(), dialog.winfo_rooty()
            ImageGrab.grab((x,y,x+dialog.winfo_width(),y+dialog.winfo_height())).save(
                os.environ['PFC_LATENCY_SCREENSHOT'])
        print('PASS: background warning on live folder stall, slow-batch timing, one recovery incident, private metadata only, 150% photo summary')
    finally:
        app.destroy()
        monitor._thread.join(2)
        assert not monitor._thread.is_alive()
