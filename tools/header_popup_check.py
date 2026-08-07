"""Focused, non-interactive GUI check for PFC header popup menus."""

import tempfile
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pfc


def main() -> None:
    original = pfc.Commander._find_ini_path
    with tempfile.TemporaryDirectory() as raw:
        pfc.Commander._find_ini_path = staticmethod(lambda: Path(raw) / "pfc.ini")
        app = pfc.Commander()
        try:
            app.geometry("900x600+300+180")
            app.update_idletasks(); app.update()
            app.left_tabs.redraw()
            app.header_popup.show(app.view_menu_button, app.view_menu)
            app.update_idletasks(); app.update()
            root = app.header_popup.popups[0]
            font_index = next(index for index, kind, label, _accelerator, _state in root.items
                              if kind == "cascade" and label == "Font Size")
            font_y = sum(root.row_bounds[font_index]) // 2
            root._motion(SimpleNamespace(y=font_y))
            app.update_idletasks(); app.update()
            assert len(app.header_popup.popups) == 2
            child = app.header_popup.popups[1]
            assert root.top.winfo_ismapped() and child.top.winfo_ismapped()
            root_arrows = [item for item in root.canvas.find_all()
                           if root.canvas.type(item) == "text" and
                           root.canvas.itemcget(item, "text") == "▶"]
            assert len(root_arrows) == 6
            child_ticks = [item for item in child.canvas.find_all()
                           if child.canvas.type(item) == "text" and
                           child.canvas.itemcget(item, "text") == "✓"]
            assert len(child_ticks) == 2  # Selected size plus enabled Auto Font Size.
            assert root.font.actual("size") == pfc.tkfont.nametofont("TkMenuFont").actual("size")
            child._left()
            app.update_idletasks(); app.update()
            assert len(app.header_popup.popups) == 1 and root.top.winfo_ismapped()
            root._escape()
            assert not app.header_popup.popups
            app.header_popup.show(app.view_menu_button, app.view_menu)
            app.update_idletasks(); app.update()
            root = app.header_popup.popups[0]
            font_index = next(index for index, kind, label, _accelerator, _state in root.items
                              if kind == "cascade" and label == "Font Size")
            root._motion(SimpleNamespace(y=sum(root.row_bounds[font_index]) // 2))
            app.update_idletasks(); app.update()
            child = app.header_popup.popups[1]
            medium_index = next(index for index, _kind, label, _accelerator, _state in child.items
                                if label == "125% Medium")
            child._click(SimpleNamespace(y=sum(child.row_bounds[medium_index]) // 2))
            app.update_idletasks(); app.update()
            assert app.font_size_var.get() == "medium"
            assert not app.header_popup.popups
            app.header_popup.show(app.view_menu_button, app.view_menu)
            medium_row_height = app.header_popup.popups[0].row_height
            app.header_popup.close_all()
            app.font_size_var.set("xxl"); app.apply_font_size()
            app.update_idletasks(); app.update()
            app.header_popup.show(app.view_menu_button, app.view_menu)
            huge_root = app.header_popup.popups[0]
            assert huge_root.row_height > medium_row_height
            huge_arrows = [item for item in huge_root.canvas.find_all()
                           if huge_root.canvas.type(item) == "text" and
                           huge_root.canvas.itemcget(item, "text") == "▶"]
            assert len(huge_arrows) == 6
            app.header_popup.close_all()
            app.header_popup.show(app.view_menu_button, app.view_menu)
            root = app.header_popup.popups[0]
            root._outside_click(SimpleNamespace(x_root=0, y_root=0))
            assert not app.header_popup.popups
        finally:
            app.destroy()
            pfc.Commander._find_ini_path = original


if __name__ == "__main__":
    main()
