"""Real Tk regression: leaf folders never advertise nonexistent descendants."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
module = importlib.import_module(next((arg for arg in sys.argv[1:] if not arg.startswith('--')),
                                    'pycommander.singlepanel'))

def settle(seconds=.15):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        app.update(); time.sleep(.01)

def wait_for(condition):
    deadline = time.monotonic()+8
    while not condition() and time.monotonic() < deadline: settle(.02)
    assert condition(), 'Folder hint check timed out'

with tempfile.TemporaryDirectory(prefix='pfc-leaf-') as raw:
    root = Path(raw)
    for name in ('Empty', 'rules', 'Projects/Child/Deep', 'Unknown'):
        (root/name).mkdir(parents=True)
    (root/'rules'/'instructions.md').write_text('rules, not a child folder')
    real_probe = module.folder_has_children
    held = threading.Event(); reads = []; active = 0; maximum = 0
    def probe(path, cancel):
        global active, maximum
        active += 1; maximum = max(maximum, active); reads.append(path)
        try:
            held.wait(4)
            if path.name == 'Unknown': return None
            return real_probe(path, cancel)
        finally: active -= 1
    app = tk.Tk(); app.geometry('920x720+0+0'); errors = []
    # Match Commander's theme: native Windows "vista" ignores the scalable
    # Treeview indentation used by PFC's custom joint/icon cells.
    ttk.Style(app).theme_use('clam')
    app.report_callback_exception = lambda *exc: errors.append(str(exc))
    with patch.object(module, 'root_folders', lambda: []), patch.object(module, 'folder_has_children', probe):
        nav = module.RootFolderTree(app, lambda path: nav.sync(path), lambda e: None)
        nav.pack(fill='both', expand=True); tree = nav.tree
        def node(path): return nav.nodes[os.path.normcase(str(path))]
        def canvas(iid):
            return next(c for c in nav._line_rows if c.winfo_ismapped() and c.row_id == iid)
        def badge(iid): return bool(canvas(iid).find_withtag('indicator'))
        try:
            parent = nav._node(root, nav.pc)
            nav._current_node = parent; nav.program_selection = parent
            tree.item(parent, open=True); tree.selection_set(parent); nav.load(parent)
            wait_for(lambda: parent in nav.loaded and nav._probe_cancel is not None)
            settle()
            leaves = [node(root/name) for name in ('Empty', 'rules')]
            branch = node(root/'Projects'); unknown = node(root/'Unknown')
            assert all(not badge(iid) for iid in (*leaves, branch, unknown)), 'Unknown is not a confirmed branch'
            held.set()
            wait_for(lambda: all(iid in nav._child_hints for iid in (*leaves, branch, unknown)))
            settle()
            assert all(nav._child_hints[iid] is False and not badge(iid) for iid in leaves)
            assert badge(branch) and nav._child_hints[branch] is True
            assert nav._child_hints[unknown] is None and not badge(unknown)
            assert all(not tree.get_children(iid) for iid in leaves)
            assert tree.get_children(unknown), 'Unknown retains keyboard/manual discovery'
            assert maximum == 1 and all(path.parent == root for path in reads), reads
            assert len(reads) == 4, 'No recursive hint scans'
            # Opening a confirmed-but-not-loaded branch clears its plus at once;
            # a placeholder must not paint a fake downward continuation.
            tree.item(branch, open=True); nav._draw_lines()
            assert not badge(branch)
            tree.item(branch, open=False); nav._draw_lines()
            assert badge(branch)
            # Three contrast/zoom rounds: badges must not change or flicker on repaint.
            style = ttk.Style(app)
            font = tkfont.nametofont('TkDefaultFont')
            for zoom, colors in ((12, ('#ffffff', '#202020')), (18, ('#e2e2e2', '#263c50')),
                                 (36, ('#252525', '#eeeeee'))):
                font.configure(family='Arial', size=zoom)
                style.configure('FolderNav.Treeview', font=font, rowheight=round(zoom*2.1),
                                background=colors[0], foreground=colors[1])
                settle(); tree.yview_moveto(0); settle()
                assert badge(branch) and all(not badge(iid) for iid in leaves)
                for iid in (*leaves, branch, unknown):
                    cell = canvas(iid)
                    x = cell.winfo_x()+cell.winfo_width()+4
                    y = cell.winfo_y()+cell.winfo_height()//2
                    assert tree.identify_element(x, y) in ('text', 'Treeitem.text'), 'Icon must not cover text'
                before = nav._line_signature
                for _ in range(6): nav._draw_lines()
                assert nav._line_signature == before and len(reads) == 4
                assert nav._icon_size == max(14, round(font.metrics('linespace')*.9))
            font.configure(size=18)
            style.configure('FolderNav.Treeview', font=font, rowheight=38,
                            background='#e2e2e2', foreground='#263c50')
            settle()
            if '--visual' in sys.argv:
                print('VISUAL READY', flush=True); settle(25)
            # Native Right expands a real branch even before selecting/navigating it.
            nav.program_selection = branch; tree.selection_set(branch)
            tree.focus(branch); tree.focus_force(); tree.event_generate('<KeyPress-Right>')
            wait_for(lambda: branch in nav.loaded); settle()
            assert tree.item(branch, 'open') and node(root/'Projects'/'Child') in tree.get_children(branch)
            # Unknown/error rows remain accessible via normal selection.
            tree.selection_set(unknown); wait_for(lambda: unknown in nav.loaded)
            assert not tree.get_children(unknown) and not nav._has_branch(unknown)
            # Refresh invalidates the negative cache; new subfolders become discoverable.
            (root/'rules'/'new folder').mkdir()
            tree.selection_set(parent); settle(); nav.refresh()
            wait_for(lambda: nav._child_hints.get(node(root/'rules')) is True if
                     os.path.normcase(str(root/'rules')) in nav.nodes else False)
            settle(); assert badge(node(root/'rules'))
            # Refresh during a blocked hint ignores its stale result and never
            # starts a replacement worker while the old OS call is outstanding.
            held.clear(); nav.refresh()
            wait_for(lambda: nav._probe_cancel is not None)
            old_cancel = nav._probe_cancel; nav.refresh(); settle()
            assert old_cancel.is_set() and nav._probe_cancel is old_cancel and maximum == 1
            held.set(); wait_for(lambda: nav._child_hints.get(node(root/'rules')) is True if
                                os.path.normcase(str(root/'rules')) in nav.nodes else False)
            settle(); assert maximum == 1 and not errors, errors
            print('PASS: empty/files-only leaves before click; honest unknown/branch badges; '
                  'single bounded worker, no recursive scan; 100/150/300% contrast, stable redraw; '
                  'keyboard/manual discovery; refresh invalidation and cancellation', flush=True)
        finally:
            held.set(); nav.destroy(); app.destroy()
