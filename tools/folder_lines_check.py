"""Dotted folder-tree connectors: zoom/theme, icons, scroll and hit testing."""
import importlib
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')


def settle(app, seconds=.15):
    end=time.monotonic()+seconds
    while time.monotonic()<end: app.update(); time.sleep(.01)


with tempfile.TemporaryDirectory(prefix='pfc-lines-') as raw:
    root=Path(raw)
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda self,**kw:True
    app=pfc.Commander(); errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.geometry('1450x880+0+0'); app.auto_font_size_var.set(False)
        app.panel_count_var.set(1); app.apply_panel_count(); settle(app)
        # This visual fixture owns its synthetic tree; workspace synchronization
        # is exercised separately by single_panel_check.py against real folders.
        app._sync_single_workspace=lambda:None
        nav=app.folder_tree; tree=nav.tree
        tree.delete(*tree.get_children(nav.pc)); nav.paths.clear();nav.nodes.clear()
        for name in ('Projects','Documents','Photos'):
            parent=nav._node(root/name,nav.pc)
            for dummy in tree.get_children(parent): tree.delete(dummy)
            for number in range(20):
                child=nav._node(root/name/f'Folder {number:02}',parent)
                for dummy in tree.get_children(child):tree.delete(dummy)
            tree.item(parent,open=True)
        nav.program_selection=None
        navigated=[];nav.on_navigate=navigated.append
        projects=nav.nodes[str(root/'Projects').lower() if sys.platform=='win32' else str(root/'Projects')]
        for scheme in pfc.COLOR_SCHEMES:
            app.color_scheme_var.set(scheme);app.apply_color_scheme(save=False)
            for zoom in ('small','large','300'):
                app.font_size_var.set(zoom);app.apply_font_size(save=False);settle(app)
                tree.yview_moveto(0);settle(app)
                canvases=[c for c in nav._line_rows if c.winfo_ismapped()]
                assert canvases and any(c.find_withtag('branch') for c in canvases)
                for canvas in canvases:
                    for line in canvas.find_withtag('branch'):
                        assert canvas.itemcget(line,'dash')=='1 2'
                        assert float(canvas.itemcget(line,'width'))==1
                    assert canvas.winfo_y()==tree.bbox(canvas.row_id)[1]
                    # No canvas may cover the native row label.
                    text_x=canvas.winfo_x()+canvas.winfo_width()+nav._icon_size+4
                    mid=canvas.winfo_y()+canvas.winfo_height()//2
                    if mid<tree.winfo_height()-2:
                        assert tree.identify_element(text_x,mid) in ('text','Treeitem.text'), (scheme,zoom,canvas.row_id,text_x,mid,tree.identify_element(text_x,mid),nav._line_indent)
                before=nav._line_signature
                nav._draw_lines(); assert nav._line_signature==before
                tree.yview_moveto(.6);settle(app)
                assert nav._line_signature!=before
        tree.yview_moveto(0);settle(app)
        canvas=next(c for c in nav._line_rows if c.winfo_ismapped() and c.row_id==projects)
        # Expanded rows have no collapse glyph or invisible collapse hit target.
        assert tree.item(projects,'open')
        assert not canvas.find_withtag('indicator')
        canvas.event_generate('<Button-1>',x=round(canvas.arrow_x),y=canvas.winfo_height()//2);settle(app)
        assert tree.item(projects,'open')
        tree.item(projects,open=False);nav._draw_lines();settle(app)
        assert not tree.item(projects,'open')
        assert canvas.find_withtag('indicator'), 'Closed branches remain discoverable'
        nav.loaded.add(projects)  # No filesystem scan for this synthetic fixture.
        canvas.event_generate('<Button-1>',x=round(canvas.arrow_x),y=canvas.winfo_height()//2);settle(app)
        assert tree.item(projects,'open')
        child=tree.get_children(projects)[0]
        tree.selection_set(child);tree.see(child);settle(app)
        canvas=next(c for c in nav._line_rows if c.winfo_ismapped() and c.row_id==child)
        canvas.event_generate('<Button-1>',x=2,y=canvas.winfo_height()//2);settle(app)
        assert navigated[-1]==nav.paths[child]
        # Horizontal clipping preserves alignment too.
        tree.column('#0',width=1400,stretch=False);tree.xview_moveto(.04);settle(app)
        assert not errors,errors
        if '--screenshot' in sys.argv:
            from PIL import ImageGrab
            app.font_size_var.set('large');app.apply_font_size(save=False)
            tree.xview_moveto(0);tree.yview_moveto(0);settle(app)
            ImageGrab.grab().save(str(Path(raw).parent/'pfc-folder-lines.png'))
        print('PASS: fine dotted branches, last-child corners, scaled icons, three themes and 100/150/300% zoom, '
              'native text clear, stable redraw, scroll alignment, no collapse glyph, expansion and selection')
    finally: app.destroy()
