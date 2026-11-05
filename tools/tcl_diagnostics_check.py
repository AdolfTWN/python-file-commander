"""Native Tcl bgerror is recorded automatically without copying private text."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')

with tempfile.TemporaryDirectory(prefix='pfc-tcl-log-') as raw:
    root=Path(raw);original=pfc.DiagnosticLog
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**k:True
    pfc.Commander._start_windows_tray=lambda *a:None
    with patch.object(pfc,'DiagnosticLog',side_effect=lambda *a,**k:original(*a,directory=root/'logs',**k)):
        app=pfc.Commander()
    try:
        app.auto_font_size_var.set(False)
        app.tk.call('after','idle','123456missing_test_callback')
        marker='SYNTHETIC_NDA_DOCUMENT_MARKER'
        app.tk.call('after','idle',marker)
        deadline=time.monotonic()+.4
        while time.monotonic()<deadline:app.update();time.sleep(.01)
        text=app.debug_log.snapshot(automatic=True)
        rows=[json.loads(line) for line in text.splitlines()]
        errors=[row for row in rows if row.get('event')=='tk.background.failed']
        assert len(errors)==2,errors
        assert all(row['severity']=='ERROR' and row['version']==pfc.__version__ and row['time'] for row in errors)
        assert errors[0].get('reason')=='Deleted Tk callback'
        assert errors[0].get('callback')=='missing_test_callback'
        assert marker not in text and '123456missing_test_callback' not in text
        print('PASS: native Tcl errors logged with time/version, callback category and no document text')
    finally:app.close_app()
