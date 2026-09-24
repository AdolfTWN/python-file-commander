"""File-list navigation reveals its tree selection despite sticky relayout/scans."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')

def settle(app, seconds=.15):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline: app.update();time.sleep(.005)

with tempfile.TemporaryDirectory() as raw:
    root=Path(raw);home=root/'Users'/'Local';cloud=home/'OneDrive';desktop=cloud/'Desktop'
    desktop.mkdir(parents=True)
    for parent in (home,cloud):
        for i in range(55): (parent/f'Folder {i:02}').mkdir()
    (home/'Downloads'/'Package'/'Nested').mkdir(parents=True)
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda self,**kw:True
    pfc.Commander._start_windows_tray=lambda self:None
    app=pfc.Commander();errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.geometry('1300x750+0+0');app.auto_font_size_var.set(False)
        app.active.navigate(home);app.panel_count_var.set(1);app.apply_panel_count(save=False)
        nav=app.folder_tree;tree=nav.tree
        for scale in ('small','large','175','xl'):
            app.font_size_var.set(scale);app.apply_font_size(save=False)
            for path in (home/'Downloads'/'Package'/'Nested',home,cloud,desktop,home):
                tree.yview_moveto(1);settle(app)
                app.active.navigate(path)
                deadline=time.monotonic()+8
                while time.monotonic()<deadline:
                    settle(app)
                    if not nav.pending and not nav._context_queue and nav._view_settle_job is None:break
                iid=nav.nodes[os.path.normcase(str(path))]
                assert tree.selection()==(iid,) and tree.focus()==iid
                box=tree.bbox(iid)
                assert box and box[1]>=1 and box[1]+box[3]<tree.winfo_height(),(scale,path,box)
                assert not tree.winfo_children(), 'Highlight cannot be split across child surfaces'
        tree.yview_moveto(0);settle(app);view=tree.yview()
        nav.sync(home);settle(app)
        assert tree.yview()==view, 'Repeated sync must respect manual scrolling'
        assert not errors,errors
        print('PASS: Downloads/home/OneDrive/Desktop-shaped local navigation; settled selection visible at 100/150/175/200%; no override of manual scroll')
    finally:app.destroy()
