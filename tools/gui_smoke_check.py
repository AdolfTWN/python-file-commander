"""Non-destructive smoke check for the generated portable GUI."""

import tempfile
from pathlib import Path
import sys
import configparser
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pfc


def main() -> None:
    original = pfc.Commander._find_ini_path
    with tempfile.TemporaryDirectory() as raw:
        ini_path = Path(raw) / "pfc.ini"
        pfc.Commander._find_ini_path = staticmethod(lambda: ini_path)
        app = None
        try:
            app = pfc.Commander(); app.withdraw(); app.update_idletasks(); app.update()
            labels = [app.files_menu.entrycget(index, "label")
                      for index in range(app.files_menu.index("end") + 1)
                      if app.files_menu.type(index) not in {"separator", "tearoff"}]
            required = {"Copy to Clipboard", "Paste", "Delete", "Permanent Delete",
                        "Send Delete to Recycle Bin",
                        "Continue After File Errors", "Favorites", "Recent Folders"}
            assert required.issubset(labels), required.difference(labels)
            accelerators = {app.files_menu.entrycget(index, "label"):
                            app.files_menu.entrycget(index, "accelerator")
                            for index in range(app.files_menu.index("end") + 1)
                            if app.files_menu.type(index) == "command"}
            assert accelerators["Copy to Clipboard"] == "Ctrl+C"
            assert accelerators["Permanent Delete"] == "Shift+Del"
            version_labels = [app.versions_menu.entrycget(index, "label")
                              for index in range(app.versions_menu.index("end") + 1)
                              if app.versions_menu.type(index) == "command"]
            assert "Current version: v0.8.5" in version_labels and "v0.8.5" in version_labels
            version_index = next(index for index in range(app.versions_menu.index("end") + 1)
                                 if app.versions_menu.type(index) == "command" and
                                 app.versions_menu.entrycget(index, "label") == "v0.8.5")
            assert app.versions_menu.entrycget(version_index, "accelerator") == "2026/07/14"
            assert app.recycle_bin_var.get() and app.continue_errors_var.get()
            assert ini_path.exists(), "pfc.ini was not generated on first launch"
            app.toggle_favorite()
            assert app.favorites, "Favorite folder was not stored"
            saved = configparser.ConfigParser(); saved.read(ini_path, encoding="utf-8")
            assert saved.getboolean("operations", "send_delete_to_recycle_bin")
            assert saved.get("hotkeys", "permanent_delete") == "<Shift-Delete>"
            assert saved.get("hotkeys", "versions_menu") == "<Alt-h>"
            assert saved.get("navigation", "favorites") != "[]"
            assert app.tab_style_var.get() == "rounded"
            rounded_height = int(float(app.left_tabs.bar.cget("height")))
            for style in ("slanted", "chamfered", "compact", "rounded"):
                app.tab_style_var.set(style); app.apply_tab_style(); app.update_idletasks()
                assert app.left_tabs._tab_style == style and app.right_tabs._tab_style == style
            compact_height = None
            app.tab_style_var.set("compact"); app.apply_tab_style(); app.update_idletasks()
            compact_height = int(float(app.left_tabs.bar.cget("height")))
            assert compact_height <= rounded_height
            last_tab_right = app.left_tabs._hitboxes[-1][1]
            polygon_right = max(max(app.left_tabs.bar.coords(item)[::2])
                                for item in app.left_tabs.bar.find_all()
                                if app.left_tabs.bar.type(item) == "polygon")
            assert polygon_right > last_tab_right, "Compact tab skirt is missing"
            app.tab_style_var.set("rounded"); app.apply_tab_style()
            app.deiconify(); app.update_idletasks(); app.update()
            source, target = app.left_tabs.current(), app.right_tabs.current()
            event = SimpleNamespace(x_root=target.tree.winfo_rootx() + 12,
                                    y_root=target.tree.winfo_rooty() + target.tree.winfo_height() - 8,
                                    state=0)
            assert source.selected_paths(), "Source pane has no selected item for drag smoke check"
            app._handle_internal_drag("start", source, event)
            assert app._drag_state is not None and app._drag_state["target"] is not None
            event.state = 1; app._handle_internal_drag("motion", source, event)
            assert app._drag_state["mode"] == "move"
            app._handle_internal_drag("cancel", source, event)
            assert app._drag_state is None and app._drag_ghost is None
            app.withdraw()
            print("GUI smoke check passed")
        finally:
            if app is not None:
                app.destroy()
            pfc.Commander._find_ini_path = original


if __name__ == "__main__":
    main()
