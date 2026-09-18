"""Regression: named-font changes must not invalidate breadcrumb geometry."""
import importlib
from pathlib import Path
import sys
import tempfile
import time
import tkinter.font as tkfont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
module = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'pycommander.app')


def settle(app, seconds=.15):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update(); time.sleep(.01)


with tempfile.TemporaryDirectory() as raw:
    root = Path(raw)/'dsp-ai-kit'/'solutions'/'DSPsolutions'/'erd-generation'
    root.mkdir(parents=True)
    module.Commander._find_ini_path = staticmethod(lambda: Path(raw)/'pfc.ini')
    module.Commander._sync_auto_start = lambda self, **kwargs: True
    app = module.Commander(); errors = []
    app.report_callback_exception = lambda *exc: errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False); app.font_size_var.set('large')
        app.geometry('1800x760'); app.apply_font_size(save=False)
        pane = app.left_tabs.current(); pane.navigate(root); app.set_active(pane)
        bar = pane.path_bar; settle(app)
        def assert_layout():
            for item in bar.canvas.find_all():
                if bar.canvas.type(item) != 'text':
                    continue
                x = bar.canvas.coords(item)[0]
                region = next((r for r in bar._regions if r[0] <= x < r[1]), None)
                bbox = bar.canvas.bbox(item)
                assert region and bbox[2] <= region[1]+1, (bar.canvas.itemcget(item,'text'), bbox, region)
            assert bar._regions[-1][2] == len(bar._parts)-1
        assert_layout()
        font = tkfont.nametofont('TkDefaultFont')
        original = font.actual()
        def measured_widths():
            return [tkfont.Font(root=app, font=bar.canvas.itemcget(item, 'font')).measure(
                bar.canvas.itemcget(item, 'text')) for item in bar.canvas.find_all()]
        old_widths = measured_widths()
        # Simulate the OS changing a shared named font without resizing Canvas.
        font.configure(size=original['size']*2)
        assert old_widths == measured_widths(), 'Shared font invalidates existing breadcrumb coordinates'
        for event in ('<Expose>', '<Visibility>', '<Map>'):
            bar.canvas.event_generate(event); settle(app); assert_layout()
        font.configure(**original)
        app.event_generate('<FocusIn>'); settle(app); assert_layout()
        for scale in module.FONT_SCALES:
            app.font_size_var.set(scale); app.apply_font_size(save=False); settle(app)
            assert_layout()
            for item in bar.canvas.find_withtag('folder'):
                rendered = tkfont.nametofont(bar.canvas.itemcget(item, 'font'))
                assert rendered.actual('underline') == 1
            assert bar.canvas.find_withtag('folder')
            assert bar.link.metrics('linespace') == bar.bold.metrics('linespace')
        app.font_size_var.set('large'); app.apply_font_size(save=False); settle(app)
        expected = bar.link.cget('size')
        original_scaling = float(app.tk.call('tk', 'scaling'))
        app.tk.call('tk', 'scaling', original_scaling*.6)
        bar.canvas.event_generate('<Expose>'); settle(app)
        assert bar.link.cget('size') == expected, 'OS scaling changed selected zoom pixels'
        assert_layout()
        app.tk.call('tk', 'scaling', original_scaling)
        before = bar.committed
        bar.begin_edit(); pane.path_var.set('draft path')
        bar.canvas.event_generate('<Expose>'); settle(app)
        assert bar.editing and pane.path_var.get() == 'draft path'
        bar.cancel(); settle(app); assert bar.committed == before
        for _ in range(3):
            app.withdraw(); settle(app); app.deiconify(); settle(app); assert_layout()
        if '--lock-test' in sys.argv:
            import ctypes
            marker = Path(__file__).with_name('pathbar-resume-continue.txt')
            marker.unlink(missing_ok=True)
            print('READY: locking Windows at 150%; unlock PFC-Test to continue', flush=True)
            assert ctypes.windll.user32.LockWorkStation()
            # Host operator unlocks; continue on a task-owned marker, not a password.
            locked_at = time.monotonic()
            expected_pixels = bar.link.cget('size')
            deadline = locked_at+1200
            while not marker.exists() and time.monotonic() < deadline:
                settle(app)
            assert marker.exists(), 'Timed out waiting for operator unlock validation'
            # QGA may still hold the marker open; the host cleans it up later.
            settle(app); assert_layout()
            assert app.font_size_var.get() == 'large'
            assert bar.link.cget('size') == expected_pixels
            elapsed = time.monotonic()-locked_at
            if '--long-lock' in sys.argv:
                assert elapsed >= 600, elapsed
            print(f'PASS: real Windows lock/unlock at 150%, {elapsed:.1f}s, pixels={expected_pixels}', flush=True)
        assert not errors, errors
        print('PASS: font-change isolation, resume repaint, underlined folders, all zoom steps, editing and restore', flush=True)
    finally:
        app.destroy()
    assert bar._redraw_job is None and bar._closed
