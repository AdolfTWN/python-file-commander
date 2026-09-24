"""Saved deep paths: complete sibling levels, honest connectors and stable rows."""
import importlib
import os
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
module = importlib.import_module(next((arg for arg in sys.argv[1:] if not arg.startswith('--')),
                                    'pycommander.singlepanel'))


def wait_for(condition, seconds=8):
    deadline = time.monotonic()+seconds
    while not condition() and time.monotonic() < deadline:
        app.update(); time.sleep(.01)
    assert condition(), 'Timed out waiting for folder hierarchy'


def settle(seconds=.2):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        app.update(); time.sleep(.01)


drive = Path(Path.cwd().anchor)
user = drive/'Users'/'PFC-Test'
downloads = user/'Downloads'
package = downloads/'XPS Package'
target = package/'XPS Package'
chain = list(reversed(target.parents))+[target]
listing = {path: [chain[index+1]] for index,path in enumerate(chain[:-1])}
listing[target] = [target/name for name in ('Capsule','EFI','Firmware')]
listing[downloads] += [downloads/name for name in ('.codex','Drivers','Photos','Z-last')]
listing[user] += [user/'Documents',user/'Pictures']
listing[drive] += [drive/'Apps',drive/'Windows']
reads=[]; held=threading.Event(); hold=False
active=0; maximum=0; lock=threading.Lock()


def scan(path, cancel):
    global active,maximum
    with lock:
        reads.append(path);active+=1;maximum=max(maximum,active)
    try:
        if hold: held.wait(3)
        time.sleep(.03)
        return sorted(listing.get(path,[]),key=lambda p:p.name.casefold()),False
    finally:
        with lock:active-=1


app=tk.Tk();app.geometry('860x800+0+0');errors=[]
app.report_callback_exception=lambda *exc:errors.append(str(exc))
with patch.object(module,'root_folders',lambda:[drive]), patch.object(module,'child_folders',scan):
    nav=module.RootFolderTree(app,lambda path:nav.sync(path),lambda e:None)
    nav.pack(fill='both',expand=True);tree=nav.tree
    def node(path):return nav.nodes[os.path.normcase(str(path))]
    def idle():return not nav.pending and not nav._context_queue
    try:
        # Two blocked workers must not silently drop the remaining ancestors.
        hold=True;nav.sync(target);settle(.12)
        assert nav._context_queue and len(nav.pending)==2
        assert maximum==2
        selected=tree.selection();held.set()
        wait_for(idle);settle()
        assert tree.selection()==selected==(node(target),)
        assert set(reads)==set(chain),reads
        assert len(reads)==len(chain) and maximum<=2
        assert not nav.expand_all_var.get()
        for path in chain:
            iid=node(path)
            assert iid in nav.loaded
            assert tree.item(iid,'open')
            actual=[nav.paths[child] for child in tree.get_children(iid)]
            assert actual==sorted(listing[path],key=lambda p:p.name.casefold()),(path,actual)
        # No eager recursion through sibling folders, and no fake long lines.
        assert node(downloads/'Drivers') not in nav.loaded
        tree.see(node(target));settle()
        from folder_native_test_support import assert_guides
        assert assert_guides(nav,node(target))>0
        # Clicking Downloads must not cause missing siblings to suddenly appear.
        before=tree.get_children(node(downloads));before_reads=list(reads)
        tree.selection_set(node(downloads));settle()
        assert tree.get_children(node(downloads))==before and reads==before_reads
        assert nav._current_node==node(downloads)
        # Delayed initial siblings must not undo manual collapse.
        nav.sync(target);settle()
        tree.item(node(downloads),open=False);nav.sync(target);settle()
        assert not tree.item(node(downloads),'open')
        # A refresh cancels prior work; a newly seeded path is completed again.
        hold=False;tree.selection_set(node(target));nav.refresh()
        wait_for(idle);settle()
        assert tree.selection()==(node(target),)
        assert all(node(path) in nav.loaded for path in chain)
        assert not errors,errors
        if '--screenshot' in sys.argv:
            from PIL import ImageGrab
            tree.yview_moveto(0);settle()
            ImageGrab.grab().save('/tmp/pfc-folder-hierarchy.png')
        print('PASS: initial ancestor/sibling population, two-worker queue, sorted in-place merge, '
              'selection, real branch topology, no click-dependent siblings, collapse and refresh')
    finally:
        held.set();nav.destroy();app.destroy()
