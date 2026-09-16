"""GUI regression for common-prefix icons, editor, custom slots and archives."""
import configparser
import importlib
from pathlib import Path
import sys
import tempfile
import time
import zipfile
import os
import threading
import ctypes

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
module = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'pycommander.app')


def settle(app):
    end = time.monotonic() + .15
    while time.monotonic() < end:
        app.update(); time.sleep(.01)


def main():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw).resolve()
        home = root / 'User'; cloud = home / 'OneDrive - Work'; downloads = home / 'Downloads'
        code = cloud / 'Code 100%'; target = code / 'Project' / 'Source'
        target.mkdir(parents=True); downloads.mkdir()
        unrelated = root / 'User-other'; unrelated.mkdir()
        file = target / 'test.txt'; file.write_text('test')
        module.Commander._find_ini_path = staticmethod(lambda: root / 'pfc.ini')
        module.Commander._sync_auto_start = lambda self, **kw: True
        app = module.Commander(); errors = []
        app.report_callback_exception = lambda *exc: errors.append(str(exc))
        try:
            app.geometry('1100x700'); settle(app)
            pane = app.left_tabs.current(); app.set_active(pane)
            pane._automatic_home_prefixes = [(home, 'home'), (cloud, 'cloud'), (downloads, 'download')]
            pane.navigate(target); settle(app)
            assert pane._home_match == (cloud, 'cloud')
            assert [text for text, _ in pane.path_bar._parts] == ['Code 100%', 'Project', 'Source']
            pane.tree.focus_force(); pane.tree.event_generate('<F12>'); settle(app)
            assert pane.path_entry.get() == str(target) and pane.path_entry.selection_present()
            pane.path_var.set(str(file)); pane.path_entry.event_generate('<Return>'); settle(app)
            assert pane.selected_paths() == [file]
            if os.name == 'nt':
                def escape_menu():
                    time.sleep(.4)
                    ctypes.windll.user32.keybd_event(0x1B, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(0x1B, 0, 2, 0)
                threading.Thread(target=escape_menu, daemon=True).start()
            else:
                app.after(100, lambda: pane._home_menu.unpost())
            pane.home_button.event_generate('<Button-3>'); settle(app)
            assert pane._home_menu.index('end') == 8
            assert pane._home_menu.entrycget(4, 'image')
            assert 'Code' in pane._home_menu.entrycget(4, 'label')
            pane._home_menu.invoke(8); settle(app)
            dialog = app._prefix_preferences
            dialog.rows[0][1].set(str(code)); dialog.save_button.invoke(); settle(app)
            assert pane._home_match == (code, 'code')
            assert [text for text, _ in pane.path_bar._parts] == ['Project', 'Source']
            saved = configparser.ConfigParser(); saved.read(root / 'pfc.ini', encoding='utf-8')
            assert module.load_custom_prefixes(saved) == app.custom_home_prefixes
            pane.home_button.invoke(); settle(app)
            assert pane.path == code and pane.path_bar._parts == [('Code', code)]
            pane.up(); settle(app)
            assert pane._home_match == (cloud, 'cloud')
            pane.navigate(downloads); settle(app)
            assert pane._home_match == (downloads, 'download')
            pane.navigate(root); settle(app)
            assert pane._home_match is None
            def assert_prefix(location, expected):
                pane.navigate_external(location)
                # The icon and crumbs must update together during navigation,
                # without waiting for a resize or the next redraw event.
                assert pane._home_match == expected, (location, pane._home_match)
                icon = expected[1] if expected else 'root'
                image = pane._home_images[(icon, module.prefix_icon_size(pane))]
                assert str(pane.home_button.cget('image')[0]) == str(image)
                assert pane.path_bar.committed == str(location)
                if expected is None:
                    assert pane.path_bar._parts == module.path_ancestors(location)
                    assert str(pane._home_root()) in pane._home_tooltip()
                else:
                    assert expected[0] not in [p for _, p in pane.path_bar._parts] or location == expected[0]
                pane.path_bar.begin_edit()
                assert pane.path_entry.get() == str(location)
                pane.path_bar.cancel()
                settle(app)
            for location, expected in ((unrelated,None), (target,(code,'code')),
                                       (cloud,(cloud,'cloud')), (home,(home,'home')),
                                       (root,None), (downloads,(downloads,'download')),
                                       (unrelated,None), (code,(code,'code')), (root,None)):
                assert_prefix(location, expected)
            pane.home_button.invoke(); settle(app)
            assert pane.path == Path(root.anchor) and pane._home_match is None
            assert pane.path_bar._parts == module.path_ancestors(pane.path)
            # An archive outside configured prefixes must also show ROOT and its
            # original full path, not inherit a previous prefix or the temp path.
            plain_zip = unrelated / 'outside.zip'
            with zipfile.ZipFile(plain_zip, 'w') as z: z.writestr('inside/file.txt', 'test')
            app._open_special_file(pane, plain_zip)
            deadline = time.monotonic()+15
            while pane in app._archive_open_jobs and time.monotonic() < deadline: settle(app)
            assert pane.archive_session is not None and pane._home_match is None
            assert pane.path_bar._parts[:-1] == module.path_ancestors(unrelated)
            assert pane._home_root() == Path(plain_zip.anchor)
            pane.home_button.invoke(); settle(app)
            assert pane.path == Path(plain_zip.anchor) and pane.archive_session is None
            archive = code / 'sample.zip'
            with zipfile.ZipFile(archive, 'w') as z: z.writestr('inside/file.txt', 'test')
            app._open_special_file(pane, archive)
            deadline = time.monotonic()+15
            while pane in app._archive_open_jobs and time.monotonic() < deadline: settle(app)
            assert pane.archive_session is not None
            pane.navigate(pane.archive_session.root / 'inside'); settle(app)
            assert [s for s, _ in pane.path_bar._parts] == ['sample.zip', 'inside']
            assert pane.path_bar.committed == str(archive / 'inside')
            pane.home_button.invoke(); settle(app)
            assert pane.path == code and pane.archive_session is None
            pane.navigate(target); pane.lock_mode = 'locked'
            pane.home_button.invoke(); settle(app)
            assert pane.path == target and app.active.path == code
            pane.lock_mode = 'unlocked'; app.left_tabs.select(pane); app.set_active(pane)
            app.edit_home_prefixes(); settle(app)
            before = [dict(item) for item in app.custom_home_prefixes]
            app._prefix_preferences.rows[0][1].set('cancelled')
            app._prefix_preferences.destroy(); assert app.custom_home_prefixes == before
            app.auto_font_size_var.set(False)
            for scale in ('small', '175', '300'):
                app.font_size_var.set(scale); app.apply_font_size(save=False); settle(app)
                assert pane.home_button.winfo_ismapped()
                assert pane.path_bar.canvas.winfo_width() > 30
            app.font_size_var.set('small'); app.apply_font_size(save=False); settle(app)
            if '--screenshot' in sys.argv:
                from PIL import ImageGrab
                ImageGrab.grab().save('/tmp/pfc-homeprefix.png')
            assert not errors, errors
            print('PASS: prefix/ROOT transitions, matching icons and full paths, root navigation, F12, INI, Home, ZIP, locked tab, zoom')
        finally:
            app.close_app()


if __name__ == '__main__': main()
