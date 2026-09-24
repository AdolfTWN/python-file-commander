"""Real Tk hover/focus lifecycle checks; package and portable, Linux/Windows."""
import importlib
import os
from pathlib import Path
import subprocess
import sys
import time
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
module = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'pycommander.tooltip')
tabs = module if sys.argv[1:] else importlib.import_module('pycommander.tabs')


def settle(root, seconds=.12):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(.005)


def point(root, widget, x=10, y=10):
    widget.event_generate('<Motion>', warp=True, x=x, y=y, when='tail')
    settle(root, .03)


def main():
    root = tk.Tk()
    root.tk.call('tk', 'scaling', float(os.environ.get('PFC_TOOLTIP_TEST_SCALE', '1.333')))
    root.geometry('520x420+80+80')
    errors = []
    root.report_callback_exception = lambda *exc: errors.append(str(exc))
    button = ttk.Button(root, text='Hover target')
    button.pack(fill='x')
    tree = ttk.Treeview(root, height=8)
    tree.pack(fill='both', expand=True)
    for i in range(24):
        tree.insert('', 'end', iid=str(i), text=f'Folder {i}')
    other = tk.Toplevel(root)
    other.geometry('200x160+700+80')
    other.title('Another dialog')
    try:
        tip = module.ToolTip(button, 'PFC help', delay=100)
        root.focus_force(); settle(root)
        point(root, button)
        tip._enter(); settle(root, .17)
        assert tip.popup is not None, 'valid hover must show help'
        assert not tip.popup.attributes('-topmost'), 'help must not be globally topmost'
        assert root.focus_get() is not tip.popup, 'help must not steal focus'
        other.focus_force(); settle(root)
        assert tip.popup is None and tip.job is None, 'visible help survived focus loss'
        root.focus_force(); settle(root)
        tip._enter()
        other.focus_force(); settle(root, .2)
        assert tip.popup is None and tip.job is None, 'delayed help appeared after focus loss'
        root.focus_force(); settle(root)
        tip._enter(); settle(root, .17)
        root.event_generate('<Escape>'); settle(root)
        assert tip.popup is None, 'Escape must dismiss help'
        tip._enter(); settle(root, .17)
        point(root, tip.popup, 5, 5)
        assert tip.popup is None, 'help must yield when pointer approaches it'
        point(root, button)
        tip.lifetime_ms = 150
        tip._enter(); settle(root, .4)
        assert tip.popup is None and tip.watch_job is None, 'bounded expiry'
        assert not tip.owner_bindings, 'temporary owner bindings leaked'
        tip.lifetime_ms = 8000
        tip._enter(); settle(root, .17)
        root.withdraw(); settle(root)
        assert tip.popup is None and tip.job is None, 'hidden owner retained help'
        root.deiconify(); root.focus_force(); settle(root)
        point(root, button)
        tip._enter(); settle(root, .17)
        # Independent Tk process: actual OS focus change, not a simulated event.
        child = subprocess.Popen([sys.executable, '-c',
            "import tkinter as t; r=t.Tk(); r.geometry('180x100+700+300'); "
            "r.after(100,r.focus_force); r.after(850,r.destroy); r.mainloop()"])
        try:
            settle(root, .6)
            assert tip.popup is None and tip.job is None, 'help survived another process gaining focus'
            child.wait(timeout=5)
        finally:
            if child.poll() is None:
                child.terminate(); child.wait(timeout=5)
        root.focus_force(); settle(root)
        rowtip = module.TreeItemToolTip(tree, lambda item: 'Path ' + item, delay=90)
        box = tree.bbox('0')
        point(root, tree, 40, box[1]+box[3]//2)
        settle(root, .15)
        assert rowtip.popup is not None, ('row hover help missing', rowtip.item,
            rowtip._eligible(), tree.winfo_pointerxy(), box, root.focus_get(), errors)
        tree.yview_scroll(4, 'units'); settle(root, .15)
        assert rowtip.popup is None, 'stale row help survived scroll without Motion'
        rowtip.hide()
        menu = tk.Menu(root, tearoff=False)
        menu.add_command(label='Example')
        native = module.MenuToolTip(menu, {}, delay=90)
        menu.post(200, 200); menu.activate(0)
        point(root, menu, 12, 10)
        native._selected(); settle(root, .15)
        assert native.popup is not None, 'posted menu help missing'
        menu.unpost(); settle(root)
        assert native.popup is None and native.last_index is None
        # Reopening the same menu entry must not retain a stale active index.
        menu.post(200, 200); menu.activate(0)
        point(root, menu, 12, 10)
        native._selected(); settle(root, .15)
        assert native.popup is not None
        menu.unpost(); settle(root)
        root.focus_force(); settle(root)
        controller = tabs.HeaderPopupController(root)
        controller.show_at(200, 200, menu); settle(root)
        popup = controller.popups[0]
        popup.help_tip.delay = 90
        top, bottom = popup.row_bounds[0]
        point(root, popup.canvas, 15, (top+bottom)//2)
        controller.schedule_tooltip(popup, 0); settle(root, .15)
        assert popup.help_tip.popup is not None, 'custom header help missing'
        controller.close_all(); settle(root)
        assert popup.help_tip.popup is None and not popup.help_tip.owner_bindings
        root.focus_force(); point(root, button)
        tip._enter(); settle(root, .17)
        button.destroy(); settle(root)
        assert tip.popup is None and tip.job is None and not tip.owner_bindings
        assert not errors, errors
        print('PASS: hover, pending/visible focus loss, external process, Escape, pointer approach, expiry, scroll, menus, destruction', flush=True)
    finally:
        root.destroy()


if __name__ == '__main__':
    main()
