"""User tasks and measured chrome at wide/narrow reading scales, no user data."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')
baseline = '--baseline' in sys.argv


def pump(app, seconds=.25):
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        app.update()
        time.sleep(.01)


def capture(window, name):
    window.lift(); pump(window)
    if os.name == 'nt':
        from folder_native_test_support import capture_window
        capture_window(window, Path(__file__).parent/('evidence-compact-'+name+'.bmp'))
    else:
        from PIL import ImageGrab
        x, y = window.winfo_rootx(), window.winfo_rooty()
        ImageGrab.grab((x, y, x+window.winfo_width(), y+window.winfo_height())).save(
            '/tmp/pfc-compact-'+name+('-before' if baseline else '-after')+'.png')


def inside(widget, window):
    assert widget.winfo_ismapped(), str(widget)
    assert window.winfo_rootx() <= widget.winfo_rootx()
    assert widget.winfo_rootx()+widget.winfo_width() <= window.winfo_rootx()+window.winfo_width()+2, str(widget)


def toolbar_usable(bar, window):
    for group, _, _ in bar.groups:
        inside(group, window)
        pending = [group]
        while pending:
            widget = pending.pop(); pending.extend(widget.winfo_children())
            if widget.winfo_ismapped() and isinstance(widget, (pfc.ttk.Button,pfc.ttk.Entry,pfc.ttk.Checkbutton,pfc.ttk.Menubutton)):
                inside(widget, window)
    snapshot=(tuple(tuple(r) for r in bar.rows),bar.winfo_height())
    pump(window)
    assert snapshot==(tuple(tuple(r) for r in bar.rows),bar.winfo_height()), 'Layout oscillated'


with tempfile.TemporaryDirectory(prefix='pfc-compact-tasks-') as raw:
    root = Path(raw)
    files = [root/'Project notes.md', root/'Project revised.md']
    for i, path in enumerate(files):
        path.write_text('# Project\n\n- [ ] Review\n\n' + ('alpha beta\n' if i else 'alpha gamma\n')*30)
    structured = root/'report.json'
    structured.write_text(json.dumps({'devices': [{'name': 'alpha', 'status': 'ready'}]*20}))
    pfc.Commander._find_ini_path = staticmethod(lambda: root/'pfc.ini')
    pfc.Commander._sync_auto_start = lambda *a, **kw: True
    pfc.Commander._start_windows_tray = lambda *a: None
    app = pfc.Commander(); errors = []
    app.report_callback_exception = lambda *exc: errors.append(str(exc))
    measurements = []
    try:
        app.auto_font_size_var.set(False)
        app.active.navigate(root)
        for scale, width, language in [('small', 1600, 'en'), ('large', 1280, 'en'),
                                       ('xl', 760, 'zh_TW')]:
            app.ui_language_var.set(language); app.apply_ui_language()
            app.font_size_var.set(scale); app.apply_font_size(save=False); pump(app)
            app.search(); search = app.search_window
            search.geometry(f'{width}x850+0+0'); pump(app)
            measurements.append(dict(view='search', scale=scale, width=width,
                chrome=search.tree.winfo_rooty()-search.winfo_rooty(),
                action_rows=len({b.winfo_y() for b in search.result_buttons})))
            if not baseline:
                for b in search.result_buttons:
                    inside(b, search)
                    assert b.winfo_width()>=pfc.tkfont.nametofont('TkDefaultFont').measure(b.cget('text'))+12
                toolbar_usable(search.result_actions,search)
                assert not search.progress_eta.winfo_ismapped(), 'Empty elapsed row reserves space'
                assert all(e.winfo_width() >= 60 for e, _ in search.query_rows)
                search.mask_var.set('*.md'); search.start()
                deadline = time.monotonic()+12
                while search.worker is not None:
                    assert time.monotonic() < deadline
                    pump(app, .05)
                assert len(search.results) == 2
                assert search.search_state == 'complete'
            if scale == 'large': capture(search, 'search')
            search.close(); app.search_window = None
            app.preview_paths([*files, structured], structured)
            win = app.preview_window; win.geometry(f'{width}x850+0+0'); pump(app, 1)
            page = win.active_page
            measurements.append(dict(view='preview', scale=scale, width=width,
                chrome=page.activity_controls.winfo_rooty()-page.file_row.winfo_rooty()))
            if not baseline:
                inside(page.search, win)
                assert page.search.winfo_width() >= 70
                toolbar_usable(page.reading_tools,win)
                if scale=='small':
                    assert len(page.reading_tools.rows)==1, 'Wide reading toolbar still wraps'
                    capture(win,'wide')
                if scale=='xl':capture(win,'narrow')
                page.search_var.set('alpha'); page.find_all_matched(); pump(app, 1)
                assert page.markdown_var.get() == pfc.tr('Rendered')
                assert page.render_view.model.get('kind') == 'tree'
                if scale=='small':
                    tree=page.render_view.tree
                    selection=tree.selection()
                    rendered=page.render_view.model
                    search_widget=page.search
                    for new_width in (1000,1600,1000,1600):
                        win.geometry(f'{new_width}x850+0+0');pump(app)
                        toolbar_usable(page.reading_tools,win)
                        assert page.search is search_widget
                        assert page.render_view.model is rendered and tree.selection()==selection
                        assert page.search_var.get()=='alpha'
            if scale == 'large': capture(win, 'preview')
            win.close(); app.preview_window = None
            compare = pfc.CompareWindow(app, app.config_data, lambda: None)
            frame = compare.add(*files); compare.apply_scale(app._font_scales[scale])
            compare.geometry(f'{width}x850+0+0'); pump(app)
            measurements.append(dict(view='compare', scale=scale, width=width,
                chrome=frame.view.body.winfo_rooty()-frame.view.winfo_rooty()))
            if not baseline:
                inside(frame.view.search, compare)
                assert frame.view.search.winfo_width() >= 70
                toolbar_usable(frame.view.navigation_tools,compare)
                if scale=='small':assert len(frame.view.navigation_tools.rows)==1
                frame.view.search_var.set('alpha'); frame.view.find_next(); pump(app)
            if scale == 'large': capture(compare, 'compare')
            compare.close()
            rename = pfc.MultiRenameWindow(app, files, [], lambda: None)
            rename.geometry(f'{width}x850+0+0'); pump(app)
            measurements.append(dict(view='rename', scale=scale, width=width,
                chrome=rename.tree.winfo_rooty()-rename.winfo_rooty()))
            if not baseline:
                inside(rename.mask_entry, rename)
                assert rename.mask_entry.winfo_width() >= 80
                toolbar_usable(rename.naming_tools,rename)
                toolbar_usable(rename.replace_tools,rename)
                rename.mask_var.set('[N]_[C]'); pump(app)
                assert len(rename.tree.get_children()) == 2
            if scale == 'large': capture(rename, 'rename')
            rename.destroy()
            if not baseline:
                app.show_settings();settings=app.settings_window
                settings.geometry(f'{width}x850+0+0');pump(app)
                for category,_ in pfc.SETTINGS_CATEGORIES:
                    settings.show_page(category);pump(app,.1)
                    assert settings.footer.winfo_ismapped()
                    if category in ('general','navigation'):
                        assert not settings.comparison.winfo_ismapped()
                        saved={k:v.get() for k,v in settings.vars.items()}
                        settings.preview_toggle.invoke();pump(app,.1)
                        assert settings.comparison.winfo_ismapped()
                        settings.preview_toggle.invoke();pump(app,.1)
                        assert saved=={k:v.get() for k,v in settings.vars.items()}
                    for label,control in settings._compact_controls:
                        assert control.winfo_width()>=70
                        if settings.canvas.winfo_width()>=label.winfo_reqwidth()+settings.font.measure('M'*12)+70:
                            assert abs(label.winfo_y()-control.winfo_y())<8
                    if scale=='large' and category=='general':capture(settings,'settings')
                settings.cancel()
        assert not errors, errors
        print(json.dumps(measurements))
        print('PASS: compact search/preview/compare/rename user tasks')
    finally:
        app.close_app()
