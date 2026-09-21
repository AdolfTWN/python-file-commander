"""One-panel shared-tab layout, navigation, restoration and explicit targets."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')


def settle(app, seconds=.12):
    end = time.monotonic()+seconds
    while time.monotonic()<end: app.update(); time.sleep(.01)


def dispose(app):
    # Recreate a Tk interpreter in this test process without delivering callbacks
    # belonging to its predecessor (normal application exit ends the process).
    # Cancel delivery without deleting commands registered on child widgets;
    # those widgets own their command cleanup during destroy().
    for job in app.tk.call('after','info'): app.tk.call('after', 'cancel', job)
    app.destroy()


with tempfile.TemporaryDirectory() as raw:
    root = Path(raw)
    for name in ('A','B','C','D','Destination'):
        (root/name).mkdir()
        (root/name/'file.txt').write_text('fixture')
    (root/'A'/'child').mkdir()
    pfc.Commander._find_ini_path = staticmethod(lambda:root/'pfc.ini')
    pfc.Commander._sync_auto_start = lambda self,**kw:True
    app = pfc.Commander(); errors=[]
    app.report_callback_exception = lambda *exc:errors.append(str(exc))
    try:
        app.geometry('1400x800+0+0'); app.auto_font_size_var.set(False)
        left,right,third,_ = app.panel_tabs
        left.current().navigate(root/'A'); right.current().navigate(root/'B')
        extra=right.add_tab(root/'C'); third.current().navigate(root/'D')
        right.set_color(extra,'orange'); right.set_lock(extra,'reset')
        extra.set_quick_filter('file')
        app.panel_count_var.set(3); app.apply_panel_count(); settle(app)
        before=[list(t.panes()) for t in app.panel_tabs]
        app.set_active(extra)
        app.panel_count_var.set(1); app.apply_panel_count(); settle(app)
        assert app._single_layout
        assert app.single_tabs._tabs == before[0]+before[1]+before[2]
        assert len(app.visible_panel_tabs())==1 and app.visible_panes()==[extra]
        assert app.single_tabs.winfo_width()>app.split.winfo_width()*.95
        assert .28 < app.split.sashpos(0)/app.split.winfo_width() < .38
        assert all(not t.bar.winfo_viewable() for t in app.panel_tabs)
        assert extra.quick_filter_var.get()=='file' and extra.archive_session is None
        nav = app.folder_tree
        active_node = nav.nodes[os.path.normcase(str(extra.path))]
        assert nav.tree.item(active_node, 'open'), 'Active folder expands by default'
        assert nav.loaded == {active_node}, 'Only the active directory is scanned, never the whole disk'
        for item in app.folder_tree.paths:
            if app.folder_tree.tree.item(item, 'open'):
                assert all(child in app.folder_tree.paths for child in app.folder_tree.tree.get_children(item))
        extra.navigate(root/'A'/'child')
        app.single_tabs.select(left.current()); settle(app)
        assert extra.path==root/'C', 'Cross-group reset tab must restore on leaving'
        assert app.active is left.current()
        app.single_tabs.select(right.panes()[0]); settle(app)
        assert app.active.path==root/'B'
        assert tuple(app.split.panes())==(str(app.folder_tree),str(right))
        assert app.active is right.current(), 'Displayed file list must match the shared tab'
        # New tabs from P2 go into P1, while old ownership/metadata remain intact.
        app.new_tab(); settle(app)
        added=app.active
        assert added in left.panes() and added not in right.panes()
        assert added in app.single_tabs._tabs
        assert right._colors[extra]=='orange' and extra.lock_mode=='reset'
        app.new_tab(); settle(app)
        disposable=app.active
        app.close_tab(); settle(app)
        assert disposable not in app.single_tabs._tabs
        assert app.active is app._tabs_for(app.active).current()
        app.single_tabs.select(extra); settle(app)
        expected=app.single_tabs._tabs[(app.single_tabs.index(extra)+1)%len(app.single_tabs._tabs)]
        app.switch_tab(1); settle(app)
        assert app.active is expected
        # Shared menu callbacks update the original pane's records.
        app.single_tabs.set_color(extra,'purple')
        assert right._colors[extra]=='purple'
        app.single_tabs.reorder(extra,0); settle(app)
        assert app.single_tabs._tabs[0] is extra
        assert right.panes()==before[1], 'Shared reordering must not scramble original groups'
        # Lazy one-level load and tree selection.
        app.single_tabs.select(added); added.navigate(root/'A'); settle(app)
        iid=app.folder_tree.nodes[os.path.normcase(str(root/'A'))]
        app.folder_tree.load(iid)
        settle(app,.4)
        child=app.folder_tree.nodes[os.path.normcase(str(root/'A'/'child'))]
        app.folder_tree.tree.selection_set(child); settle(app)
        assert app.active.path==root/'A'/'child'
        added.navigate(root/'A'); added.select_path(root/'A'/'file.txt'); settle(app)
        with patch.object(pfc.filedialog,'askdirectory',return_value=''), patch.object(app,'_execute_transfer') as transfer:
            app.copy(); app.move(); transfer.assert_not_called()
        with patch.object(pfc.filedialog,'askdirectory',return_value=str(root/'Destination')), patch.object(app,'_execute_transfer') as transfer:
            app.copy(); assert transfer.call_args.args[3]==root/'Destination'
            app.move(); assert transfer.call_args.args[0]=='Move'
        with patch.object(pfc.filedialog,'askopenfilename',return_value=str(root/'B'/'file.txt')), patch.object(app,'compare_paths') as compare:
            app.compare_selected(); compare.assert_called_once_with(root/'A'/'file.txt',root/'B'/'file.txt')
        assert 'P2' not in app.action_button_by_hotkey['F5'].cget('text')
        # Activate the toplevel first, as a real user click does. Forcing X input
        # focus directly to a child races native FocusIn delivery under Xvfb.
        app.focus_force(); settle(app, .2)
        app.folder_tree.tree.focus_set(); settle(app)
        assert app.focus_get() is app.folder_tree.tree, (app.focus_get(), app.folder_tree.tree, app._single_layout)
        with patch.object(app,'delete') as delete:
            app.delete_hotkey(permanent=True); delete.assert_not_called()
        # Saved divider and shared ordering; normal groups remain untouched.
        app.split.sashpos(0,round(app.split.winfo_width()*.4)); app._remember_tree_ratio()
        for count in (2,4,1,3,1):
            app.panel_count_var.set(count); app.apply_panel_count(); settle(app)
            if count!=1:
                assert len(app.split.panes())==count
                assert all(t.bar.winfo_viewable() for t in app.panel_tabs[:count])
                assert right.panes()==before[1]
        app.single_tabs.select(extra); app.save_config()
        assert not errors,errors
    finally: dispose(app)
    app = pfc.Commander()
    try:
        settle(app)
        assert app.panel_count_var.get()==1 and app._single_layout
        assert app.active.path==root/'C' and app._tabs_for(app.active) is app.right_tabs
        assert app.active.lock_mode=='reset'
        assert app.right_tabs._colors[app.active]=='purple'
        assert abs(app._tree_ratio-.4)<.02
        app.panel_count_var.set(3); app.apply_panel_count(); settle(app)
        assert [p.path for p in app.right_tabs.panes()]==[root/'B',root/'C']
        print('PASS: shared tabs/layout, lazy folder tree, owner restoration/restart, lock state, '
              'new tabs in P1, explicit/cancelled operation targets, saved divider and metadata')
    finally: dispose(app)
