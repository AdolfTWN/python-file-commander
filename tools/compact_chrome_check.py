"""Task-based checks of content-fit zoom and grouped popup toolbars."""
import importlib
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'pycommander.app')


def pump(app, seconds=.4):
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        app.update()
        time.sleep(.01)


def auto_settle(app):
    """Wait for the bounded fit/verification, not a machine-speed assumption."""
    pump(app, .5)
    deadline = time.monotonic()+8
    while app._auto_font_job is not None or app._auto_font_busy:
        assert time.monotonic() < deadline, 'Auto did not finish its bounded fit'
        pump(app, .1)


def shot(win, name):
    if '--screenshots' in sys.argv or '--before' in sys.argv:
        from PIL import ImageGrab
        x, y = win.winfo_rootx(), win.winfo_rooty()
        ImageGrab.grab(bbox=(x, y, x+win.winfo_width(), y+win.winfo_height())).save(
            '/tmp/pfc-'+name+('-before' if '--before' in sys.argv else '-after')+'.png')


with tempfile.TemporaryDirectory(prefix='pfc-chrome-') as raw:
    root = Path(raw)
    pfc.Commander._find_ini_path = staticmethod(lambda: root/'pfc.ini')
    pfc.Commander._sync_auto_start = lambda *a, **kw: True
    pfc.Commander._start_windows_tray = lambda *a: None
    app = pfc.Commander()
    errors = []
    app.report_callback_exception = lambda *exc: errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False)
        app.geometry('1400x900+0+0')
        folder = root/'Documents'; folder.mkdir()
        for i in range(60):
            (folder/f'{i:02} Project Notes.md').write_text('# Project\n\nSample alpha Alpha\n')
        for pane in app.visible_panes(): pane.navigate(folder)
        app.font_size_var.set('large'); app.apply_font_size(save=False)
        app.search(); pump(app)
        win = app.search_window; win.geometry('1100x760+0+0'); pump(app)
        shot(win, 'search-chrome')
        if '--before' not in sys.argv:
            assert win.tree.winfo_rooty()-win.winfo_rooty() < 230
            for entry, related in win.query_rows:
                assert abs(entry.winfo_rooty()-related.winfo_rooty()) < 12
                assert entry.winfo_width() >= 80
            win.toggle_filters(); pump(app)
            assert win.advanced.winfo_ismapped()
            win.min_size_var.set('1'); win.toggle_filters()
            assert win.min_size_var.get() == '1'
            win.clear_filters()
            win.mask_var.set('Project'); win.content_var.set('alpha'); win.start(); pump(app, 1.5)
            assert len(win.results) == 60, len(win.results)
        win.close(); app.search_window = None
        if '--before' not in sys.argv:
            for level in ('small', 'large', 'xl'):
                app.font_size_var.set(level); app.apply_font_size(save=False)
                app.search(); win = app.search_window
                win.geometry('760x680+0+0'); pump(app)
                assert win.results_button.winfo_rootx()+win.results_button.winfo_width() <= win.winfo_rootx()+win.winfo_width()
                assert all(e.winfo_width() >= 60 for e, _ in win.query_rows), level
                win.close(); app.search_window = None
                compare = pfc.CompareWindow(app, app.config_data, lambda: None)
                first = folder/'00 Project Notes.md'; second = folder/'01 Project Notes.md'
                frame = compare.add(first, second)
                compare.apply_scale(app._font_scales[level])
                compare.geometry('760x680+0+0'); pump(app)
                view = frame.view
                assert view.search.winfo_width() >= 70, (level, view.search.winfo_width())
                assert abs(view.search.winfo_rooty()-view.case_button.winfo_rooty()) < 12
                if level == 'large': shot(compare, 'compare-chrome')
                compare.close()
                rename = pfc.MultiRenameWindow(app, [first, second], [], lambda: None)
                rename.geometry('760x680+0+0'); pump(app)
                assert rename.mask_entry.winfo_width() >= 80
                if level == 'large': shot(rename, 'rename-chrome')
                rename.destroy()
                space = pfc.SpaceAnalyzerWindow(app, folder, lambda p: None, lambda p: None, app.palette)
                space.geometry('760x680+0+0'); pump(app)
                assert space.path_entry.winfo_width() >= 100
                assert space.canvas.winfo_rooty()-space.winfo_rooty() < 90
                if level == 'large': shot(space, 'space-chrome')
                space.close()
            app.font_size_var.set('small'); app.apply_font_size(save=False)
            app.auto_font_size_var.set(True); app.set_auto_font_size(); pump(app, 2)
            scale = app.font_size_var.get()
            samples = app._auto_font_samples()
            assert samples and all(len(rows) == 30 for _, rows in samples)
            assert scale != 'small', (scale, [p.tree.winfo_width() for p, _ in samples])
            assert all(not p.name_marquee.clipped(i) for p, rows in samples for i, _, _ in rows), scale
            pump(app, 1); assert app.font_size_var.get() == scale, 'Auto oscillated'
            app.geometry('950x700+0+0'); pump(app, 2)
            assert app._font_scales[app.font_size_var.get()] <= app._font_scales[scale]
            assert not app._auto_font_busy
            shot(app, 'auto-fit')
            short = root/'Short'; short.mkdir()
            for i in range(35): (short/f'{i:02}.txt').write_text('short')
            long = root/'Long'; long.mkdir()
            (long/('long_name_'*18+'.txt')).write_text('long')
            app.geometry('1760x950+0+0')
            for count in (1, 2, 3, 4):
                app.panel_count_var.set(count); app.apply_panel_count(save=False)
                for pane in app.visible_panes(): pane.navigate(short)
                app.set_auto_font_size(); auto_settle(app)
                chosen = app.font_size_var.get()
                assert app._font_scales[chosen] >= 1
                if count >= 3:
                    for pane in app.visible_panes()[2:]: pane.navigate(long)
                    pump(app, 1)
                    assert app.font_size_var.get() == chosen, 'Panel 3/4 must not constrain Auto'
                # No sampling or global font redraw is allowed during browsing.
                sample_calls, apply_calls = [], []
                original_sample, original_apply = app._auto_font_samples, app.apply_font_size
                def sampled():
                    sample_calls.append(1)
                    return original_sample()
                def applied(*args, **kw):
                    apply_calls.append(1)
                    return original_apply(*args, **kw)
                app._auto_font_samples, app.apply_font_size = sampled, applied
                pane = app.visible_panes()[0]; pane.navigate(long); pump(app, 1)
                assert app.font_size_var.get() == chosen, ('navigation must stay stable', count)
                pane.tree.yview_moveto(1); pane.tree.event_generate('<ButtonRelease-1>', x=20, y=65)
                pane.refresh(); pump(app, 1)
                pane.navigate(short); pump(app, 2)
                pane.tree.yview_moveto(.5); pump(app, .5)
                tabs = app._tabs_for(pane)
                tabs.add_tab(long); pump(app, .6)
                tabs.select(pane); pump(app, .6)
                assert app.font_size_var.get() == chosen
                assert not sample_calls and not apply_calls, (count, sample_calls, apply_calls)
                # Height-only and same-monitor moves must not inspect filenames.
                app.geometry('1760x800+10+10'); pump(app, 1)
                assert not sample_calls and not apply_calls, ('height/move', count)
                app._auto_font_samples, app.apply_font_size = original_sample, original_apply
                pane.navigate(long); pump(app, .5)
                app.set_auto_font_size(); auto_settle(app)
                assert app.font_size_var.get() == 'small', ('explicit refit floor', count)
                pane.navigate(short); pump(app, .5)
                app.set_auto_font_size(); auto_settle(app)
                # Width changes remain real fit triggers; navigation does not.
                app._auto_font_samples = sampled
                sample_calls.clear()
                app.geometry('1450x800+10+10'); auto_settle(app)
                assert not app._auto_font_busy
                assert sample_calls, ('width must refit', count)
                app._auto_font_samples = original_sample
                app.geometry('1760x950+0+0'); auto_settle(app)
                print('PASS: stable Auto browsing/scroll/refresh/tab/height; width refit; panels', count,
                      'navigation sample calls', 0, 'global font applies', 0)
            app.auto_font_size_var.set(False)
            app.font_size_var.set('large'); app.apply_font_size(save=False)
            for lang, theme in (('zh_TW', 'dark'), ('zh_CN', 'light')):
                pfc.set_language(lang)
                app.color_scheme_var.set(theme); app.apply_color_scheme(save=False)
                app.search(); win = app.search_window; win.geometry('760x680+0+0'); pump(app)
                assert all(e.winfo_width() >= 60 for e, _ in win.query_rows)
                shot(win, 'search-'+lang)
                win.close(); app.search_window = None
                pump(app)
                app.active.tree.focus_force()
                app.active.tree.event_generate('<Motion>', warp=True, x=5, y=5)
                pump(app); shot(app, 'zoom-'+theme)
                before = (app.zoom_frame.winfo_width(), app.zoom_frame.winfo_height())
                app.zoom_plus.event_generate('<Motion>', warp=True, x=5, y=5)
                pump(app)
                assert str(pfc.ttk.Style(app).lookup('Zoom.TButton', 'relief')) == 'raised'
                assert before == (app.zoom_frame.winfo_width(), app.zoom_frame.winfo_height())
                shot(app, 'zoom-hover-'+theme)
            pfc.set_language('en')
        assert not errors, errors
        print('PASS: popup chrome fixture')
    finally:
        app.close_app()
