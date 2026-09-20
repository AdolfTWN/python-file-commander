"""Exercise actual tab badges, bounded image lifetime and unchanged lock behavior."""
import importlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pycommander.app')
tab_module = pfc if pfc.__name__ == 'pfc' else importlib.import_module('pycommander.tabs')


with tempfile.TemporaryDirectory() as raw:
    root = Path(raw)
    for name in ('Downloads', 'Projects', 'Documents', 'child'):
        (root/name).mkdir()
    pfc.Commander._find_ini_path = staticmethod(lambda: root/'pfc.ini')
    pfc.Commander._sync_auto_start = lambda self, **kwargs: True
    app = pfc.Commander()
    errors = []
    app.report_callback_exception = lambda *exc: errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False)
        app.geometry('1600x800+0+0')
        tabs = app.left_tabs
        free = tabs.current(); free.navigate(root/'Downloads')
        locked = tabs.add_tab(root/'Projects'); tabs.set_lock(locked, 'locked')
        reset = tabs.add_tab(root/'Documents'); tabs.set_lock(reset, 'reset')
        for zoom in ('small', 'large', '300'):
            app.font_size_var.set(zoom); app.apply_font_size(save=False)
            for scheme in pfc.COLOR_SCHEMES:
                app.color_scheme_var.set(scheme); app.apply_color_scheme(save=False)
                for style in pfc.TAB_STYLES:
                    tabs.set_style(style)
                    for active in (free, locked, reset):
                        tabs.select(active); app.update()
                        assert len(tabs.bar.find_withtag('tab-lock-icon')) == 2
                        assert not tabs.bar.find_withtag('lock:'+str(id(free)))
                        assert set(tabs._lock_images) == {'locked', 'reset'}
                        size = tabs._lock_image_spec[0]
                        assert all(i.width()==i.height()==size for i in tabs._lock_images.values())
                        for child in (locked, reset):
                            icon = tabs.bar.bbox('lock:'+str(id(child)))
                            title = tabs.bar.bbox('title:'+str(id(child)))
                            left, right, _ = next(b for b in tabs._hitboxes if b[2] is child)
                            assert 3 <= icon[0]-left <= 6, (style, icon, left)
                            assert icon[2] <= title[0], (icon, title)
                            assert title[2] <= right, (title, right)
                            assert icon[1] >= 1 and icon[3] <= tabs.bar.winfo_height()-2
                            assert tabs._at(icon[0]+2) is child
                        # A redraw must reuse the same two native Tk images.
                        images = tuple(map(str, tabs._lock_images.values()))
                        for _ in range(8): tabs.redraw()
                        assert tuple(map(str, tabs._lock_images.values())) == images
                    for color in tab_module.TAB_COLORS:
                        before = tabs._lock_image_spec
                        tabs.set_color(locked, color); tabs.set_color(reset, color)
                        assert tabs._lock_image_spec == before
        # Restore readable font and verify actual navigation, not just indicators.
        app.font_size_var.set('small'); app.apply_font_size(save=False)
        tabs.select(locked)
        count = len(tabs.tabs()); locked.navigate(root/'child'); app.update()
        assert len(tabs.tabs()) == count+1
        assert locked.path == root/'Projects' and tabs.current().path == root/'child'
        tabs.select(reset); reset.navigate(root/'child'); app.update()
        assert reset.path == root/'child'
        tabs.select(free); app.update()
        assert reset.path == root/'Documents'
        tabs.select(reset); tabs.set_lock(reset, 'unlocked'); app.update()
        assert not tabs.bar.find_withtag('lock:'+str(id(reset)))
        tabs.set_lock(reset, 'reset'); app.save_config()
        modes = json.loads(app.config_data.get('left', 'tab_locks'))
        assert 'locked' in modes and 'reset' in modes and 'unlocked' in modes
        assert not errors, errors
        print('PASS: neutral lock tiles, distinct modes, all styles/themes at 100/150/300%, '
              'compact layout, image reuse, hit testing, lock navigation and persistence')
    finally:
        app.destroy()
