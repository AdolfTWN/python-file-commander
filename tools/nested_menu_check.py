"""Three-level main menus: re-entry, grab routing, edges and keyboard traversal."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')

def pump(app):
    until=time.monotonic()+.08
    while time.monotonic()<until: app.update();time.sleep(.01)

def hover(app,popup,index,native=False):
    x=popup.top.winfo_rootx()+popup.width//2
    y=popup.top.winfo_rooty()+sum(popup.row_bounds[index])//2
    if native and os.name=='nt':
        import ctypes
        ctypes.windll.user32.SetCursorPos(x-3,y);pump(app)
        ctypes.windll.user32.SetCursorPos(x,y);pump(app)
    else:
        # Deliberately deliver the event to the grabbed root, not the child.
        app.header_popup.popups[0]._motion(SimpleNamespace(x_root=x,y_root=y))
        pump(app)

with tempfile.TemporaryDirectory() as raw:
    pfc.Commander._find_ini_path=staticmethod(lambda:Path(raw)/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda self,**kw:True
    app=pfc.Commander();errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False)
        for size in ('small','large','300'):
            app.font_size_var.set(size);app.apply_font_size(save=False)
            for x in (0,max(0,app.winfo_screenwidth()-920)):
                app.geometry(f'900x650+{x}+0');pump(app)
                for col in range(4):
                    ctl=app.header_popup
                    ctl.show(app.view_menu_button,app.view_menu);pump(app)
                    root=ctl.popups[0]
                    index=next(i for i,k,l,a,s in root.items if l=='File Columns')
                    hover(app,root,index,native=True)
                    assert len(ctl.popups)==2
                    columns=ctl.popups[1]
                    hover(app,columns,col,native=True)
                    assert len(ctl.popups)==3,(size,col,'third level missing')
                    leaf=ctl.popups[2]
                    assert leaf.top.winfo_ismapped()
                    assert 0<=leaf.top.winfo_rootx()<=app.winfo_screenwidth()-leaf.width
                    # Keyboard return leaves the same selected parent row.
                    # Hovering it again must reopen the missing third level.
                    leaf._left()
                    columns._motion(SimpleNamespace(y=sum(columns.row_bounds[col])//2))
                    pump(app)
                    assert len(ctl.popups)==3,'selected cascade must reopen after Left/Escape'
                    # A root-grab delivery must hit-test the real child.
                    hover(app,columns,col)
                    assert len(ctl.popups)==3
                    ctl.close_all()
                print('PASS: nested columns',size,'window x=',x,flush=True)
        # Down highlights; Right enters exactly one level, Left returns one.
        ctl.show(app.view_menu_button,app.view_menu);pump(app)
        root=ctl.popups[0];root._move(1)
        assert len(ctl.popups)==1
        root._open_selected();pump(app)
        assert len(ctl.popups)==2
        columns=ctl.popups[1];columns._open_selected();pump(app)
        assert len(ctl.popups)==3
        ctl.popups[-1]._left();assert len(ctl.popups)==2
        ctl.popups[-1]._left();assert len(ctl.popups)==1
        root._escape();assert not ctl.popups
        assert not errors,errors
        print('PASS: three-level mouse/re-entry/edge/grab routing and keyboard checks')
    finally:
        app.header_popup.close_all();app.destroy()
