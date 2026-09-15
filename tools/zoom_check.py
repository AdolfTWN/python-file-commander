"""Global zoom controls, wheel routing, persistence and compact layout."""
import importlib
from pathlib import Path
import sys
import subprocess
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'pycommander.app')

def pump(app):
    end = time.monotonic() + .3
    while time.monotonic() < end:
        app.update()
        time.sleep(.01)

def main():
    if '--restore' in sys.argv:
        saved_root = Path(sys.argv[sys.argv.index('--restore') + 1])
        pfc.Commander._find_ini_path = staticmethod(lambda: saved_root / 'pfc.ini')
        pfc.Commander._sync_auto_start = lambda self, **kwargs: True
        app = pfc.Commander()
        try:
            pump(app)
            assert app.zoom_percent_var.get() == '175%' and not app.auto_font_size_var.get()
        finally:
            app.close_app()
        return
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        pfc.Commander._find_ini_path = staticmethod(lambda: root / 'pfc.ini')
        pfc.Commander._sync_auto_start = lambda self, **kwargs: True
        app = pfc.Commander()
        errors = []
        app.report_callback_exception = lambda *exc: errors.append(str(exc))
        try:
            app.geometry('960x700'); app.font_size_var.set('small'); app.select_manual_font_size()
            pane = app.left_tabs.current()
            for i in range(100): (root / f'{i:03}.txt').write_text('test')
            pane.navigate(root); pump(app)
            events = []
            pane.tree.bind('<MouseWheel>', lambda event: events.append(event.delta), add='+')
            pane.tree.event_generate('<Control-MouseWheel>', delta=120); pump(app)
            assert app.zoom_percent_var.get() == '125%'
            assert not events and not app.auto_font_size_var.get()
            pane.tree.event_generate('<Control-MouseWheel>', delta=120); pump(app)
            assert app.zoom_percent_var.get() == '150%'
            pane.tree.event_generate('<Control-MouseWheel>', delta=-120); pump(app)
            assert app.zoom_percent_var.get() == '125%'
            pane.tree.event_generate('<MouseWheel>', delta=-120); pump(app)
            assert events == [-120]
            for percent in (150, 175, 200, 225, 250, 275, 300):
                app.zoom_plus.invoke(); pump(app)
                assert app.zoom_percent_var.get() == f'{percent}%'
            assert 'disabled' in app.zoom_plus.state()
            compact_width = app.zoom_frame.winfo_width()
            app.zoom_menu.invoke(2); pump(app)
            assert app.zoom_percent_var.get() == '100%'
            assert abs(app.zoom_frame.winfo_width() - compact_width) <= 4
            assert app.zoom_frame.winfo_x() > app.action_button_by_hotkey['F12'].winfo_rootx() - app.actions_frame.winfo_rootx()
            assert app.zoom_frame.winfo_width() <= 110, app.zoom_frame.winfo_width()
            assert len(app.zoom_frame.winfo_children()) == 3
            app.search(); pump(app)
            app.search_window.mask_entry.event_generate('<Control-MouseWheel>', delta=120); pump(app)
            assert app.zoom_percent_var.get() == '125%'
            app.search_window.close()
            app.auto_font_size_var.set(True); app.set_auto_font_size(); pump(app)
            expected = app.font_size_var.get()
            app.adjust_zoom(3); pump(app)
            assert not app.auto_font_size_var.get()
            app.zoom_menu.invoke(0); pump(app)
            assert app.font_size_var.get() == expected, 'Auto must recalculate at unchanged window size'
            app.zoom_menu.invoke(5); pump(app)
            assert app.config_data.get('view', 'font_size') == '175'
            assert not app.config_data.getboolean('view', 'auto_font_size')
            app.zoom_menu.invoke(2); pump(app)
            if '--screenshot' in sys.argv:
                from PIL import ImageGrab
                ImageGrab.grab().save('/tmp/pfc-zoom-layout.png')
            app.zoom_menu.invoke(5); pump(app)
            assert not errors, errors
        finally:
            app.close_app()
        subprocess.run([sys.executable, __file__, pfc.__name__, '--restore', str(root)], check=True)
        print('PASS: 25% zoom, wheel capture, new dialogs, compact controls, Auto reset, persistence')

if __name__ == '__main__': main()
