"""Compact size, rich unit rendering and date alignment, without large files."""
import importlib
from pathlib import Path
import sys
import tempfile
import time
import tkinter.font as tkfont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
module = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'pycommander.app')


def settle(app):
    until = time.monotonic() + .12
    while time.monotonic() < until:
        app.update(); time.sleep(.01)


with tempfile.TemporaryDirectory() as raw:
    root = Path(raw)/'files'; root.mkdir()
    for index in range(45):
        (root/f'{index:02}-long-readable-file-name.txt').write_text('test')
    module.Commander._find_ini_path = staticmethod(lambda: Path(raw)/'pfc.ini')
    module.Commander._sync_auto_start = lambda self, **kw: True
    app = module.Commander(); errors = []
    app.report_callback_exception = lambda *exc: errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False)
        app.geometry('1400x760')
        pane = app.left_tabs.current(); pane.navigate(root); app.set_active(pane)
        tree, units = pane.tree, pane.size_units
        for theme in ('light_grey', 'dark', 'light'):
            app.color_scheme_var.set(theme); app.apply_color_scheme(save=False)
            for scale in module.FONT_SCALES:
                app.font_size_var.set(scale); app.apply_font_size(save=False)
                settle(app)
                rows = tree.get_children()
                for index, iid in enumerate(rows):
                    values = list(tree.item(iid, 'values'))
                    values[1] = ('24 kB', '850 MB', '12 GB', '3 TB')[index % 4]
                    tree.item(iid, values=values)
                pane._autosize_columns(); tree.focus_force(); settle(app)
                assert str(tree.column('modified', 'anchor')) == 'e'
                font = tkfont.nametofont('TkDefaultFont')
                old_width = font.measure('0000.0 MB') + max(18, font.measure('MM'))
                assert tree.column('size', 'width') < old_width
                assert units.bold.actual('weight') == 'bold'
                assert units.bold.cget('size') == font.cget('size')
                mapped = [c for c in units.cells if c.winfo_ismapped()]
                assert mapped, (theme, scale)
                for cell in mapped:
                    ids = cell.find_all()
                    unit = cell.itemcget(ids[0], 'text')
                    assert unit in ('GB', 'TB')
                    assert cell.itemcget(ids[0], 'font') == str(units.bold)
                    if unit == 'TB':
                        assert cell.itemcget(ids[0], 'fill') in ('#ff8585', '#b00020')
                    bbox = cell.bbox('all')
                    assert bbox[0] >= 0 and bbox[2] <= cell.winfo_width()+1, bbox
                cell = mapped[0]
                permanent_ids = cell.find_all()
                for _ in range(3):
                    units.request()
                    assert cell.winfo_ismapped(), 'Redraw request must not unmap visible size cells'
                    settle(app)
                    assert cell.find_all() == permanent_ids, 'Reuse text instead of recreating it'
                expected = tree.identify_row(cell.winfo_y()+3)
                cell.event_generate('<ButtonPress-1>', x=5, y=3)
                cell.event_generate('<ButtonRelease-1>', x=5, y=3)
                settle(app)
                assert expected in tree.selection()
                tree.yview_moveto(1); settle(app)
                assert len(units.cells) < len(rows), 'Only visible rich cells should have widgets'
                tree.yview_moveto(0); settle(app)
        # Actual small-file values use the new formatter, not synthetic fixtures.
        pane.refresh(); settle(app)
        assert all(tree.set(iid, 'size') == '4 B' for iid in tree.get_children())
        assert not any(c.winfo_ismapped() for c in units.cells)
        assert not errors, errors
        if '--screenshot' in sys.argv:
            app.font_size_var.set('small'); app.apply_font_size(save=False); settle(app)
            for index, iid in enumerate(tree.get_children()):
                values = list(tree.item(iid, 'values'))
                values[1] = ('24 kB', '850 MB', '12 GB', '3 TB')[index % 4]
                tree.item(iid, values=values)
            pane._autosize_columns(); settle(app)
            from PIL import ImageGrab
            ImageGrab.grab().save('/tmp/pfc-size-column.png')
        print('PASS: integer sizes, compact widths, GB bold, TB bold red, right-aligned dates, themes/zoom, selection and scrolling')
    finally:
        app.destroy()
        assert units.closed and units.pending is None
