"""Exercise a real Git working-tree change between mouse press and drag motion."""
import importlib
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
app_module = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else "pycommander.app")

def main():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        source = root / "repo"
        source.mkdir()
        fixture = "--overlay-fixture" in sys.argv
        if not fixture:
            subprocess.run(["git", "init", "-q", str(source)], check=True)
        item = source / "probe.txt"
        item.write_text("drag me")
        if fixture:
            # Offline Windows images may lack Git. Exercise native icon
            # rendering using the same status map the real Git scan returns.
            app_module.folder_statuses = lambda folder: {
                os.path.normcase(str(item.resolve())): "untracked"
            } if folder == source else {}
        target = root / "target"
        target.mkdir()
        app_module.Commander._find_ini_path = staticmethod(lambda: root / "pfc.ini")
        # A GUI regression must not change the operator's Windows startup entry.
        app_module.Commander._sync_auto_start = lambda self, **kwargs: True
        app = app_module.Commander()
        try:
            pane = app.left_tabs.current()
            destination = app.right_tabs.current()
            pane.navigate(source)
            destination.navigate(target)
            app.update()
            deadline = time.monotonic() + 10
            while pane._vcs_loading and time.monotonic() < deadline:
                app.update()
                time.sleep(.02)
            assert pane._vcs_statuses, "Git overlays did not load"
            pane.select_path(item)
            iid = pane.tree.selection()[0]
            box = pane.tree.bbox(iid)
            press = SimpleNamespace(x=box[0]+25, y=box[1]+5,
                                    x_root=pane.tree.winfo_rootx()+box[0]+25,
                                    y_root=pane.tree.winfo_rooty()+box[1]+5, state=256)
            pane._drag_press(press)
            (source / "new-untracked.txt").write_text("Git working-tree update")
            pane.refresh_if_changed()
            move = SimpleNamespace(x=press.x+20, y=press.y,
                                   x_root=destination.tree.winfo_rootx()+100,
                                   y_root=destination.tree.winfo_rooty()+150, state=256)
            pane._drag_motion(move)
            pane._drag_release(move)
            app.update()
            assert (target / item.name).read_text() == "drag me"
            assert item.exists(), "Default drag must copy, not move"
            assert any(Path(pane.tree.item(row, "tags")[0]).name == "new-untracked.txt"
                       for row in pane.tree.get_children()), "Deferred refresh was lost"
            # A second gesture with Shift must move, even if refresh arrives
            # after the drag has already started.
            move_item = source / "move-probe.txt"
            move_item.write_text("move me")
            pane.refresh()
            pane.select_path(move_item)
            box = pane.tree.bbox(pane.tree.selection()[0])
            press.y = box[1]+5
            press.y_root = pane.tree.winfo_rooty()+press.y
            pane._drag_press(press)
            move.state = 257
            pane._drag_motion(move)
            pane.refresh()
            pane._drag_release(move)
            app.update()
            assert not move_item.exists()
            assert (target / move_item.name).read_text() == "move me"
            # Cancel also releases deferred refresh, without transferring files.
            pane.select_path(item)
            box = pane.tree.bbox(pane.tree.selection()[0])
            press.y = box[1]+5
            press.y_root = pane.tree.winfo_rooty()+press.y
            pane._drag_press(press)
            pane._drag_motion(move)
            pane.refresh()
            app._handle_internal_drag("cancel", pane, None)
            app.update()
            assert pane._drag_press_item is None and not pane._refresh_after_drag
            assert item.exists()
            print("Overlay refresh during drag: PASS (" +
                  ("status fixture" if fixture else "real Git") + ")")
        finally:
            app.destroy()

if __name__ == "__main__":
    main()
