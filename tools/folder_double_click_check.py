"""Real Tk click pairs: tree text/icon/connectors and stable manual collapse."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')


def settle(app, seconds=.15):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        app.update();time.sleep(.01)


with tempfile.TemporaryDirectory(prefix='pfc-double-') as raw:
    root=Path(raw)
    for name in ('Alpha/Child/Deep','Beta/Child','Empty'):
        (root/name).mkdir(parents=True)
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda self,**kw:True
    pfc.Commander._start_windows_tray=lambda self:None
    app=pfc.Commander();errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.geometry('1450x880+0+0');app.auto_font_size_var.set(False)
        app.active.navigate(root);app.panel_count_var.set(1);app.apply_panel_count()
        settle(app,.4)
        nav=app.folder_tree;tree=nav.tree
        stamp=10000
        def node(path):return nav.nodes[os.path.normcase(str(path))]
        def double(iid, region='text'):
            global stamp
            tree.see(iid);settle(app)
            nav._draw_lines()
            c=next(c for c in nav._line_rows if c.winfo_ismapped() and c.row_id==iid)
            if region in ('connector','icon'):
                target=c;x=2 if region=='connector' else c.icon_x;y=c.icon_y
            else:
                target=tree
                x=c.winfo_x()+c.winfo_width()+8
                y=tree.bbox(iid)[1]+tree.bbox(iid)[3]//2
            stamp+=1000
            for tick in (stamp,stamp+100):
                target.event_generate('<ButtonPress-1>',x=x,y=y,time=tick)
                target.event_generate('<ButtonRelease-1>',x=x,y=y,time=tick+20)
                settle(app,.04)
            settle(app,.2)
        alpha=node(root/'Alpha')
        assert not tree.item(alpha,'open')
        double(alpha)
        assert tree.item(alpha,'open') and app.active.path==root/'Alpha'
        assert nav._current_node==alpha
        for region in ('text','icon','connector'):
            double(alpha,region)
            assert not tree.item(alpha,'open'), region
            path=app.active.path; selection=tree.selection(); position=tree.yview()
            for _ in range(3):app.save_config();nav.sync(path);settle(app)
            assert not tree.item(alpha,'open'), 'Autosave must not undo collapse'
            assert tree.selection()==selection and tree.yview()==position, 'No tree reset/jump'
            assert app.active.path==path
            double(alpha,region)
            assert tree.item(alpha,'open'), region
        # Keyboard collapse must also survive background synchronization.
        tree.focus(alpha);tree.focus_set()
        tree.event_generate('<KeyPress-Left>');settle(app)
        app.save_config();settle(app)
        assert not tree.item(alpha,'open')
        double(alpha)
        nav.expand_all_button.invoke()
        double(alpha)
        assert not nav.expand_all_var.get() and not nav._bulk_running
        assert not tree.item(alpha,'open')
        app.active.navigate(root);settle(app)
        beta=node(root/'Beta');tree.item(beta,open=False)
        double(beta,'icon')
        assert app.active.path==root/'Beta' and tree.item(beta,'open')
        # A different folder is still revealed/expanded on real navigation.
        app.active.navigate(root/'Beta'/'Child');settle(app)
        assert tree.item(node(root/'Beta'),'open')
        assert tree.selection()==(node(root/'Beta'/'Child'),)
        assert not errors,errors
        print('PASS: real text/icon/connector double clicks, open/close stability, no autosave reset, '
              'keyboard collapse, Expand All cancellation and new-folder reveal',flush=True)
    finally:app.close_app()
