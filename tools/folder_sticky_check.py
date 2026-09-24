"""Pinned ancestors follow the scrolled viewport, without scanning or jumping."""
import importlib
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')


def settle(app, seconds=.2):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        app.update();time.sleep(.01)


with tempfile.TemporaryDirectory(prefix='pfc-sticky-') as raw:
    root=Path(raw)
    pfc.Commander._find_ini_path=staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start=lambda self,**kw:True
    pfc.Commander._start_windows_tray=lambda self:None
    app=pfc.Commander();errors=[]
    app.report_callback_exception=lambda *exc:errors.append(str(exc))
    try:
        app.geometry('1450x880+0+0');app.auto_font_size_var.set(False)
        app.panel_count_var.set(1);app.apply_panel_count();settle(app)
        app._sync_single_workspace=lambda:None
        nav=app.folder_tree;tree=nav.tree
        nav.on_navigate=lambda path:None
        for _,_,cancel in nav.pending.values():cancel.set()
        nav.pending.clear()
        tree.delete(*tree.get_children(nav.pc));nav.paths.clear();nav.nodes.clear()
        nav.load=lambda *args,**kwargs:None  # All viewport work must use cached nodes.
        def add(parent,name,path):
            iid=nav._node(path/name,parent)
            tree.delete(*tree.get_children(iid));return iid
        def scroll_to(iid):
            visible=[];pending=list(tree.get_children(''))
            while pending:
                item=pending.pop(0);visible.append(item)
                if tree.item(item,'open'):pending[:0]=tree.get_children(item)
            tree.yview(visible.index(iid))
        drive=add(nav.pc,'Drive',root)
        branches=[]
        for label in ('Projects','Photos'):
            parent=add(drive,label,root/'Drive');branches.append(parent)
            for i in range(60):add(parent,f'Folder {i:02}',root/'Drive'/label)
            tree.item(parent,open=True)
        tree.item(drive,open=True);tree.yview_moveto(0);settle(app)
        assert not nav._sticky.winfo_ismapped()
        tree.yview_scroll(8,'units');settle(app)
        assert nav._sticky_chain==(nav.pc,drive,branches[0]),nav._sticky_chain
        assert len(nav._sticky.find_withtag('ancestor-icon'))==3
        assert len(nav._sticky.find_withtag('ancestor-name'))==3
        # Floating joints use the same horizontal coordinate as ordinary rows.
        x=tree.bbox(nav._visible_nodes[0])[0]
        for depth,icon in enumerate(nav._sticky.find_withtag('ancestor-icon')):
            assert nav._sticky.coords(icon)[0]==round(x+(depth+.5)*nav._line_indent)
        tree.selection_set(branches[1]);settle(app)
        assert nav._sticky_chain[-1]==branches[0], 'Context must not follow selection'
        tree.yview_moveto(.75);settle(app)
        assert nav._sticky_chain[-1]==branches[1]
        for scheme in pfc.COLOR_SCHEMES:
            app.color_scheme_var.set(scheme);app.apply_color_scheme(save=False)
            for zoom in ('small','large','300'):
                app.font_size_var.set(zoom);app.apply_font_size(save=False);settle(app)
                tree.yview_moveto(1);settle(app)
                before=(tree.yview(),nav._sticky_height,nav._sticky_chain)
                settle(app,.3)
                assert before==(tree.yview(),nav._sticky_height,nav._sticky_chain), 'No layout/scroll oscillation'
                assert tree.winfo_height()>=2*tree.bbox(nav._visible_nodes[0])[3]
        app.font_size_var.set('large');app.apply_font_size(save=False)
        tree.yview_moveto(.2);settle(app)
        tree.column('#0',width=1400,stretch=False);tree.xview_moveto(.025);settle(app)
        offset=tree.bbox(nav._visible_nodes[0])[0]
        for depth,icon in enumerate(nav._sticky.find_withtag('ancestor-icon')):
            joint=round(offset+(depth+.5)*nav._line_indent)
            actual=nav._sticky.coords(icon)[0]
            if joint>=nav._icon_size/2:assert actual==joint
            else:assert actual>=nav._icon_size/2
        tree.xview_moveto(0);settle(app)
        # Wheel on floating rows still scrolls the tree, without moving selection.
        before=tree.yview();selected=tree.selection()
        nav._sticky.event_generate('<MouseWheel>',delta=-120);settle(app)
        assert tree.yview()!=before and tree.selection()==selected
        # Clicking a pinned ancestor reveals its actual tree row.
        navigated=[];nav.on_navigate=navigated.append;nav.program_selection=None
        target=nav._sticky_rows[-1]
        nav._sticky.event_generate('<Button-1>',x=40,y=(target[0]+target[1])//2);settle(app)
        assert tree.selection()==(target[2],) and tree.bbox(target[2])
        # Return to top: no duplicated floating roots or dead band.
        tree.yview_moveto(0);settle(app)
        assert not nav._sticky.winfo_ismapped() and nav._sticky_height==0
        # Every ancestor is shown directly, including deep paths; no overflow menu.
        parent=branches[0];path=root/'Deep'
        for n in range(18):
            parent=add(parent,f'Depth {n}',path);path/=f'Depth {n}'
            tree.item(parent,open=True)
        for n in range(35):add(parent,f'Leaf {n}',path)
        scroll_to(parent);tree.yview_scroll(8,'units');settle(app)
        assert len(nav._sticky_chain)>10
        assert tuple(iid for _,_,iid in nav._sticky_rows)==nav._sticky_chain
        assert len(nav._sticky.find_withtag('ancestor-name'))==len(nav._sticky_chain)
        assert len(nav._sticky.find_withtag('ancestor-icon'))==len(nav._sticky_chain)
        assert not nav._sticky.find_withtag('ancestor-overflow')
        assert tree.winfo_height()>=2*tree.bbox(nav._visible_nodes[0])[3]
        assert app.action_button_by_hotkey['F2'].winfo_viewable(), 'All ancestors must not hide the action bar'
        assert nav._horizontal.winfo_viewable(), 'Deep paths must retain horizontal scrolling'
        before=(tree.yview(),nav._sticky_height,nav._sticky_chain)
        settle(app,.4)
        assert before==(tree.yview(),nav._sticky_height,nav._sticky_chain)
        assert nav._sticky.find_withtag('ancestor-offscreen')
        for icon in nav._sticky.find_withtag('ancestor-icon'):
            assert 0<nav._sticky.coords(icon)[0]<nav._sticky.winfo_width()
        if '--deep-visual' in sys.argv:
            print('DEEP VISUAL READY',flush=True);settle(app,25)
        # Restore a clean, representative three-level screenshot.
        tree.item(branches[0],open=False)
        scroll_to(branches[1]);tree.yview_scroll(7,'units');settle(app)
        if '--screenshot' in sys.argv:
            from PIL import ImageGrab
            ImageGrab.grab().save(str(root.parent/'pfc-folder-sticky.png'))
        if '--visual' in sys.argv:
            print('VISUAL READY',flush=True);settle(app,25)
        # Rebuilding the cache must not leave stale floating rows or hover IDs.
        nav.refresh();nav._sticky_motion(type('Event',(),{'y':5})());settle(app)
        assert all(tree.exists(iid) for iid in nav._sticky_chain)
        assert not errors,errors
        print('PASS: sticky viewport ancestors, aligned icons, branch changes, top restore, '
              'theme/zoom, stable bottom scroll, wheel/click and all deep ancestors visible',flush=True)
    finally:app.close_app()
