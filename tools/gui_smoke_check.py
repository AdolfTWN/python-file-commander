"""Non-destructive smoke check for the generated portable GUI."""

import tempfile
from pathlib import Path
import sys
import configparser
import time
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
                        "Continue After File Errors", "Favorites", "Recent Folders", "Multi-Rename"}
            assert required.issubset(labels), required.difference(labels)
            accelerators = {app.files_menu.entrycget(index, "label"):
                            app.files_menu.entrycget(index, "accelerator")
                            for index in range(app.files_menu.index("end") + 1)
                            if app.files_menu.type(index) == "command"}
            assert accelerators["Copy to Clipboard"] == "Ctrl+C"
            assert accelerators["Permanent Delete"] == "Shift+Del"
            version_labels = [app.versions_menu.entrycget(index, "label")
                              for index in range(app.versions_menu.index("end") + 1)
                              if app.versions_menu.type(index) in {"command", "cascade"}]
            assert version_labels == ["Current version: v0.9.0", "v0.9.x Changes",
                                      "v0.8.x Changes", "Yoda — Portable App Advocate"]
            assert app.version_series == ("v0.9.x", "v0.8.x")
            v09_title, v09_body = app.version_series_notes("v0.9.x")
            assert v09_title == "Python File Commander — v0.9.x Changes"
            assert "v0.9.0 — Build 2026/07/14" in v09_body
            assert "• Added: Folder Compare" in v09_body and "Yoda" not in v09_body
            notes_title, notes_body = app.version_series_notes("v0.8.x")
            assert notes_title == "Python File Commander — v0.8.x Changes"
            expected_minors = (8, 6, 3, 1, 0)
            for minor in expected_minors:
                assert f"v0.8.{minor} — Build " in notes_body
            for merged_minor in (7, 5, 4, 2):
                assert f"v0.8.{merged_minor} — Build " not in notes_body
            captured = []
            original_showinfo = pfc.messagebox.showinfo
            pfc.messagebox.showinfo = lambda title, body, **_kwargs: captured.append((title, body))
            try:
                changes_index = next(index for index in range(app.versions_menu.index("end") + 1)
                                     if app.versions_menu.type(index) == "command" and
                                     app.versions_menu.entrycget(index, "label") == "v0.8.x Changes")
                app.versions_menu.invoke(changes_index)
            finally:
                pfc.messagebox.showinfo = original_showinfo
            assert captured == [(notes_title, notes_body)], "Changes must open in one combined window"
            assert all(line.startswith("• Added:") or line.startswith("• Adjusted:")
                       for line in v09_body.splitlines() + notes_body.splitlines()
                       if line.startswith("•"))
            captured.clear()
            pfc.messagebox.showinfo = lambda title, body, **_kwargs: captured.append((title, body))
            try:
                yoda_index = next(
                    index for index in range(app.versions_menu.index("end") + 1)
                    if app.versions_menu.type(index) == "command" and
                    app.versions_menu.entrycget(index, "label") == "Yoda — Portable App Advocate")
                app.versions_menu.invoke(yoda_index)
            finally:
                pfc.messagebox.showinfo = original_showinfo
            assert captured and "advocate who helped bring this portable app into being" in captured[0][1]
            assert "report any issues" in captured[0][1] and "Use file operations carefully" in captured[0][1]
            assert app.recycle_bin_var.get() and app.continue_errors_var.get()
            assert ini_path.exists(), "pfc.ini was not generated on first launch"
            app.toggle_favorite()
            assert app.favorites, "Favorite folder was not stored"
            saved = configparser.ConfigParser(); saved.read(ini_path, encoding="utf-8")
            assert saved.getboolean("operations", "send_delete_to_recycle_bin")
            assert saved.get("hotkeys", "permanent_delete") == "<Shift-Delete>"
            assert saved.get("hotkeys", "versions_menu") == "<Alt-h>"
            assert saved.get("hotkeys", "quick_filter") == "<Control-y>"
            assert saved.get("hotkeys", "multi_rename") == "<Control-m>"
            assert saved.get("navigation", "favorites") != "[]"
            assert app.tab_style_var.get() == "right_skirt"
            skirt_height = int(float(app.left_tabs.bar.cget("height")))
            style_heights = set()
            for style in ("rounded", "squarish", "right_skirt"):
                app.tab_style_var.set(style); app.apply_tab_style(); app.update_idletasks()
                assert app.left_tabs._tab_style == style and app.right_tabs._tab_style == style
                style_heights.add(int(float(app.left_tabs.bar.cget("height"))))
            assert len(style_heights) == 1, "All tab styles must use the same height"
            app.tab_style_var.set("rounded"); app.apply_tab_style(); app.update_idletasks()
            rounded_polygons = [item for item in app.left_tabs.bar.find_all()
                                if app.left_tabs.bar.type(item) == "polygon"]
            assert rounded_polygons
            assert all(app.left_tabs.bar.itemcget(item, "smooth") in {"0", "false"}
                       for item in rounded_polygons), "Rounded bottoms must remain square"
            assert all(len(app.left_tabs.bar.coords(item)) > 8 for item in rounded_polygons)
            app.tab_style_var.set("right_skirt"); app.apply_tab_style(); app.update_idletasks()
            assert int(float(app.left_tabs.bar.cget("height"))) == skirt_height
            last_tab_right = app.left_tabs._hitboxes[-1][1]
            polygon_right = max(max(app.left_tabs.bar.coords(item)[::2])
                                for item in app.left_tabs.bar.find_all()
                                if app.left_tabs.bar.type(item) == "polygon")
            assert polygon_right > last_tab_right, "Right Skirt extension is missing"
            app.tab_style_var.set("compact"); app.apply_tab_style(save=False)
            assert app.tab_style_var.get() == "right_skirt"
            assert app.left_tabs._tab_style == "right_skirt"
            quick_root = Path(raw) / "quick-filter"; quick_root.mkdir()
            (quick_root / "alpha-report.txt").write_text("a", encoding="utf-8")
            (quick_root / "beta-report.txt").write_text("b", encoding="utf-8")
            source_pane = app.left_tabs.current(); source_pane.navigate(quick_root)
            source_pane.set_quick_filter("alpha"); app.update()
            assert len(source_pane.tree.get_children()) == 1
            assert source_pane.selected_paths()[0].name == "alpha-report.txt"
            app.save_config(); saved.read(ini_path, encoding="utf-8")
            assert "alpha" in saved.get("left", "tab_filters")
            source_pane.clear_quick_filter(); app.update()
            assert len(source_pane.tree.get_children()) == 2
            source_pane.tree.selection_set(source_pane.tree.get_children())
            app.multi_rename(); app.update()
            rename_window = app.multi_rename_window
            assert rename_window is not None and rename_window.winfo_exists()
            assert len(rename_window.tree.get_children()) == 2
            rename_window.mask_var.set("[N]_renamed"); app.update()
            assert "disabled" not in rename_window.apply_button.state()
            rename_window.destroy(); app.multi_rename_window = None

            compare_left, compare_right = Path(raw) / "compare-left", Path(raw) / "compare-right"
            compare_left.mkdir(); compare_right.mkdir()
            (compare_left / "copy-me.txt").write_text("sync", encoding="utf-8")
            planned = []
            compare_window = pfc.CompareWindow(app, app.config_data, app.save_config,
                                                lambda plans: planned.extend(plans))
            compare_window.withdraw(); compare_window.add(compare_left, compare_right)
            folder_frame = compare_window.nametowidget(compare_window.notebook.select())
            deadline = time.time() + 3
            while folder_frame._scanning and time.time() < deadline:
                app.update(); time.sleep(0.01)
            assert not folder_frame._scanning
            assert compare_window.focus_get() is folder_frame.tree
            row = next(iid for iid in folder_frame.tree.get_children()
                       if folder_frame.item_keys[iid] == "copy-me.txt")
            folder_frame.tree.selection_set(row); folder_frame.set_action("right")
            original_plan_ask = pfc.SyncPlanDialog.__dict__["ask"]
            pfc.SyncPlanDialog.ask = classmethod(lambda _cls, _parent, _plans: True)
            try:
                folder_frame.dry_run()
            finally:
                pfc.SyncPlanDialog.ask = original_plan_ask
            assert planned == [(compare_left / "copy-me.txt", compare_right / "copy-me.txt")]
            compare_window.close()
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
