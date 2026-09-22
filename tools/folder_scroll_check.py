"""Assert overlay alignment inside wheel dispatch, not after a settle delay."""
import importlib
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')


def settle(app, duration=.12):
    end = time.monotonic()+duration
    while time.monotonic()<end:
        app.update(); time.sleep(.005)


with tempfile.TemporaryDirectory(prefix='pfc-scroll-') as raw:
    root = Path(raw)
    pfc.Commander._find_ini_path = staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start = lambda self, **kw:True
    pfc.Commander._start_windows_tray = lambda self:None
    app = pfc.Commander(); errors = []
    app.report_callback_exception = lambda *exc:errors.append(str(exc))
    try:
        app.geometry('1450x900+0+0'); app.auto_font_size_var.set(False)
        app.panel_count_var.set(1); app.apply_panel_count(save=False); settle(app)
        app._sync_single_workspace = lambda:None
        nav = app.folder_tree; tree = nav.tree
        nav.on_navigate = lambda path:None
        for _, _, cancel in nav.pending.values(): cancel.set()
        nav.pending.clear(); nav._context_queue.clear()
        nav.load = lambda *a, **kw:None
        nav._probe_visible = lambda:None
        # A passing test must not depend on the 80ms polling repaint.
        nav.after_cancel(nav._poll_job)
        tree.delete(*tree.get_children(nav.pc)); nav.paths.clear(); nav.nodes.clear()
        def node(parent, name):
            iid = tree.insert(parent, 'end', text=name, open=True)
            nav.paths[iid] = root/name
            return iid
        drive = node(nav.pc, 'Drive'); project = node(drive, 'Projects')
        leaves = [node(project, f'Folder {i:02}') for i in range(70)]
        selected = leaves[5]
        tree.selection_set(selected); tree.focus(selected); tree.focus_force()
        checks = 0
        def aligned():
            assert tree.selection() == (selected,), 'Scrolling must not change selection'
            selection_bg = pfc.ttk.Style(app).lookup('FolderNav.Treeview', 'background', ('selected',))
            for canvas in nav._line_rows:
                if not canvas.winfo_ismapped(): continue
                box = tree.bbox(canvas.row_id)
                assert box, ('stale visible canvas', canvas.row_id)
                assert canvas.winfo_y() == box[1], ('one-row split', canvas.row_id, canvas.winfo_y(), box)
                assert (canvas.cget('background') == selection_bg) == (canvas.row_id == selected)
        for scheme in pfc.COLOR_SCHEMES:
            app.color_scheme_var.set(scheme); app.apply_color_scheme(save=False)
            for scale in ('small', 'large', '175', 'xl'):
                app.font_size_var.set(scale); app.apply_font_size(save=False)
                tree.yview_moveto(0); settle(app)
                for source in ('text', 'icon', 'sticky'):
                    for _ in range(2):
                        for delta in (-120, -120, -120, 120, 120, 120):
                            widget = tree
                            if source == 'icon':
                                widget = next(c for c in nav._line_rows if c.winfo_ismapped())
                            elif source == 'sticky' and nav._sticky.winfo_ismapped():
                                widget = nav._sticky
                            widget.event_generate('<MouseWheel>', delta=delta)
                            # Deliberately no update()/sleep before checking.
                            aligned(); checks += 1
                            app.update_idletasks(); aligned()
                    assert tree.yview()[0] == 0
                    assert not nav._sticky.winfo_ismapped()
                # Scrollbar and horizontal clipping use the same paint path.
                nav._scroll_view('moveto', .5); app.update_idletasks(); aligned()
                tree.column('#0', width=1300, stretch=False)
                tree.xview_moveto(.015); app.update_idletasks(); aligned()
                tree.xview_moveto(0); tree.yview_moveto(0); settle(app)
        # Ctrl+wheel must still zoom rather than scroll the folder tree.
        before = app.font_size_var.get()
        view = tree.yview()
        tree.event_generate('<Control-MouseWheel>', delta=120); settle(app)
        assert app.font_size_var.get() != before
        assert tree.yview()[0] == view[0]
        assert not errors, errors
        print(f'PASS: {checks} immediate wheel alignment checks, text/icon/sticky targets, '
              'three themes, 100/150/175/200%, sticky enter/exit, scrollbar, horizontal clip, Ctrl+wheel')
    finally:
        app.destroy()
