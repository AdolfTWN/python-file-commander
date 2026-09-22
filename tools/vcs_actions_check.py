"""F8 scope, async menus, responsive bar and safe dialog hand-off; package/portable."""
import importlib
import inspect
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'pycommander.app')
ui = inspect.getmodule(pfc.VcsActions)


def settle(app, duration=.35):
    until = time.monotonic() + duration
    while time.monotonic() < until:
        app.update(); time.sleep(.01)


def labels(menu):
    return [menu.entrycget(i, 'label') for i in range((menu.index('end') or 0) + 1)
            if menu.type(i) != 'separator']


with tempfile.TemporaryDirectory() as raw:
    root = Path(raw); repo = root / 'repo'; repo.mkdir(); (repo / '.git').mkdir()
    item = repo / 'literal space & name.txt'; item.write_text('fixture')
    other = root / 'other'; other.mkdir(); (other / '.svn').mkdir()
    pfc.Commander._find_ini_path = staticmethod(lambda: root / 'pfc.ini')
    pfc.Commander._sync_auto_start = lambda self, **kw: True
    pfc.Commander._start_windows_tray = lambda self: None
    app = pfc.Commander(); errors = []
    app.report_callback_exception = lambda *exc: errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False); app.geometry('1500x900+0+0')
        app.active.navigate(repo); app.active.select_path(item); app.active.tree.focus_force()
        settle(app, .8)
        controller = app.vcs_actions
        assert controller.context.location.kind == 'git'
        assert not app.action_button_by_hotkey['F8'].instate(['disabled'])
        assert 'Git' in app.action_button_by_hotkey['F8'].cget('text')
        app.vcs_overlay_var.set(False); app.set_vcs_overlay(); settle(app)
        assert not app.action_button_by_hotkey['F8'].instate(['disabled'])
        controller.show(); settle(app, .6)
        menu = controller.quick_menu
        assert pfc.tr('Commit selected…') in labels(menu)
        assert pfc.tr('Push current branch…') in labels(menu)
        assert app.header_popup.popups[0].menu is menu
        assert (app.header_popup.popups[0].top.winfo_rooty() + app.header_popup.popups[0].height
                <= app.action_button_by_hotkey['F8'].winfo_rooty())
        popup_id = str(app.header_popup.popups[0].top)
        # A live summary updates one canvas, never replaces the popup/grab.
        controller._summary(menu, controller.context, None)
        assert str(app.header_popup.popups[0].top) == popup_id
        app.header_popup.close_all()
        context = controller.context
        calls = []
        controller.clients['git'] = 'C:/Tools/TortoiseGitProc.exe'
        class Process:
            def poll(self): return None
        with patch.object(ui.os, 'name', 'nt'), patch.object(ui.subprocess, 'Popen',
                side_effect=lambda command, **kw: (calls.append((command, kw)) or Process())):
            for action in ('commit', 'push', 'log', 'revisiongraph'):
                controller.launch(context, action)
        assert '/path:' + str(item) in calls[0][0]
        assert '/path:' + str(repo) in calls[1][0]
        assert '/path:' + str(item) in calls[2][0]
        assert all(not kw.get('shell') for _, kw in calls)
        controller.processes.clear()
        # Cross-repo selections retain history but cannot commit/push together.
        mixed = ui.vcs_context((item, other), item)
        m = controller.build_menu(app)
        controller._populate(m, controller.snapshot(), mixed)
        for label in ('Commit selected…', 'Commit entire working copy…', 'Push current branch…'):
            index = next(i for i in range(m.index('end')+1) if m.type(i) != 'separator' and m.entrycget(i,'label') == pfc.tr(label))
            assert m.entrycget(index, 'state') == 'disabled'
        m.destroy()
        # A stale result cannot change the new active context.
        app.active.navigate(other); controller.request(tree=False); settle(app, .9)
        assert controller.context.location.kind == 'svn'
        controller.show(); settle(app, .4)
        assert pfc.tr('Push current branch…') not in labels(controller.quick_menu)
        assert pfc.tr('Show History (may use network)') in labels(controller.quick_menu)
        app.header_popup.close_all()
        app.active.navigate(repo / '.git'); settle(app, .6)
        app.active.tree.selection_remove(*app.active.tree.selection()); app.active.tree.focus('')
        controller.request(tree=False); settle(app, .5)
        assert app.action_button_by_hotkey['F8'].instate(['disabled']), (controller.snapshot(), controller.key, controller.context, controller.pending)
        # 1–4 panels and supported scales: single line, no overlap with zoom.
        for language in ('en', 'zh_TW', 'zh_CN'):
            pfc.set_language(language); app.action_bar.localize()
            for count in (1, 2, 3, 4):
                app.panel_count_var.set(count); app.apply_panel_count(save=False)
                for scale in ('small', 'large', '175', 'xl'):
                    app.font_size_var.set(scale); app.apply_font_size(save=False)
                    for width in (1050, 1600):
                        app.geometry(f'{width}x850+0+0'); settle(app, .07)
                        previous = 0
                        rows = set()
                        for button, key, _ in app.action_buttons:
                            x = button.winfo_rootx(); rows.add(button.winfo_rooty())
                            assert x >= previous, (key, x, previous)
                            previous = x + button.winfo_width()
                            assert previous <= app.zoom_frame.winfo_rootx(), (language, count, scale, width, key)
                            assert key in button.cget('text')
                        assert len(rows) == 1
        pfc.set_language('en'); app.action_bar.localize()
        # Tree target, not the previously focused file row.
        app.panel_count_var.set(1); app.apply_panel_count(save=False)
        app.active.navigate(repo); settle(app, .4)
        app.folder_tree.tree.focus_force(); controller.request(tree=True); settle(app, .7)
        assert controller.context.focus == repo
        assert controller.context.paths == (repo,)
        # Non-main windows cannot accidentally invoke the hidden main F8 action.
        window = pfc.tk.Toplevel(app); window.focus_force(); settle(app)
        old = getattr(controller, 'quick_menu', None)
        controller.show()
        assert getattr(controller, 'quick_menu', None) is old
        window.destroy()
        assert not errors, errors
        print('PASS: F8 context/status, scoped GUI commands, Git/SVN menus, no writes, tree focus, '
              'three languages / 1–4 panels / 100–200% responsive bar, popup reuse, child-window guard')
    finally:
        app.header_popup.close_all(); app.destroy()
