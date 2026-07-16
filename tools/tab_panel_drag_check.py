"""Focused GUI check for dragging a tab between visible panels."""

import tempfile
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pfc


def main() -> None:
    original = pfc.Commander._find_ini_path
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        first = root / "first"; first.mkdir()
        moved = root / "moved"; moved.mkdir()
        (moved / "selected.txt").write_text("selected", encoding="utf-8")
        target = root / "target"; target.mkdir()
        ini_path = root / "pfc.ini"
        pfc.Commander._find_ini_path = staticmethod(lambda: ini_path)
        app = pfc.Commander()
        try:
            app.geometry("1000x600+40+40")
            app.update()
            source_tabs, target_tabs = app.left_tabs, app.right_tabs
            source_tabs.current().navigate(first)
            pane = source_tabs.add_tab(moved)
            pane.sort_column = "modified"; pane.reverse = True
            pane.show_hidden = True; pane.show_extensions = False
            pane.set_quick_filter("selected")
            pane.select_path(moved / "selected.txt")
            source_tabs.set_color(pane, "amber", notify=False)
            pane.lock_mode = "reset"; pane.locked_path = moved
            source_tabs.set_lock(pane, "reset", notify=False)
            app.update()

            source_left, source_right, _ = next(box for box in source_tabs._hitboxes if box[2] is pane)
            target_left, target_right, _ = target_tabs._hitboxes[0]
            press_x = (source_left + source_right) // 2
            drop_x_root = target_tabs.bar.winfo_rootx() + target_right + 4
            drop_y_root = target_tabs.bar.winfo_rooty() + target_tabs.bar.winfo_height() // 2
            source_tabs._tab_press(SimpleNamespace(x=press_x))
            source_tabs._tab_motion(SimpleNamespace(
                x=drop_x_root - source_tabs.bar.winfo_rootx(),
                y=drop_y_root - source_tabs.bar.winfo_rooty(),
                x_root=drop_x_root, y_root=drop_y_root))
            assert target_tabs._drop_position == 1
            source_tabs._tab_release(SimpleNamespace(
                x=drop_x_root - source_tabs.bar.winfo_rootx(),
                y=drop_y_root - source_tabs.bar.winfo_rooty(),
                x_root=drop_x_root, y_root=drop_y_root))
            app.update()

            assert len(source_tabs.tabs()) >= 1
            moved_pane = target_tabs.current()
            assert moved_pane.path == moved
            assert target_tabs.index(moved_pane) == 1
            assert target_tabs._colors[moved_pane] == "amber"
            assert moved_pane.lock_mode == "reset" and moved_pane.locked_path == moved
            assert moved_pane.sort_column == "modified" and moved_pane.reverse
            assert moved_pane.show_hidden and not moved_pane.show_extensions
            assert moved_pane.quick_filter_var.get() == "selected"
            assert moved_pane.selected_paths() == [moved / "selected.txt"]
            assert target_tabs._drop_position is None
            print("Cross-panel tab drag check passed", flush=True)
        finally:
            app.destroy()
            pfc.Commander._find_ini_path = original


if __name__ == "__main__":
    main()
