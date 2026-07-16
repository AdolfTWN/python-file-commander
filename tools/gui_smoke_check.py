"""Non-destructive smoke check for the generated portable GUI."""

import tempfile
from pathlib import Path
import sys
import configparser
import json
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
            assert app.header_left_widgets[0].cget("text") == "PFC"
            assert app.header_left_widgets[1].cget("text") == f"v{pfc.__version__}"
            assert all("Build" not in widget.cget("text") for widget in app.header_left_widgets)
            for menu_button in (app.files_menu_button, app.view_menu_button, app.versions_menu_button):
                assert menu_button.cget("relief") == "raised"
                assert isinstance(menu_button, pfc.tk.Button)
            hierarchy_indexes = [index for index in range(app.view_menu.index("end") + 1)
                                 if app.view_menu.type(index) == "cascade"]
            assert len(hierarchy_indexes) == 5
            assert all(not app.view_menu.entrycget(index, "accelerator")
                       for index in hierarchy_indexes)
            pfc._refresh_scaled_indicators(app.font_size_menu)
            selected_font_entries = [index for index in range(app.font_size_menu.index("end") + 1)
                                     if app.font_size_menu.entrycget(index, "accelerator") == "✓"]
            assert len(selected_font_entries) == 1
            assert int(app.font_size_menu.entrycget(selected_font_entries[0], "indicatoron")) == 0
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
            assert version_labels == ["Current version: v0.12.0", "v0.12.x Changes", "v0.11.x Changes", "v0.10.x Changes",
                                      "v0.9.x Changes", "v0.8.x Changes",
                                      "Yoda — Portable App Advocate"]
            assert app.version_series == ("v0.12.x", "v0.11.x", "v0.10.x", "v0.9.x", "v0.8.x")
            v11_title, v11_body = app.version_series_notes("v0.11.x")
            assert v11_title == "Python File Commander — v0.11.x Changes"
            assert "v0.11.1 — Build 2026/07/16" in v11_body
            assert "v0.11.0 — Build 2026/07/16" in v11_body
            assert "• Adjusted: UI language changes apply immediately" in v11_body
            assert "• Adjusted: Improved font rendering" in v11_body
            assert "• Adjusted: Replaced compact version pop-ups" in v11_body
            assert "• Added: Configurable two-to-four-panel layout" in v11_body
            assert "• Added: Visual clipboard summary" in v11_body
            assert "• Added: English, Traditional Chinese" in v11_body
            v10_title, v10_body = app.version_series_notes("v0.10.x")
            assert v10_title == "Python File Commander — v0.10.x Changes"
            assert "v0.10.0 — Build 2026/07/16" in v10_body
            assert "• Added: Mouse drag reordering" in v10_body
            assert "• Added: Native file drag-and-drop" in v10_body
            assert "• Added: File and folder context menu" in v10_body
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
            changes_index = next(index for index in range(app.versions_menu.index("end") + 1)
                                 if app.versions_menu.type(index) == "command" and
                                 app.versions_menu.entrycget(index, "label") == "v0.8.x Changes")
            app.versions_menu.invoke(changes_index); app.update_idletasks(); app.update()
            assert app.version_window is not None and app.version_window.winfo_exists()
            assert app.version_window.title() == notes_title
            assert app.version_text.get("1.0", "end-1c") == notes_body
            assert app.version_text.cget("font") == str(pfc.tkfont.nametofont("TkDefaultFont"))
            assert tuple(app.version_window.minsize()) == (720, 500)
            app.version_window.destroy()
            assert "Windows File Explorer" not in v09_body
            assert all(line.startswith("• Added:") or line.startswith("• Adjusted:")
                       for line in v11_body.splitlines() + v10_body.splitlines() + v09_body.splitlines() + notes_body.splitlines()
                       if line.startswith("•"))
            captured = []
            original_showinfo = pfc.messagebox.showinfo
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
            assert not saved.has_option("hotkeys", "multi_rename")
            assert saved.get("navigation", "favorites") != "[]"
            assert app.panel_count_var.get() == 2 and len(app.split.panes()) == 2
            panel_labels = [app.panel_counts_menu.entrycget(index, "label")
                            for index in range(app.panel_counts_menu.index("end") + 1)]
            assert panel_labels == ["2 Panels", "3 Panels", "4 Panels"]
            language_labels = [app.language_menu.entrycget(index, "label")
                               for index in range(app.language_menu.index("end") + 1)]
            assert language_labels == ["English", "繁體中文", "简体中文", "한국어"]
            assert app.ui_language_var.get() == "en"
            app.panel_count_var.set(4); app.apply_panel_count(save=False); app.update()
            assert len(app.split.panes()) == 4 and len(app.visible_panes()) == 4
            assert all(tabs.current().shell_drop_target.active for tabs in app.panel_tabs)
            app.set_active(app.panel_tabs[2].current())
            assert app.panes()[1] is app.panel_tabs[3].current()
            app.set_active(app.panel_tabs[3].current())
            assert app.panes()[1] is app.panel_tabs[0].current(), "Rightmost target must wrap left"
            app.save_config(); saved.read(ini_path, encoding="utf-8")
            assert saved.getint("view", "panel_count") == 4
            assert saved.get("view", "ui_language") == "en"
            assert saved.has_section("panel3") and saved.has_section("panel4")
            app.panel_count_var.set(2); app.apply_panel_count(save=False); app.set_active(app.left_tabs.current())
            assert len(app.split.panes()) == 2
            clipboard_file_a = Path(raw) / "first-report.txt"
            clipboard_file_b = Path(raw) / "second-report.pdf"
            clipboard_folder = Path(raw) / "clipboard-folder"
            clipboard_file_a.write_text("a", encoding="utf-8")
            clipboard_file_b.write_text("b", encoding="utf-8")
            clipboard_folder.mkdir()
            app._set_clipboard_visual("Clipboard: first-report.txt",
                                      [clipboard_file_a, clipboard_file_b, clipboard_folder], "paths",
                                      trailing=" and 2 items...")
            assert app.clipboard_summary.cget("text") == "Clipboard: first-report.txt and 2 items..."
            assert len(app._clipboard_icon_images) == 1
            assert sum(app.clipboard_icon_canvas.type(item) == "image"
                       for item in app.clipboard_icon_canvas.find_all()) == 1
            assert app.left_tabs.current().shell_drop_target.active
            assert app.right_tabs.current().shell_drop_target.active
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
            reorder_a = Path(raw) / "reorder-a"; reorder_a.mkdir()
            reorder_b = Path(raw) / "reorder-b"; reorder_b.mkdir()
            app.left_tabs.add_tab(reorder_a)
            app.left_tabs.add_tab(reorder_b)
            app.update_idletasks(); app.left_tabs.redraw()
            original_order = app.left_tabs.panes()
            dragged = original_order[-1]
            last_left, last_right, _ = app.left_tabs._hitboxes[-1]
            first_left, _first_right, _ = app.left_tabs._hitboxes[0]
            app.left_tabs._tab_press(SimpleNamespace(x=(last_left + last_right) // 2))
            app.left_tabs._tab_motion(SimpleNamespace(x=first_left))
            app.left_tabs._tab_release(SimpleNamespace(x=first_left))
            assert app.left_tabs.panes()[0] is dragged
            app.save_config(); saved.read(ini_path, encoding="utf-8")
            assert json.loads(saved.get("left", "tabs"))[0] == str(reorder_b)
            explorer_target = Path(raw) / "explorer-target"; explorer_target.mkdir()
            explorer_copy = Path(raw) / "explorer-copy.txt"
            explorer_copy.write_text("copy", encoding="utf-8")
            explorer_move = Path(raw) / "explorer-move.txt"
            explorer_move.write_text("move", encoding="utf-8")
            target_pane = app.right_tabs.current(); target_pane.navigate(explorer_target)
            app.update_idletasks()
            drop_x = target_pane.tree.winfo_rootx() + 8
            drop_y = target_pane.tree.winfo_rooty() + target_pane.tree.winfo_height() - 8
            app._handle_internal_drag("external_drop", target_pane, {
                "paths": [explorer_copy], "x_root": drop_x, "y_root": drop_y, "move": False,
            })
            assert explorer_copy.exists() and (explorer_target / explorer_copy.name).exists()
            app._handle_internal_drag("external_drop", target_pane, {
                "paths": [explorer_move], "x_root": drop_x, "y_root": drop_y, "move": True,
            })
            assert not explorer_move.exists() and (explorer_target / explorer_move.name).exists()
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
            app.set_active(source_pane); app.update()
            assert app.action_button_by_hotkey["F2"].cget("text") == "F2 Multi-Rename"
            app.multi_rename(); app.update()
            rename_window = app.multi_rename_window
            assert rename_window is not None and rename_window.winfo_exists()
            assert len(rename_window.tree.get_children()) == 2
            rename_window.mask_var.set("[N]_renamed"); app.update()
            assert "disabled" not in rename_window.apply_button.state()
            rename_window.destroy(); app.multi_rename_window = None
            source_pane.tree.selection_set(source_pane.tree.get_children()[0]); app.update()
            assert app.action_button_by_hotkey["F2"].cget("text") == "F2 Rename"
            selected_rows = source_pane.tree.get_children()
            source_pane.tree.selection_set(selected_rows)
            first_box = source_pane.tree.bbox(selected_rows[0])
            context_calls = []
            original_context = source_pane.on_context
            source_pane.on_context = lambda *args: context_calls.append(args)
            try:
                source_pane._context_click(SimpleNamespace(
                    y=first_box[1] + max(1, first_box[3] // 2), x_root=50, y_root=50))
            finally:
                source_pane.on_context = original_context
            assert len(source_pane.tree.selection()) == 2, "Right-click must preserve multi-selection"
            assert context_calls and source_pane.tree.bind("<Shift-F10>")
            context_menu = app._build_file_context_menu(source_pane, source_pane.selected_paths()[0])
            context_labels = [context_menu.entrycget(index, "label")
                              for index in range(context_menu.index("end") + 1)
                              if context_menu.type(index) == "command"]
            required_context = {"Open / Enter Folder", "Preview", "Compare",
                                "Copy to Clipboard", "Cut to Clipboard",
                                "Paste into Current Folder", "Copy to Next Panel",
                                "Move to Next Panel", "Rename", "Multi-Rename",
                                "Copy Path", "Delete", "Permanent Delete"}
            assert required_context.issubset(context_labels)
            rename_index = context_labels.index("Rename")
            rename_menu_index = next(index for index in range(context_menu.index("end") + 1)
                                     if context_menu.type(index) == "command" and
                                     context_menu.entrycget(index, "label") == context_labels[rename_index])
            multi_index = next(index for index in range(context_menu.index("end") + 1)
                               if context_menu.type(index) == "command" and
                               context_menu.entrycget(index, "label") == "Multi-Rename")
            assert context_menu.entrycget(rename_menu_index, "state") == "disabled"
            assert context_menu.entrycget(multi_index, "state") == "normal"
            context_folder = quick_root / "context-folder"; context_folder.mkdir()
            source_pane.refresh(); source_pane.select_path(context_folder)
            app._build_file_context_menu(source_pane, context_folder)
            folder_labels = [app.file_context_menu.entrycget(index, "label")
                             for index in range(app.file_context_menu.index("end") + 1)
                             if app.file_context_menu.type(index) == "command"]
            assert "Open Folder in New Tab" in folder_labels
            assert "Paste into This Folder" in folder_labels

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
            original_point_owner = pfc.point_belongs_to_process
            pfc.point_belongs_to_process = lambda _x, _y: True
            try:
                app._handle_internal_drag("start", source, event)
                assert app._drag_state is not None and app._drag_state["target"] is not None
                event.state = 1; app._handle_internal_drag("motion", source, event)
                assert app._drag_state["mode"] == "move"
                app._handle_internal_drag("cancel", source, event)
            finally:
                pfc.point_belongs_to_process = original_point_owner
            assert app._drag_state is None and app._drag_ghost is None
            selected_before = app.active.selected_paths()
            path_before = app.active.path
            app.ui_language_var.set("zh_TW"); app.apply_ui_language(); app.update()
            assert app.files_menu_button.cget("text") == "檔案"
            assert app.active.tree.heading("#0", "text").startswith("名稱")
            assert app.active.path == path_before and app.active.selected_paths() == selected_before
            app.ui_language_var.set("en"); app.apply_ui_language(); app.update()
            assert app.files_menu_button.cget("text") == "Files"
            app.withdraw()
            print("GUI smoke check passed", flush=True)
        finally:
            if app is not None:
                app.destroy()
            pfc.Commander._find_ini_path = original

    localized = {
        "en": ("Files", "View", "Name", "v0.11.x Changes", "• Added: Configurable"),
        "zh_TW": ("檔案", "檢視", "名稱", "v0.11.x 變更內容", "• 新增：可設定"),
        "zh_CN": ("文件", "查看", "名称", "v0.11.x 更新内容", "• 新增：可配置"),
        "ko": ("파일", "보기", "이름", "v0.11.x 변경 내용", "• 추가: 패널 상태"),
    }
    original = pfc.Commander._find_ini_path
    with tempfile.TemporaryDirectory() as raw:
        for code, expected in localized.items():
            ini_path = Path(raw) / f"pfc-{code}.ini"
            ini_path.write_text(f"[view]\nui_language = {code}\n", encoding="utf-8")
            pfc.Commander._find_ini_path = staticmethod(lambda path=ini_path: path)
            app = pfc.Commander(); app.withdraw(); app.update_idletasks()
            try:
                assert app.files_menu_button.cget("text") == expected[0]
                assert app.view_menu_button.cget("text") == expected[1]
                assert app.left_tabs.current().tree.heading("#0", "text").startswith(expected[2])
                assert app.language_menu.entrycget(0, "label") == "English"
                assert app.language_menu.entrycget(1, "label") == "繁體中文"
                title, body = app.version_series_notes("v0.11.x")
                assert expected[3] in title
                assert expected[4] in body
                missing_notes = app.version_series_notes("v9.9.x")[1]
                assert (missing_notes == "No release notes available.") == (code == "en")
            finally:
                app.destroy()
    pfc.Commander._find_ini_path = original
    print("Localized GUI smoke check passed", flush=True)


if __name__ == "__main__":
    main()
