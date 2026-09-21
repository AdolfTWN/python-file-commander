"""Bounded Expand All, cancellation, navigation, stale results and cached links."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')
tree_module = pfc if pfc.__name__ == 'pfc' else importlib.import_module('pycommander.singlepanel')


def settle(app, seconds=.2):
    until = time.monotonic()+seconds
    while time.monotonic() < until:
        app.update(); time.sleep(.01)


def wait_for(app, condition, timeout=10):
    until = time.monotonic()+timeout
    while not condition() and time.monotonic()<until: settle(app,.05)
    assert condition(), 'Timed out waiting for tree job'


with tempfile.TemporaryDirectory(prefix='pfc-expand-') as raw:
    root = Path(raw); scope = root/'Projects'; scope.mkdir()
    outside = root/'Outside'; outside.mkdir()
    for name in ('Code/Source/Widgets','Documents/Guides','Photos/Trips'):
        (scope/name).mkdir(parents=True)
    (scope/'README.md').write_text('not read')
    pfc.Commander._find_ini_path = staticmethod(lambda: root/'pfc.ini')
    pfc.Commander._sync_auto_start = lambda self, **kw: True
    pfc.Commander._start_windows_tray = lambda self: None
    app = pfc.Commander(); errors=[]
    app.report_callback_exception = lambda *exc: errors.append(str(exc))
    try:
        app.geometry('1450x880+0+0'); app.auto_font_size_var.set(False)
        app.active.navigate(scope); app.panel_count_var.set(1); app.apply_panel_count()
        nav = app.folder_tree; tree = nav.tree
        wait_for(app, lambda:not nav.pending)
        assert not nav.expand_all_var.get()
        initial = dict(nav.nodes)
        settle(app,.3)
        assert nav.nodes == initial, 'Off means no recursive reads'
        scan = tree_module.child_folders; reads=[]
        def recording(path, cancel, **kw):
            reads.append(path)
            return scan(path,cancel,**kw)
        with patch.object(tree_module,'child_folders',recording):
            nav.expand_all_button.invoke()
            wait_for(app,lambda:not nav._bulk_running)
        assert nav.expand_all_var.get()
        expected = [scope]+[p for p in scope.rglob('*') if p.is_dir()]
        for path in expected:
            iid = nav.nodes[os.path.normcase(str(path))]
            assert tree.item(iid,'open'), path
        assert set(reads) == set(expected), reads
        assert all(path==scope or scope in path.parents for path in reads)
        nav.expand_all_button.invoke()
        assert not nav.expand_all_var.get()
        assert tree.item(nav.nodes[os.path.normcase(str(scope/'Code'))],'open')

        # Tree clicks preselect a node before navigation synchronizes it. That
        # path must reset the expansion boundary too, not reuse the old parent.
        nav.expand_all_button.invoke()
        code=nav.nodes[os.path.normcase(str(scope/'Code'))]
        tree.selection_set(code); settle(app)
        assert app.active.path == scope/'Code'
        assert nav._current_node == code and not nav.expand_all_var.get()
        reads.clear()
        with patch.object(tree_module,'child_folders',recording):
            nav.expand_all_button.invoke(); wait_for(app,lambda:not nav._bulk_running)
        assert all(path == scope/'Code' or scope/'Code' in path.parents for path in reads)
        app.active.navigate(scope); settle(app)

        # Cancelling invalidates queued results and signals the worker. Nothing
        # from the cancelled enumeration may arrive later as a phantom row.
        started=threading.Event(); observed=[]
        ghost=scope/'Cancelled-result'
        def slow(path,cancel,**kw):
            started.set(); cancel.wait(2); observed.append(cancel.is_set())
            return [ghost],False
        with patch.object(tree_module,'child_folders',slow):
            nav.expand_all_button.invoke()
            wait_for(app,started.is_set)
            nav.expand_all_button.invoke()
            wait_for(app,lambda:bool(observed))
            settle(app)
        assert observed == [True] and not nav._bulk_pending
        assert os.path.normcase(str(ghost)) not in nav.nodes

        # Existing cached linked branches must not bypass recursion guards.
        link=scope/'Linked'
        try:
            link.symlink_to(outside,target_is_directory=True)
        except OSError:
            print('NOTE: real directory symlink fixture unavailable on this platform')
        else:
            iid=nav._node(link,nav._current_node)
            nav.loaded.add(iid)
            nav.expand_all_button.invoke(); wait_for(app,lambda:not nav._bulk_running)
            assert iid in nav.failed and not tree.item(iid,'open')
            assert nav._bulk_incomplete
            nav.expand_all_button.invoke()

        nav.EXPAND_FOLDERS=2
        nav.expand_all_button.invoke(); wait_for(app,lambda:not nav._bulk_running)
        assert not nav.expand_all_var.get() and nav.status.cget('text')
        nav.EXPAND_FOLDERS=500; nav.EXPAND_SECONDS=.01
        nav.expand_all_button.invoke(); settle(app,.15)
        assert not nav._bulk_running and not nav.expand_all_var.get()
        nav.EXPAND_SECONDS=30
        nav.EXPAND_DEPTH=0
        nav.expand_all_button.invoke(); wait_for(app,lambda:not nav._bulk_running)
        assert not nav.expand_all_var.get() and nav.status.cget('text')
        nav.EXPAND_DEPTH=32
        if os.name == 'nt':
            target=scope/'Photos'
            iid=nav.nodes[os.path.normcase(str(target))]
            tree.item(iid,open=False)
            original_lstat=Path.lstat
            def reparse_stat(path,*args,**kwargs):
                info=original_lstat(path,*args,**kwargs)
                if path == target:
                    return SimpleNamespace(st_mode=info.st_mode,st_file_attributes=0x400)
                return info
            with patch.object(Path,'lstat',reparse_stat):
                nav.expand_all_button.invoke(); wait_for(app,lambda:not nav._bulk_running)
            assert iid in nav.failed and not tree.item(iid,'open')
            assert nav._bulk_incomplete
            nav.expand_all_button.invoke()
        nav.expand_all_button.invoke()
        app.active.navigate(outside); settle(app)
        assert not nav._bulk_running and not nav.expand_all_var.get()
        nav.expand_all_button.invoke()
        app.panel_count_var.set(2); app.apply_panel_count(); settle(app)
        assert not nav.expand_all_var.get(), 'Hidden one-panel trees must stop expanding'
        app.panel_count_var.set(1); app.apply_panel_count(); settle(app)
        nav.expand_all_button.invoke(); nav.refresh(); settle(app)
        assert not nav.expand_all_var.get(), 'Refresh cancels expansion'
        assert not errors,errors
        if '--visual' in sys.argv:
            app.active.navigate(scope); settle(app)
            app.font_size_var.set('large'); app.apply_font_size(save=False)
            nav.expand_all_button.invoke(); wait_for(app,lambda:not nav._bulk_running)
            nav.tree.yview_moveto(0); settle(app)
            print('VISUAL READY',flush=True)
            settle(app,25)
        print('PASS: default off, scoped recursive expansion, cancellation, stale results, cached link refusal, '
              'budgets, navigation/unmap/refresh stop and preserved open branches',flush=True)
    finally:
        app.close_app()
