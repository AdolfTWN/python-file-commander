"""Folder identity, cache eviction, overlays, navigation and zoom regressions.

Uses deterministic colored Shell responses on every OS, then compares Windows
Known Folder rows with uncached native Shell images. No network or startup writes.
"""
import gc
import hashlib
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pfc = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'pycommander.app')
icons = pfc if pfc.__name__ == 'pfc' else importlib.import_module('pycommander.icons')
native_get = icons.ShellIconProvider.get


def settle(app):
    end = time.monotonic() + .12
    while time.monotonic() < end:
        app.update()
        time.sleep(.01)


def pixels(image):
    return image.tk.call(str(image), 'data', '-format', 'png')


def fixture_load(self, path, is_dir):
    rgb = hashlib.sha256(str(path).encode()).hexdigest()[:6]
    image = icons.PhotoImage(width=self.size, height=self.size)
    image.put('#' + rgb, to=(0, 0, self.size, self.size))
    return image


def fixture_get(self, *args, **kwargs):
    # Only the synchronous get call sees a Windows platform; never the app or
    # pathlib globally. Exercise real cache/compositing on Linux as well.
    with patch.dict(native_get.__globals__, os=SimpleNamespace(name='nt', path=os.path)):
        return native_get(self, *args, **kwargs)


def verify_rows(pane, expected_paths):
    def walk(parent=''):
        for iid in pane.tree.get_children(parent):
            if pane.tree.item(iid, 'tags'):
                yield iid
            yield from walk(iid)
    rows = list(walk())
    assert {pane.tree.item(iid, 'tags')[0] for iid in rows} == {str(p) for p in expected_paths}
    gc.collect()
    live = set(pane.tk.call('image', 'names'))
    for iid in rows:
        path = Path(pane.tree.item(iid, 'tags')[0])
        name, = pane.tree.item(iid, 'image')
        assert name in live, ('Eviction removed a displayed image', path)
        reference = icons.ShellIconProvider(pane.icons.size)
        expected = reference.get(path, path.is_dir())
        actual = pane._row_icons[str(path)]
        assert str(actual) == name
        assert pixels(actual) == pixels(expected), ('Wrong folder or scale', path, pane.icons.size)
    assert len(pane._row_icons) == len(rows), 'Old navigation images must be released'


with tempfile.TemporaryDirectory(prefix='pfc-icon-check-') as raw:
    root = Path(raw)
    left, right = root / 'first', root / 'second'
    left.mkdir(); right.mkdir()
    names = ['Downloads', 'OneDrive', 'Documents', 'Desktop', 'Projects', 'Pictures']
    first = [left / name for name in names]
    second = [right / name for name in reversed(names)]
    for path in first + second:
        path.mkdir()
    pfc.Commander._find_ini_path = staticmethod(lambda: root / 'pfc.ini')
    pfc.Commander._sync_auto_start = lambda *a, **kw: True
    pfc.Commander._start_windows_tray = lambda *a: None
    app = pfc.Commander()
    errors = []
    app.report_callback_exception = lambda *exc: errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False)
        app.vcs_overlay_var.set(False); app.onedrive_overlay_var.set(False)
        app.geometry('1200x780+0+0')
        pane = app.left_tabs.current()
        with patch.object(icons.ShellIconProvider, '_load', fixture_load), \
                patch.object(icons.ShellIconProvider, 'get', fixture_get):
            for scale in ('small', '175', '125', '200', 'small'):
                app.font_size_var.set(scale); app.apply_font_size(save=False)
                pane.icons.cache_limit = 2  # Deliberately smaller than displayed rows.
                for directory, paths in ((left, first), (right, second), (left, first)):
                    pane.navigate(directory); settle(app)
                    verify_rows(pane, paths)
                    assert len(pane.icons.cache) <= 2
                print('PASS: navigation, zoom, live image eviction at ' + scale, flush=True)
            # Native compositing must keep the right base under both badges.
            provider = icons.ShellIconProvider(40, cache_limit=2)
            for overlay in (None, 'clean', 'modified', 'untracked'):
                for cloud in (None, 'online', 'available', 'pinned', 'syncing'):
                    actual = [provider.get(path, True, overlay, cloud) for path in first]
                    assert len({pixels(image) for image in actual}) == len(first)
                    for path, image in zip(first, actual):
                        reference = icons.ShellIconProvider(40).get(path, True, overlay, cloud)
                        assert pixels(reference) == pixels(image)
            print('PASS: independent folder identity with VCS/cloud badge combinations', flush=True)
            pane.show_file_listing(first, 'Icon test'); verify_rows(pane, first)
            pane.show_preview(first[0]); assert not pane._row_icons
            pane.navigate(left); pane.search(''); verify_rows(pane, first)
            pane.navigate(right); verify_rows(pane, second)
            print('PASS: result/preview/search image ownership cleanup', flush=True)
            for mode in ('folder', 'file'):
                pane.view_mode = mode; pane.refresh(); settle(app)
                verify_rows(pane, [right] + second)
            pane.view_mode = 'list'; pane.refresh()
            # A zoom during a pressed drag defers refresh; old row images must
            # survive provider replacement until the drag releases its rows.
            pane._drag_press_item = pane.tree.get_children()[0]
            old_images = tuple(pane.tree.item(iid, 'image')[0] for iid in pane.tree.get_children())
            app.font_size_var.set('175'); app.apply_font_size(save=False)
            gc.collect()
            assert set(old_images) <= set(app.tk.call('image', 'names'))
            pane._drag_press_item = None; pane.refresh(); verify_rows(pane, second)
            # Clipboard owns its displayed image outside the provider too.
            app.clipboard_icons.cache_limit = 1
            app._set_clipboard_visual('Clipboard: folder', [first[0]], kind='folder')
            clipboard_name = str(app._clipboard_icon_images[0])
            for path in first[1:]:
                app.clipboard_icons.get(path, True)
            gc.collect()
            assert clipboard_name in app.tk.call('image', 'names')
            print('PASS: nested tree, deferred drag zoom and clipboard image lifetime', flush=True)
        if os.name == 'nt':
            # Read only existing Known Folder icon metadata, plus ordinary test
            # folders. No OneDrive sign-in, hydration or folder-content search.
            native_paths = [Path.home() / name for name in names if (Path.home() / name).is_dir()]
            native_paths += first[:2]
            assert len(native_paths) >= 4
            for scale in ('small', '175', '125', '200', 'small'):
                app.font_size_var.set(scale); app.apply_font_size(save=False)
                pane.icons = icons.ShellIconProvider(pane.icons.size, cache_limit=2)
                for paths in (native_paths, list(reversed(native_paths))):
                    pane.show_file_listing(paths, 'Native Windows folder icons'); settle(app)
                    verify_rows(pane, paths)
                    # Compare against uncached Shell results, not another cache.
                    for path in paths:
                        native = pane.icons._load(path, True)
                        assert native is not None
                        assert pixels(pane._row_icons[str(path)]) == pixels(pane.icons._with_text_gap(native))
                    assert len({pixels(img) for img in pane._row_icons.values()}) >= 2
                print('PASS: Windows Shell pixel equality in both orders at ' + scale, flush=True)
        assert not errors, errors
    finally:
        app.close_app()
print('PASS: folder icon regressions complete', flush=True)
