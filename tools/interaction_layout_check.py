"""Real widget event routes, external folder changes and readable scaled dialogs."""
import importlib
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'pycommander.app')


def pump(app, seconds=.15):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        time.sleep(.01)


with tempfile.TemporaryDirectory(prefix='pfc-interaction-') as raw:
    root = Path(raw)
    pfc.Commander._find_ini_path = staticmethod(lambda: root/'pfc.ini')
    pfc.Commander._sync_auto_start = lambda *a, **kw: True
    pfc.Commander._start_windows_tray = lambda *a: None
    app = pfc.Commander()
    errors = []
    app.report_callback_exception = lambda *exc: errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False)
        app.font_size_var.set('large'); app.apply_font_size(save=False)
        app.geometry('1200x800+0+0')
        if '--before' in sys.argv:
            from PIL import ImageGrab
            app.show_settings(); d = app.settings_window
            d.geometry('1040x720+0+0'); d.show_page('layout'); pump(app)
            ImageGrab.grab().save('/tmp/pfc-layout-before.png')
            d.cancel()
        else:
            folder = root/'Downloads'; folder.mkdir()
            long = folder/('very_long_readable_filename_'*6+'.txt'); long.write_text('sample')
            pane = app.active; pane.navigate(folder); pane.tree.focus_force(); pump(app)
            pane.select_path(long); pane.name_marquee.request(); pump(app)
            m = pane.name_marquee; tree = pane.tree
            assert m.item and m.canvas.winfo_ismapped()
            opened = []; pane.on_open_file = lambda pane, path: opened.append(path) or True
            # Send to the actual overlay, not directly to its forwarding helper.
            # Tk sees the original canvas events as well as forwarded tree events.
            x, y = m.canvas.winfo_rootx()+8, m.canvas.winfo_rooty()+8
            for stamp in (20000, 20120):
                target = m.canvas if m.canvas.winfo_ismapped() else tree
                options = dict(x=x-target.winfo_rootx(), y=y-target.winfo_rooty(), time=stamp)
                target.event_generate('<ButtonPress-1>', **options)
                target.event_generate('<ButtonRelease-1>', **dict(options, time=stamp+20))
                pump(app, .04)
            assert opened == [long], opened
            pump(app, .3)
            (folder/'downloaded.txt').write_text('new download')
            (folder/'extracted').mkdir()
            pump(app, 2.8)
            names = {p.name for p in (Path(tree.item(i, 'tags')[0]) for i in tree.get_children())}
            assert {'downloaded.txt', 'extracted'} <= names, names
            assert pane.selected_paths() == [long]
            for scale in ('small', 'large', '175', 'xl'):
                app.font_size_var.set(scale); app.apply_font_size(save=False)
                app.show_settings(); d = app.settings_window
                d.geometry('1040x720+0+0')
                for category, _ in pfc.SETTINGS_CATEGORIES:
                    d.show_page(category); pump(app)
                    assert d.footer.winfo_y()+d.footer.winfo_height() <= d.winfo_height()
                    if d._whole_page_scroll:
                        assert abs(d.comparison.winfo_rooty()-d.canvas.winfo_rooty()) <= 3, (scale, category, d.canvas.yview())
                    for preview, _ in d.layout_examples:
                        assert preview.winfo_rootx()+preview.winfo_width() <= d.comparison.winfo_rootx()+d.comparison.winfo_width()+2, (scale, category, preview.winfo_width(), d.comparison.winfo_width())
                        assert preview.title.winfo_reqwidth() <= preview.winfo_width()+2
                    if '--screenshots' in sys.argv and scale == 'large':
                        from PIL import ImageGrab
                        ImageGrab.grab().save('/tmp/pfc-settings-'+category+'-after.png')
                d.cancel()
            md = folder/'Notes.md'; md.write_text('# Notes\n\nalpha Alpha\n\n| Item | Status |\n| --- | --- |\n| Check | Done |\n')
            app.preview_paths([md], md); win = app.preview_window
            for scale in ('small', 'large', 'xl'):
                app.font_size_var.set(scale); app.apply_font_size(save=False)
                for width in (1100, 680):
                    win.geometry(f'{width}x680+0+0'); pump(app, .4)
                    page = win.active_page
                    assert abs(page.search.winfo_rooty()-page.find_prev_button.winfo_rooty()) < 12
                    assert page.search.winfo_rootx()+page.search.winfo_width() <= page.find_prev_button.winfo_rootx()
                    assert page.case_check.winfo_ismapped()
                    assert page.case_check.winfo_rootx()+page.case_check.winfo_width() <= win.winfo_rootx()+win.winfo_width()
                    assert page.search.winfo_width() >= 60
                    assert page.wrap_check.winfo_height() >= 24
                    assert page.markdown_check.winfo_ismapped()
                    assert page.markdown_check.winfo_rootx()+page.markdown_check.winfo_width() <= win.winfo_rootx()+win.winfo_width()
                    if '--screenshots' in sys.argv and scale == 'large':
                        from PIL import ImageGrab
                        ImageGrab.grab().save(f'/tmp/pfc-preview-{width}-after.png')
            page.markdown_var.set(pfc.tr('Markdown Source')); page.load(); pump(app, 1)
            assert '# Notes' in page.text.get('1.0', 'end')
            page.markdown_check.invoke(); pump(app, 1)
            assert '# Notes' not in page.text.get('1.0', 'end')
            page.search_var.set('alpha'); page.find_all()
            assert len(page.matches) == 2
            page.case_check.invoke(); assert len(page.matches) == 1
            page.wrap_check.invoke(); assert page.text.cget('wrap') == ('word' if page.wrap_var.get() else 'none')
            win.close(); app.preview_window = None
            assert not errors, errors
            print('PASS: overlay double-click, external create/extract visibility and scaled Settings bounds')
    finally:
        d = getattr(app, 'settings_window', None)
        if d is not None and d.winfo_exists(): d.cancel()
        app.close_app()
