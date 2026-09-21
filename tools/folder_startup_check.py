"""Saved-path startup draws all ancestor guides before any folder click."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')

def settle(app,seconds=.5):
    until=time.monotonic()+seconds
    while time.monotonic()<until:app.update();time.sleep(.01)

with tempfile.TemporaryDirectory(prefix='pfc-startup-') as raw:
    root=Path(raw);target=root/'Users'/'Local'/'Projects'/'Commander'
    target.mkdir(parents=True)
    for name in ('agents','compare','code','tests','tools'):(target/name).mkdir()
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda self,**kw:True
    pfc.Commander._start_windows_tray=lambda self:None
    app=pfc.Commander()
    app.geometry('1450x880+0+0');app.auto_font_size_var.set(False)
    app.font_size_var.set('large');app.apply_font_size(save=False)
    app.active.navigate(target);app.panel_count_var.set(1);app.apply_panel_count()
    settle(app);app.save_config()
    for job in app.tk.call('after','info'):app.tk.call('after','cancel',job)
    app.close_app()
    app=pfc.Commander();errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        settle(app,1)
        nav=app.folder_tree;tree=nav.tree
        assert app.active.path==target
        iid=nav.nodes[os.path.normcase(str(target))]
        ancestors=[];parent=tree.parent(iid)
        while parent:
            ancestors.append(parent);parent=tree.parent(parent)
        assert any(item not in nav.loaded for item in ancestors if item in nav.paths)
        # No input events before these assertions: inspect the first loaded view.
        checked=0
        for canvas in nav._line_rows:
            if not canvas.winfo_ismapped():continue
            row=canvas.row_id;depth=0;parent=tree.parent(row)
            while parent:depth+=1;parent=tree.parent(parent)
            bbox=tree.bbox(row);offset=bbox[0]-canvas.winfo_x()
            coords=[canvas.coords(line) for line in canvas.find_withtag('branch')]
            for level in range(1,depth):
                x=round((level-.5)*nav._line_indent+offset)
                assert [float(x),0.,float(x),float(bbox[3])] in coords,(row,level,coords)
                checked+=1
        assert checked>10
        if '--visual' in sys.argv:
            print('VISUAL READY',flush=True);settle(app,25)
        assert not errors,errors
        print('PASS: saved-path restart, unscanned ancestors and complete vertical guides before any folder click',flush=True)
    finally:app.close_app()
