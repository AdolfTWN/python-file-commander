"""Real malformed startup and failed preference saves retain safe diagnostics."""
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
api=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')

if '--startup-child' in sys.argv:
    folder=Path(sys.argv[sys.argv.index('--startup-child')+1])
    original=api.DiagnosticLog
    def diagnostic(version,**kwargs):return original(version,directory=folder/'logs',**kwargs)
    with patch.object(api,'DiagnosticLog',diagnostic),\
            patch.object(api.Commander,'_find_ini_path',return_value=folder/'pfc.ini'),\
            patch.object(api,'relaunch_with_pythonw',return_value=False),\
            patch.object(api,'hide_private_console'),\
            patch.object(api.Commander,'_sync_auto_start',side_effect=AssertionError('Startup mutation after invalid config')):
        api.main()
    raise AssertionError('Malformed configuration unexpectedly loaded')

with tempfile.TemporaryDirectory(prefix='pfc-settings-diagnostics-') as raw:
    folder=Path(raw);startup=folder/'startup';startup.mkdir()
    invalid=b'PRIVATE-CONFIGURATION-CONTENT\n[broken\n'
    (startup/'pfc.ini').write_bytes(invalid)
    child=subprocess.run([sys.executable,__file__,api.__name__,'--startup-child',str(startup)],
                         capture_output=True,timeout=30)
    assert child.returncode!=0,'Startup did not reject invalid configuration'
    path=startup/'logs'/'pfc-errors.jsonl'
    assert path.exists(),'Early configuration failure bypassed automatic diagnostics'
    snapshot=path.read_text(encoding='utf-8')
    rows=api.diagnostic_records(snapshot)
    failure=next(row for row in rows if row['event']=='python.unhandled')
    assert failure['version']==api.__version__ and failure['time'] and failure['frames']
    assert 'PRIVATE' not in snapshot and str(startup) not in snapshot
    assert (startup/'pfc.ini').read_bytes()==invalid,'Failed startup changed original configuration'
    saved=folder/'save';saved.mkdir();ini=saved/'pfc.ini'
    ini.write_text('[view]\nauto_font_size=false\n[startup]\nauto_start=false\n')
    original=api.DiagnosticLog
    def diagnostic(version,**kwargs):return original(version,directory=saved/'logs',**kwargs)
    with patch.object(api,'DiagnosticLog',diagnostic),\
            patch.object(api.Commander,'_find_ini_path',return_value=ini),\
            patch.object(api.Commander,'_sync_auto_start'),patch.object(api.Commander,'_start_windows_tray'):
        app=api.Commander()
    try:
        app.update()
        before=ini.read_bytes()  # Normal startup may persist new defaults.
        with patch.object(api,'write_config_atomic',side_effect=PermissionError(13,'PRIVATE-PATH-CONTENT')):
            app.save_config();app.save_config()
        snapshot=app.debug_log.snapshot(automatic=True)
        rows=[row for row in api.diagnostic_records(snapshot) if row['event']=='settings.save.failed']
        assert len(rows)==1,'Save warning missing or duplicated on every retry'
        assert rows[0]['severity']=='WARNING' and rows[0]['version']==api.__version__
        assert rows[0]['time'] and rows[0]['errno']==13
        assert 'PRIVATE' not in snapshot
        assert ini.read_bytes()==before,'Failed save changed original configuration'
    finally:app.destroy()
print('PASS: early startup failure and one-per-session save warning recorded with version/time; original preferences preserved')
