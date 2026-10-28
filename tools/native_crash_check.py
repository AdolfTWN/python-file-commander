"""Native failure only in a disposable child; restart, recover and view the card.

No parent/GUI/VM is crashed. Windows suppresses only the child's OS error dialog.
"""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if '--crash-child' in sys.argv or '--live-child' in sys.argv:
    _, module_name, _, directory = sys.argv
    pfc = importlib.import_module(module_name)
    import faulthandler
    faulthandler.disable()  # isolated child owns its handler, even under -X faulthandler
    if os.name == 'nt':
        import ctypes
        ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    else:
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    log = pfc.DiagnosticLog('0.18.crash-fixture', directory, automatic=True)
    log.install_hooks()
    assert log._native_capture.enabled
    if '--live-child' in sys.argv:
        (Path(directory)/'ready').touch()
        sys.stdin.readline()
        log.close()
        raise SystemExit(0)
    if os.name == 'nt':
        # ctypes on the Python thread translates SEH into OSError. A disposable
        # native thread's invalid entry point gives a real unhandled AV instead.
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateThread.restype = ctypes.c_void_p
        kernel.CreateThread.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
                                       ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p]
        # Aligned PC in Windows' reserved lowest 64 KiB. Address 1 instead
        # triggers instruction-misalignment on ARM64, not an access violation.
        assert kernel.CreateThread(None, 0, ctypes.c_void_p(0x10), None, 0, None)
        time.sleep(10)
        raise AssertionError('Native child failed to terminate')
    os.abort()

module_name = sys.argv[1] if len(sys.argv) > 1 else 'pycommander.app'
pfc = importlib.import_module(module_name)
with tempfile.TemporaryDirectory() as raw:
    directory = Path(raw) / 'logs'
    live = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), module_name,
                             '--live-child', str(directory)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic()+15
        while not (directory/'ready').exists() and live.poll() is None and time.monotonic()<deadline:
            time.sleep(.02)
        assert (directory/'ready').exists(), 'Live child did not initialize'
        live_journals = list(directory.glob('pfc-native-*.log'))
        observer = pfc.DiagnosticLog('observer', directory, automatic=True)
        try:
            observer.install_hooks()
            assert all(path.exists() for path in live_journals), 'Live journal was consumed'
            assert 'process.native_crash' not in observer.snapshot(automatic=True)
        finally:
            observer.close()
        live.communicate(input=b'\n', timeout=10)
        assert live.returncode == 0
        assert not list(directory.glob('pfc-native-*.log')), 'Clean child left a journal'
    finally:
        if live.poll() is None:
            live.kill(); live.communicate(timeout=10)
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), module_name,
                             '--crash-child', str(directory)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
    if os.name == 'nt':
        assert result.returncode & 0xffffffff == 0xC0000005, hex(result.returncode & 0xffffffff)
    else:
        import signal
        assert result.returncode == -signal.SIGABRT, (result.returncode, result.stderr[-300:])
    journals = list(directory.glob('pfc-native-*.log'))
    assert len(journals) == 1 and journals[0].stat().st_size > 100
    # Next app launch, without any Debug/Verbose switch.
    ini = Path(raw) / 'pfc.ini'
    with patch.object(pfc.Commander, '_find_ini_path', return_value=ini), \
         patch.object(pfc.Commander, '_sync_auto_start'), \
         patch.object(pfc.Commander, '_start_windows_tray'):
        app = pfc.Commander()
    app.debug_log.close()
    app.debug_log = pfc.DiagnosticLog(pfc.__version__, directory, automatic=True,
                                    runtime={'tk': 'Tk ' + str(app.tk.call('package', 'provide', 'Tk'))})
    try:
        app.debug_log.install_hooks()
        rows = [r for r in pfc.diagnostic_records(app.debug_log.snapshot(automatic=True))
                if r['event'] == 'process.native_crash']
        assert len(rows) == 1, rows
        row = rows[0]
        assert row['version'] == '0.18.crash-fixture', row
        assert row['severity'] == 'CRITICAL' and row['time'] and row['utc_time']
        assert row['runtime']['python'] and row['runtime']['machine']
        assert raw not in json.dumps(row)
        if os.name == 'nt':
            assert row['native_code'] == '0xC0000005', row
        assert not journals[0].exists(), 'Recovery must consume the journal'
        app.show_debug_log(); app.update()
        windows = [w for w in app.winfo_children() if isinstance(w, pfc.tk.Toplevel)]
        win = windows[-1]
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        table = next(w for w in descendants(win) if isinstance(w, pfc.ttk.Treeview))
        iid = next(i for i in table.get_children() if table.item(i, 'values')[-1] == 'process.native_crash')
        table.selection_set(iid); table.event_generate('<<TreeviewSelect>>'); app.update()
        text = next(w for w in descendants(win) if isinstance(w, pfc.tk.Text))
        card = text.get('1.0', 'end')
        assert '0.18.crash-fixture' in card and 'Runtime:' in card
        assert ('0xC0000005' if os.name == 'nt' else 'NativeAbort') in card
        assert text.yview()[1] == 1.0, 'Photo card requires scrolling at default scale'
        if os.name == 'nt':
            from folder_native_test_support import capture_window
            capture_window(win, Path(__file__).parent/'evidence-native-crash.bmp')
        app.font_size_var.set('xl'); app.apply_font_size(save=False)
        width = min(1500, app.winfo_screenwidth()-40)
        height = min(1000, app.winfo_screenheight()-80)
        win.geometry(f'{width}x{height}+20+20'); app.update()
        assert text.dlineinfo(text.index('end-1c')) is not None, '200% photo card requires scrolling'
        if os.name == 'nt':
            capture_window(win, Path(__file__).parent/'evidence-native-crash-200.bmp')
        print('Native crash captured, recovered once, old version/time preserved, photo card visible', flush=True)
        assert app.debug_log.clear()
        assert 'process.native_crash' not in app.debug_log.snapshot(automatic=True)
    finally:
        app.debug_log.close()
        app.destroy()
