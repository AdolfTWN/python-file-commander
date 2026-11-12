"""Windows enumeration semantics and measured, identical full-folder tasks."""
import ctypes
import importlib
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')
data=sys.modules[pfc.DirectoryReads.__module__]


with tempfile.TemporaryDirectory(prefix='pfc-entry-listing-') as raw:
    root=Path(raw);folder=root/'files';folder.mkdir()
    for n in range(316):
        (folder/(f'fixture-{n:03}'+('.md' if n%2 else '.zip'))).write_bytes(b'fixture'+str(n).encode())
    expected=data.listing_signature(data.listing_items(folder.iterdir()))
    rows=data.directory_items(folder)
    assert data.listing_signature(rows)==expected
    if os.name=='nt':
        # Ordinary entries must not reopen files. A fresh enumeration must see
        # changed metadata rather than preserving DirEntry objects in a cache.
        with patch.object(Path,'stat',side_effect=AssertionError('Unexpected per-file Path.stat')):
            assert data.listing_signature(data.directory_items(folder))==expected
        changed=folder/'fixture-000.zip';changed.write_bytes(b'updated fixture data')
        assert data.listing_signature(data.directory_items(folder))!=expected
        expected=data.listing_signature(data.listing_items(folder.iterdir()))
        hidden=folder/'hidden.txt';system=folder/'system.txt';dot=folder/'.dot'
        for path in (hidden,system,dot):path.write_text('fixture')
        setattrs=ctypes.windll.kernel32.SetFileAttributesW
        assert setattrs(str(hidden),2) and setattrs(str(system),4)
        try:
            names={row.path.name for row in data.directory_items(folder)}
            assert not {'hidden.txt','system.txt','.dot'} & names
            assert len(data.directory_items(folder,True,True))==319
            assert hidden in [r.path for r in data.directory_items(folder,reveal=hidden)]
        finally:
            setattrs(str(hidden),0x80);setattrs(str(system),0x80)
            for path in (hidden,system,dot):path.unlink()
        target=root/'target';target.mkdir();(target/'child.txt').write_text('target')
        junction=folder/'junction'
        subprocess.run(['cmd','/c','mklink','/J',str(junction),str(target)],check=True,capture_output=True)
        try:
            row=next(r for r in data.directory_items(folder) if r.path==junction)
            oracle=junction.stat()
            assert row.is_dir and row.metadata.st_size==oracle.st_size
            assert row.metadata.st_mtime_ns==oracle.st_mtime_ns
        finally:junction.rmdir()
        expected=data.listing_signature(data.listing_items(folder.iterdir()))

    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda *a,**k:True
    pfc.Commander._start_windows_tray=lambda *a:None
    app=pfc.Commander();errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.config_data.set('refresh','auto_refresh','false')
        if app._auto_refresh_job is not None:
            app.after_cancel(app._auto_refresh_job);app._auto_refresh_job=None
        app.vcs_overlay_var.set(False);app.onedrive_overlay_var.set(False)
        pane=app.active
        assert pane.navigate(folder);app.update()  # Same warm icon cache for both paths.
        if os.name=='nt':
            def legacy(folder,show_hidden=False,show_system=False,reveal=None,*,latency=None,cancelled=None):
                rows=[]
                for path in folder.iterdir():
                    if cancelled is not None and cancelled.is_set():raise data.DirectoryReadCancelled()
                    # Controlled 3ms provider latency per path-based request,
                    # modelling the two stages reported by the user.
                    time.sleep(.003)
                    attrs=ctypes.windll.kernel32.GetFileAttributesW(str(path))
                    if path!=reveal and ((not show_hidden and (path.name.startswith('.') or attrs&2)) or
                                         (not show_system and attrs&4)):continue
                    time.sleep(.003)
                    rows.append(data.DirectoryItem(path,path.stat()))
                return tuple(rows)
            candidate=data.directory_items
            timings={}
            for label,function in (('legacy',legacy),('enumerated',candidate)):
                samples=[]
                for _ in range(3):
                    with patch.object(data,'directory_items',function):
                        start=time.monotonic();assert pane.navigate(folder)
                        samples.append(time.monotonic()-start)
                    assert pane._signature==expected
                    assert len(pane.tree.get_children())==316
                timings[label]=statistics.median(samples)
            assert timings['enumerated'] < timings['legacy']*.6,timings
            print('Controlled full folder navigation, 316 ordinary entries, 3ms per path provider query, median of 3:',timings,flush=True)
            print('PASS: native enumerated metadata equals path-stat oracle; hidden/system/reveal, fresh listing and junction target semantics preserved',flush=True)
        else:
            print('PASS: POSIX listing and full folder navigation retain identical 316 rows; Windows provider comparison is Windows-only',flush=True)
        assert not errors,errors
    finally:app.close_app()
