from __future__ import annotations

import os
import configparser
import ctypes
import json
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from . import __version__
from .fileops import OperationFailure, OperationResult, copy_items, delete_items, format_size, is_system, move_items, recycle_items, roots
from .clipboard import clear_file_clipboard, extract_virtual_files, get_file_clipboard, get_virtual_file_descriptors, set_file_clipboard
from .icons import ShellIconProvider
from .compare import CompareWindow
from .preview import PreviewWindow
from .search import SearchWindow
from .multirename import MultiRenameWindow
from .shelldnd import DROPEFFECT_COPY, DROPEFFECT_MOVE, ShellFileDropTarget, point_belongs_to_process, start_shell_drag
from .tooltip import MenuToolTip, install_button_tooltips
from .tabs import ChamferNotebook, TAB_STYLES
from .i18n import LANGUAGES, set_language, tr


PANEL_SECTIONS = ("left", "right", "panel3", "panel4")

# The single-file builder replaces this fallback with a fixed date literal.
BUILD_DATE = datetime.now().strftime("%Y/%m/%d")
VERSION_HISTORY = (
    ("v0.11.0", "2026/07/16", (
        "Added: Configurable two-to-four-panel layout with persistent panel state and next-panel operations.",
        "Added: Visual clipboard summary with overlapping native icons and concise remaining-item counts.",
        "Added: English, Traditional Chinese, Simplified Chinese, and Korean user interfaces.",
    )),
    ("v0.10.0", "2026/07/16", (
        "Added: Mouse drag reordering for tabs with persistent panel order.",
        "Added: Native file drag-and-drop between PFC and Windows File Explorer.",
        "Added: File and folder context menu with frequent operations and keyboard access.",
    )),
    ("v0.9.0", "2026/07/14", (
        "Added: Folder Compare with background scanning, filters, content checks, and copy-only Safe Sync dry runs.",
        "Added: Per-tab Quick Filter for the active file list.",
        "Added: Multi-Rename with live preview, validation, rollback, and in-session undo.",
    )),
    ("v0.8.8", "2026/07/14", (
        "Adjusted: Combined the v0.8.x change history into one window.",
    )),
    ("v0.8.6", "2026/07/14", (
        "Added: Right Skirt, Rounded, and Squarish tab styles with saved preference.",
        "Adjusted: Made Right Skirt the default and kept all tab styles at equal height.",
    )),
    ("v0.8.3", "2026/07/14", (
        "Added: Internal drag-and-drop with Copy and Shift+Move destination feedback.",
        "Added: Outlook attachment paste with attachment-aware clipboard summary.",
        "Adjusted: Aligned menu actions and keyboard shortcuts into separate columns.",
    )),
    ("v0.8.1", "2026/07/14", (
        "Added: Recycle Bin delete and explicit Shift+Del permanent delete.",
        "Added: Copy, move, and paste conflict choices with partial-failure recovery.",
        "Added: Keyboard-accessible Favorites and Recent Folders.",
    )),
    ("v0.8.0", "2026/07/13", (
        "Added: Dual file panels with tabs, navigation, sorting, and portable INI settings.",
        "Added: Preview, Search, Compare, and end-to-end keyboard operation.",
    )),
)


def ensure_config_defaults(config: configparser.ConfigParser) -> None:
    defaults = {
        "view": {"font_size": "small", "tab_style": "right_skirt", "panel_count": "2", "ui_language": "en"},
        "refresh": {"auto_refresh": "true", "active_interval_ms": "2000",
                    "background_interval_ms": "10000", "network_interval_ms": "5000"},
        "operations": {"send_delete_to_recycle_bin": "true", "continue_after_error": "true"},
        "navigation": {"favorites": "[]", "recent_folders": "[]"},
    }
    for section, values in defaults.items():
        if not config.has_section(section):
            config.add_section(section)
        for key, value in values.items():
            if not config.has_option(section, key):
                config.set(section, key, value)


def write_config_atomic(config: configparser.ConfigParser, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            config.write(stream)
        temporary.replace(path)
    except OSError:
        try: temporary.unlink(missing_ok=True)
        except OSError: pass
        raise


def hide_private_console() -> bool:
    """Hide a console created only for PFC, without hiding a user's shell."""
    if os.name != "nt":
        return False
    kernel32, user32 = ctypes.windll.kernel32, ctypes.windll.user32
    kernel32.GetConsoleWindow.restype = ctypes.c_void_p
    process_ids = (ctypes.c_uint32 * 64)()
    count = kernel32.GetConsoleProcessList(process_ids, len(process_ids))
    # An existing CMD/PowerShell console includes at least the shell and Python.
    if count != 1:
        return False
    window = kernel32.GetConsoleWindow()
    if not window:
        return False
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.ShowWindow(window, 0)  # SW_HIDE
    return True


def relaunch_with_pythonw() -> bool:
    """Hand a Windows GUI launch from python.exe to pythonw.exe once."""
    if os.name != "nt" or os.environ.get("PFC_PYTHONW") == "1":
        return False
    executable = Path(sys.executable)
    if executable.name.casefold() == "pythonw.exe":
        return False
    pythonw = executable.with_name("pythonw.exe")
    if not pythonw.is_file():
        return False
    environment = os.environ.copy()
    environment["PFC_PYTHONW"] = "1"
    subprocess.Popen([str(pythonw), *sys.argv], cwd=os.getcwd(), env=environment,
                     close_fds=True, creationflags=0x00000008)  # DETACHED_PROCESS
    return True


class FilePane(ttk.Frame):
    columns = ("ext", "size", "modified", "attr")
    all_sort_columns = ("name", "ext", "size", "modified", "attr")
    base_widths = {"name": 300, "ext": 55, "size": 85, "modified": 135, "attr": 55}

    def __init__(self, master: tk.Misc, on_activate, on_change=lambda: None,
                 on_drag=lambda _action, _pane, _event: None,
                 on_context=lambda _pane, _path, _x, _y: None) -> None:
        super().__init__(master)
        self.on_activate = on_activate
        self.on_change = on_change
        self.on_drag = on_drag
        self.on_context = on_context
        self.path = Path.home()
        self.history: list[Path] = []
        self.sort_column = "name"
        self.reverse = False
        self.show_hidden = False
        self.show_system = False
        self.show_extensions = True
        self.mode = "files"
        self.display_title = self.path.name or str(self.path)
        self.lock_mode = "unlocked"
        self.locked_path: Path | None = None
        self.on_locked_navigation = lambda _path: None
        self._signature = None
        self.quick_filter_var = tk.StringVar()
        self.quick_filter_visible = False
        self._drag_press_item = None
        self._drag_press_xy = None
        self._dragging = False
        self.heading_labels = {"name": tr("Name"), "ext": tr("Ext"), "size": tr("Size"),
                               "modified": tr("Date Modified"), "attr": tr("Attr")}
        self.icons = ShellIconProvider()

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 3))
        self.drive = ttk.Combobox(bar, state="readonly", width=8, values=[str(p) for p in roots()])
        self.drive.pack(side="left")
        self.drive.bind("<<ComboboxSelected>>", lambda _e: self.navigate(Path(self.drive.get())))
        ttk.Button(bar, text="↑", width=3, command=self.up).pack(side="left", padx=2)
        ttk.Button(bar, text="⌂", width=3, command=lambda: self.navigate(Path.home())).pack(side="left")
        self.path_var = tk.StringVar()
        self.path_entry = ttk.Entry(bar, textvariable=self.path_var)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.path_entry.bind("<Return>", self.navigate_from_entry)

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=self.columns, show="tree headings", selectmode="extended", style="Inactive.Treeview")
        self.tree.heading("#0", text=tr("Name") + " ▲", command=lambda: self.change_sort("name"))
        self.tree.column("#0", width=self.base_widths["name"], minwidth=120, stretch=True)
        for col in self.columns:
            marker = ""
            self.tree.heading(col, text=self.heading_labels[col] + marker, command=lambda c=col: self.change_sort(c))
            self.tree.column(col, width=self.base_widths[col], stretch=False, anchor="e" if col == "size" else "w")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        horizontal.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.open_selected)
        self.tree.bind("<Return>", self.open_selected)
        self.tree.bind("<FocusIn>", lambda _e: self.on_activate(self))
        self.tree.bind("<ButtonPress-1>", self._drag_press, add="+")
        self.tree.bind("<B1-Motion>", self._drag_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self._drag_release, add="+")
        self.tree.bind("<Button-3>", self._context_click)
        self.tree.bind("<Shift-F10>", self._context_keyboard)
        self.tree.bind("<KeyPress-Menu>", self._context_keyboard)
        self.tree.tag_configure("PFC_DROP_TARGET", background="#8ec8f0", foreground="#102b3c")
        self.quick_filter_bar = ttk.Frame(self)
        ttk.Label(self.quick_filter_bar, text=tr("Quick Filter:")).pack(side="left")
        self.quick_filter_entry = ttk.Entry(self.quick_filter_bar, textvariable=self.quick_filter_var)
        self.quick_filter_entry.pack(side="left", fill="x", expand=True, padx=(4, 3))
        ttk.Button(self.quick_filter_bar, text="×", width=3, command=self.clear_quick_filter).pack(side="right")
        self.quick_filter_entry.bind("<Escape>", lambda _event: self.clear_quick_filter())
        self.quick_filter_entry.bind("<Return>", lambda _event: self.focus_file_list())
        self.quick_filter_var.trace_add("write", self._quick_filter_changed)
        self.status = ttk.Label(self, anchor="w")
        self.status.pack(fill="x", pady=(3, 0))
        install_button_tooltips(self)
        self.navigate(self.path)
        try:
            self.shell_drop_target = ShellFileDropTarget(self.tree, self._shell_files_dropped)
        except OSError:
            self.shell_drop_target = None

    def _shell_files_dropped(self, paths, x_root: int, y_root: int, move: bool) -> None:
        self.on_drag("external_drop", self, {
            "paths": list(paths), "x_root": x_root, "y_root": y_root, "move": move,
        })

    def _drag_press(self, event):
        if self.tree.identify_region(event.x, event.y) not in {"tree", "cell"}:
            self._drag_press_item = None; self._drag_press_xy = None; return None
        self._drag_press_item = self.tree.identify_row(event.y)
        self._drag_press_xy = (event.x_root, event.y_root)
        self._dragging = False
        if self._drag_press_item in self.tree.selection():
            self.tree.focus(self._drag_press_item); self.tree.focus_set()
            return "break"  # Preserve an existing multi-selection while beginning a drag.
        return None

    def _drag_motion(self, event):
        if not self._drag_press_item or self._drag_press_xy is None:
            return None
        if not self._dragging:
            if abs(event.x_root - self._drag_press_xy[0]) < 6 and abs(event.y_root - self._drag_press_xy[1]) < 6:
                return None
            if self._drag_press_item not in self.tree.selection():
                self.tree.selection_set(self._drag_press_item)
            self._dragging = True
            self.on_drag("start", self, event)
        else:
            self.on_drag("motion", self, event)
        return "break"

    def _drag_release(self, event):
        was_dragging = self._dragging
        if was_dragging:
            self.on_drag("drop", self, event)
        self._drag_press_item = None; self._drag_press_xy = None; self._dragging = False
        return "break" if was_dragging else None

    def _context_click(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return None
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        self.tree.focus(iid); self.tree.focus_set(); self.on_activate(self)
        tags = self.tree.item(iid, "tags")
        if tags:
            self.on_context(self, Path(tags[0]), event.x_root, event.y_root)
        return "break"

    def _context_keyboard(self, _event=None):
        iid = self.tree.focus() or (self.tree.selection()[0] if self.tree.selection() else "")
        if not iid:
            return "break"
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        self.tree.focus(iid); self.tree.focus_set(); self.on_activate(self)
        tags, box = self.tree.item(iid, "tags"), self.tree.bbox(iid)
        if tags:
            x = self.tree.winfo_rootx() + (box[0] + 20 if box else 20)
            y = self.tree.winfo_rooty() + (box[1] + box[3] if box else 20)
            self.on_context(self, Path(tags[0]), x, y)
        return "break"

    def navigate(self, path: Path, bypass_lock: bool = False) -> bool:
        try:
            path = path.expanduser().resolve()
            if not path.is_dir():
                raise NotADirectoryError(path)
            if not bypass_lock and self.lock_mode == "locked" and path != self.path:
                self.on_locked_navigation(path)
                return False
            if path != self.path:
                self.history.append(self.path)
            self.path = path
            self.mode = "files"
            self.display_title = path.name or str(path)
            self.path_var.set(str(path))
            if os.name == "nt":
                self.drive.set(path.anchor)
            self.refresh()
            self.on_change()
            return True
        except OSError as exc:
            self.path_var.set(str(self.path))
            messagebox.showerror(tr("Cannot open folder"), str(exc))
            return False

    def up(self) -> None:
        self.navigate(self.path.parent)

    def navigate_from_entry(self, _event=None) -> str:
        if self.navigate(Path(self.path_var.get().strip().strip('"'))):
            self.focus_file_list()
        return "break"

    def change_sort(self, column: str) -> None:
        self.reverse = not self.reverse if self.sort_column == column else False
        self.sort_column = column
        for col in self.all_sort_columns:
            marker = (" ▲" if not self.reverse else " ▼") if col == self.sort_column else ""
            target = "#0" if col == "name" else col
            self.tree.heading(target, text=self.heading_labels[col] + marker)
        self.refresh()
        self.on_change()

    def refresh(self) -> None:
        selected = {self.tree.item(i, "tags")[0] for i in self.tree.selection() if self.tree.item(i, "tags")}
        scroll_position = self.tree.yview()[0] if self.tree.get_children() else 0.0
        self.tree.delete(*self.tree.get_children())
        try:
            entries = [p for p in self.path.iterdir()
                       if (self.show_hidden or not p.name.startswith(".")) and (self.show_system or not is_system(p))]
            self._signature = self.signature_for(entries)
            needle = self.quick_filter_var.get().strip().casefold()
            if needle:
                entries = [path for path in entries if needle in path.name.casefold()]
            def key(p: Path):
                try:
                    stat = p.stat()
                    values = {"name": p.name.lower(), "ext": p.suffix.lower(), "size": stat.st_size,
                              "modified": stat.st_mtime, "attr": p.name.startswith(".")}
                    return (not p.is_dir(), values[self.sort_column])
                except OSError:
                    return (True, p.name.lower())
            entries.sort(key=key, reverse=self.reverse)
            total = 0
            for p in entries:
                try:
                    stat = p.stat()
                    is_dir = p.is_dir()
                    total += 0 if is_dir else stat.st_size
                    visible_name = p.name if is_dir or self.show_extensions else p.stem
                    name = f"[{visible_name}]" if is_dir else visible_name
                    values = ("" if is_dir else p.suffix[1:], "<DIR>" if is_dir else format_size(stat.st_size),
                              datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                              ("d" if is_dir else "-") + ("h" if p.name.startswith(".") else "-"))
                    iid = self.tree.insert("", "end", text=name, image=self.icons.get(p, is_dir), values=values, tags=(str(p),))
                    if str(p) in selected:
                        self.tree.selection_add(iid)
                except OSError:
                    continue
            filter_status = tr(" — filter: {filter}", filter=self.quick_filter_var.get().strip()) if needle else ""
            self.status.configure(text=tr("{count} items   {size}", count=len(entries),
                                          size=format_size(total)) + filter_status)
            current = self.tree.selection()
            children = self.tree.get_children()
            if not current and children:
                self.tree.selection_set(children[0])
                self.tree.focus(children[0])
                self.tree.see(children[0])
            elif children:
                self.tree.yview_moveto(scroll_position)
        except OSError as exc:
            messagebox.showerror(tr("Cannot read folder"), str(exc))

    @staticmethod
    def signature_for(entries) -> tuple:
        signature = []
        for path in entries:
            try:
                stat = path.stat()
                signature.append((path.name, stat.st_size, stat.st_mtime_ns, stat.st_mode))
            except OSError:
                signature.append((path.name, None, None, None))
        return tuple(sorted(signature))

    def refresh_if_changed(self) -> bool:
        if self.mode != "files":
            return False
        try:
            entries = [p for p in self.path.iterdir()
                       if (self.show_hidden or not p.name.startswith(".")) and (self.show_system or not is_system(p))]
            signature = self.signature_for(entries)
        except OSError:
            return False
        if signature == self._signature:
            return False
        self.refresh()
        return True

    def selected_paths(self) -> list[Path]:
        result = []
        for iid in self.tree.selection():
            tags = self.tree.item(iid, "tags")
            if tags:
                result.append(Path(tags[0]))
        return result

    def select_path(self, path: Path) -> None:
        for iid in self.tree.get_children():
            tags = self.tree.item(iid, "tags")
            if tags and Path(tags[0]) == path:
                self.tree.selection_set(iid); self.tree.focus(iid); self.tree.see(iid); break

    def focus_file_list(self) -> None:
        children = self.tree.get_children()
        selected = self.tree.selection()
        target = selected[0] if selected else (children[0] if children else None)
        if target is not None:
            if not selected:
                self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)
        self.tree.focus_set()

    def _quick_filter_changed(self, *_args) -> None:
        if self.mode == "files":
            self.refresh()
            self.on_change()

    def set_quick_filter(self, value: str) -> None:
        self.quick_filter_var.set(value)
        if value and not self.quick_filter_visible:
            self.quick_filter_bar.pack(fill="x", pady=(2, 0), before=self.status)
            self.quick_filter_visible = True

    def toggle_quick_filter(self) -> str:
        if not self.quick_filter_visible:
            self.quick_filter_bar.pack(fill="x", pady=(2, 0), before=self.status)
            self.quick_filter_visible = True
            if self.mode != "files":
                self.mode = "files"; self.path_var.set(str(self.path)); self.refresh()
            self.quick_filter_entry.focus_set(); self.quick_filter_entry.selection_range(0, "end")
        else:
            self.clear_quick_filter()
        return "break"

    def clear_quick_filter(self) -> str:
        self.quick_filter_var.set("")
        if self.quick_filter_visible:
            self.quick_filter_bar.pack_forget(); self.quick_filter_visible = False
        self.focus_file_list()
        self.on_change()
        return "break"

    def open_selected(self, _event=None) -> None:
        items = self.selected_paths()
        if not items:
            return
        item = items[0]
        if item.is_dir():
            self.navigate(item)
        else:
            try:
                os.startfile(item) if os.name == "nt" else subprocess.Popen(["xdg-open", str(item)])
            except OSError as exc:
                messagebox.showerror(tr("Cannot open file"), str(exc))

    def show_preview(self, item: Path) -> None:
        self.mode = "preview"
        self.display_title = item.name
        self.tree.delete(*self.tree.get_children())
        self.path_var.set(f"[Preview] {item}")
        try:
            stat = item.stat()
            details = [
                f"Name: {item.name}",
                f"Path: {item}",
                f"Size: {format_size(stat.st_size)}",
                f"Modified: {datetime.fromtimestamp(stat.st_mtime):%Y-%m-%d %H:%M:%S}",
                "",
            ]
            if item.is_dir():
                details.append("Folder preview: press Right to enter it.")
            elif item.suffix.lower() in {".txt", ".md", ".csv", ".json", ".xml", ".log", ".py", ".ini", ".yaml", ".yml"}:
                with item.open("r", encoding="utf-8", errors="replace") as stream:
                    details.extend(line.rstrip("\r\n") for _, line in zip(range(300), stream))
            else:
                details.append("Binary file: metadata preview only.")
            for line in details:
                self.tree.insert("", "end", text=line, values=("", "", "", ""))
            self.status.configure(text=f"Previewing {item.name}")
            self.on_change()
        except OSError as exc:
            messagebox.showerror(tr("Preview failed"), str(exc))

    def search(self, query: str) -> None:
        self.mode = "search"
        self.display_title = f"Search: {query}"
        self.tree.delete(*self.tree.get_children())
        self.path_var.set(f"[Search] {query} in {self.path}")
        query = query.casefold()
        count = 0
        try:
            for item in self.path.rglob("*"):
                if query not in item.name.casefold():
                    continue
                try:
                    stat = item.stat()
                    is_dir = item.is_dir()
                    relative = item.relative_to(self.path)
                    display = str(relative if is_dir or self.show_extensions else relative.with_name(item.stem))
                    self.tree.insert("", "end", text=display, image=self.icons.get(item, is_dir), values=(
                        "" if is_dir else item.suffix[1:], "<DIR>" if is_dir else format_size(stat.st_size),
                        datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"), "d-" if is_dir else "--"),
                        tags=(str(item),))
                    count += 1
                    if count >= 2000:
                        break
                except OSError:
                    continue
            self.status.configure(text=f"{count} match(es)" + (" (limited to 2000)" if count == 2000 else ""))
            self.on_change()
        except OSError as exc:
            messagebox.showerror(tr("Search failed"), str(exc))

    def toggle_hidden(self) -> None:
        self.show_hidden = not self.show_hidden
        self.refresh()
        self.on_change()

    def toggle_system(self) -> None:
        self.show_system = not self.show_system
        self.refresh()
        self.on_change()

    def set_active_appearance(self, active: bool) -> None:
        self.tree.configure(style="Active.Treeview" if active else "Inactive.Treeview")

    def apply_scale(self, scale: float) -> None:
        icon_size = max(16, round(16 * scale))
        if self.icons.size != icon_size:
            self.icons = ShellIconProvider(icon_size)
        self.tree.column("#0", width=round(self.base_widths["name"] * scale), minwidth=120, stretch=True)
        for column in self.columns:
            self.tree.column(column, width=round(self.base_widths[column] * scale))
        self.refresh()


class PaneTabs(ChamferNotebook):
    def __init__(self, master: tk.Misc, on_activate, on_change=lambda: None, initial_paths=None,
                 color_for=lambda _path: "default", on_tab_color=lambda _path, _color: None,
                 on_drag=lambda _action, _pane, _event: None,
                 on_context=lambda _pane, _path, _x, _y: None,
                 tab_style="right_skirt") -> None:
        self.color_for = color_for
        self.on_tab_color = on_tab_color
        self.on_drag = on_drag
        self.on_context = on_context
        super().__init__(master, on_color_changed=self._color_changed,
                         on_lock_changed=self._lock_changed,
                         on_tabs_reordered=self._tabs_reordered, tab_style=tab_style)
        self.on_activate = on_activate
        self.on_change = on_change
        self.bind("<<NotebookTabChanged>>", lambda _e: self._tab_changed())
        for path in initial_paths or [Path.home()]:
            self.add_tab(path, notify=False)

    def add_tab(self, path: Path, notify: bool = True) -> FilePane:
        position = self.index(self.select()) + 1 if self.tabs() else 0
        pane = FilePane(self, self.on_activate, on_drag=self.on_drag,
                        on_context=self.on_context)
        pane.on_change = lambda source=pane: self._pane_changed(source)
        pane.on_locked_navigation = lambda target, source=pane: self.add_tab(target)
        pane.navigate(path)
        self.add(pane, text=path.name or str(path), color="default", position=position)
        self.select(pane)
        pane.tree.focus_set()
        if notify:
            self.on_change()
        return pane

    def _pane_changed(self, pane: FilePane) -> None:
        if not self.tabs():
            self.on_change()
            return
        try:
            self.tab(pane, text=pane.display_title)
        except (tk.TclError, AttributeError):
            pass
        self.on_change()

    def _tab_changed(self) -> None:
        try:
            pane = self.current()
            self.on_activate(pane)
            self.after_idle(pane.focus_file_list)
        except tk.TclError:
            return
        self.on_change()

    def select(self, tab=None):
        if tab is None:
            return super().select()
        previous = self._selected
        result = super().select(tab)
        if previous is not None and previous is not self._selected:
            if previous.lock_mode == "reset" and previous.locked_path is not None:
                previous.navigate(previous.locked_path, bypass_lock=True)
        return result

    def current(self) -> FilePane:
        return self.nametowidget(self.select())

    def close_current(self) -> None:
        if len(self.tabs()) > 1:
            self.forget(self.select())
            self.on_change()

    def panes(self) -> list[FilePane]:
        return [self.nametowidget(tab) for tab in self.tabs()]

    def _color_changed(self, pane, color) -> None:
        self.on_change()

    def _lock_changed(self, pane, mode) -> None:
        pane.lock_mode = mode
        pane.locked_path = None if mode == "unlocked" else pane.path
        self.on_change()

    def _tabs_reordered(self) -> None:
        self.on_change()


class ConflictDialog(tk.Toplevel):
    def __init__(self, parent, source: Path, target: Path) -> None:
        super().__init__(parent)
        self.result = ("cancel", False)
        self.apply_all = tk.BooleanVar(value=False)
        self.title(tr("File conflict")); self.resizable(False, False); self.transient(parent)
        body = ttk.Frame(self, padding=12); body.pack(fill="both", expand=True)
        ttk.Label(body, text=tr("An item with the same name already exists."),
                  font=tkfont.nametofont("TkHeadingFont")).pack(anchor="w", pady=(0, 8))
        ttk.Label(body, text=f"{tr('Source')}: {source}\n{tr('Destination')}: {target}", justify="left",
                  wraplength=720).pack(anchor="w")
        ttk.Checkbutton(body, text=tr("Apply this choice to all remaining conflicts"),
                        variable=self.apply_all).pack(anchor="w", pady=(12, 8))
        buttons = ttk.Frame(body); buttons.pack(fill="x")
        first_button = None
        for text, action in (("Replace existing", "replace"), ("Skip", "skip"),
                             ("Keep both", "keep_both"), ("Cancel", "cancel")):
            button = ttk.Button(buttons, text=tr(text), command=lambda value=action: self.choose(value))
            button.pack(side="left", padx=3)
            if first_button is None: first_button = button
        self.bind("<Escape>", lambda _event: self.choose("cancel"))
        self.protocol("WM_DELETE_WINDOW", lambda: self.choose("cancel"))
        self.update_idletasks()
        self.geometry(f"+{parent.winfo_rootx() + 60}+{parent.winfo_rooty() + 80}")
        self.grab_set(); self.lift(); self.focus_force()
        if first_button is not None: first_button.focus_set()

    def choose(self, action: str) -> None:
        self.result = (action, self.apply_all.get() if action != "cancel" else False)
        self.destroy()

    @classmethod
    def ask(cls, parent, source: Path, target: Path) -> tuple[str, bool]:
        dialog = cls(parent, source, target)
        parent.wait_window(dialog)
        return dialog.result


class Commander(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self._ready = False
        self.ini_path = self._find_ini_path()
        self.config_data = configparser.ConfigParser()
        self.config_data.read(self.ini_path, encoding="utf-8")
        ensure_config_defaults(self.config_data)
        saved_language = self.config_data.get("view", "ui_language", fallback="en")
        set_language(saved_language)
        try:
            self._tab_colors = json.loads(self.config_data.get("tab_colors", "colors", fallback="{}"))
        except (json.JSONDecodeError, TypeError):
            self._tab_colors = {}
        self.title("Python File Commander")
        self.geometry(self.config_data.get("window", "geometry", fallback="1200x720"))
        self.minsize(800, 480)
        self.active: FilePane | None = None
        self.compare_window = None
        self.preview_window = None
        self.search_window = None
        self.multi_rename_window = None
        self._rename_undo = []
        self._drag_state = None
        self._drag_ghost = None
        self._drag_highlight = None
        saved_panel_count = self.config_data.getint("view", "panel_count", fallback=2)
        self.panel_count_var = tk.IntVar(value=max(2, min(4, saved_panel_count)))
        self.ui_language_var = tk.StringVar(value=saved_language if saved_language in dict(LANGUAGES) else "en")
        self._clipboard_visual_key = None
        self._clipboard_icon_images = []
        self._clipboard_icon_size = 18
        self.clipboard_icons = ShellIconProvider(self._clipboard_icon_size)
        self.font_size_var = tk.StringVar(value=self.config_data.get("view", "font_size", fallback="small"))
        saved_tab_style = self.config_data.get("view", "tab_style", fallback="right_skirt")
        if saved_tab_style == "compact":
            saved_tab_style = "right_skirt"
        elif saved_tab_style not in TAB_STYLES:
            saved_tab_style = "right_skirt"
        self.tab_style_var = tk.StringVar(value=saved_tab_style)
        self.recycle_bin_var = tk.BooleanVar(
            value=self.config_data.getboolean("operations", "send_delete_to_recycle_bin", fallback=True))
        self.continue_errors_var = tk.BooleanVar(
            value=self.config_data.getboolean("operations", "continue_after_error", fallback=True))
        self.favorites = self._load_navigation_paths("favorites")
        self.recent_folders = self._load_navigation_paths("recent_folders")
        self._font_scales = {"small": 1.0, "medium": 1.5, "large": 2.0, "huge": 3.0}
        self._base_font_sizes = {}
        for name in ("TkDefaultFont", "TkTextFont", "TkFixedFont", "TkMenuFont", "TkHeadingFont",
                     "TkCaptionFont", "TkSmallCaptionFont"):
            try:
                self._base_font_sizes[name] = tkfont.nametofont(name).cget("size")
            except tk.TclError:
                pass
        style = ttk.Style(self)
        style.configure("Active.Treeview", background="white", fieldbackground="white", indent=6)
        style.map("Active.Treeview", background=[("selected", "#1683e2")], foreground=[("selected", "white")])
        style.configure("Inactive.Treeview", background="white", fieldbackground="white", indent=6)
        style.map("Inactive.Treeview", background=[("selected", "#91a9bd")], foreground=[("selected", "white")])
        style.configure("PFC.TNotebook", background="#9eafbd", borderwidth=1)
        style.configure("PFC.TNotebook.Tab", background="#c7d3dd", foreground="#243442",
                        padding=(10, 5), borderwidth=1)
        style.map("PFC.TNotebook.Tab",
                  background=[("selected", "#1683e2"), ("active", "#dce7ef")],
                  foreground=[("selected", "#005a9e"), ("active", "#10202c")],
                  expand=[("selected", (1, 1, 1, 0))])
        flat_item_layout = [("Treeitem.padding", {"sticky": "nswe", "children": [
            ("Treeitem.image", {"side": "left", "sticky": ""}),
            ("Treeitem.text", {"side": "left", "sticky": ""}),
        ]})]
        style.layout("Active.Treeview.Item", flat_item_layout)
        style.layout("Inactive.Treeview.Item", flat_item_layout)
        self.apply_font_size(save=False)
        self._build_menu()
        split = ttk.Panedwindow(self, orient="horizontal")
        split.pack(fill="both", expand=True, padx=5, pady=5)
        self.split = split
        self.panel_tabs = []
        for section in PANEL_SECTIONS:
            tabs = PaneTabs(split, self.set_active, self.save_config, self._saved_paths(section),
                            self.get_tab_color, self.set_tab_color, self._handle_internal_drag,
                            self._show_file_context_menu, self.tab_style_var.get())
            self.panel_tabs.append(tabs)
        self.left_tabs, self.right_tabs = self.panel_tabs[:2]
        self.left = self.left_tabs.current()
        self.right = self.right_tabs.current()
        for tabs in self.visible_panel_tabs():
            split.add(tabs, weight=1)
        for section, tabs in zip(PANEL_SECTIONS, self.panel_tabs):
            self._restore_tab(tabs, section)
            self._restore_panel_options(tabs, section)
        active_section = self.config_data.get("state", "active_panel", fallback="left")
        active_index = PANEL_SECTIONS.index(active_section) if active_section in PANEL_SECTIONS else 0
        if active_index >= self.panel_count_var.get():
            active_index = 0
        self.active = self.panel_tabs[active_index].current()
        self.apply_font_size(save=False)
        self.apply_tab_style(save=False)
        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=5, pady=(0, 5))
        for text, command in ((f"F2 {tr('Rename')}", self.rename), (f"F3 {tr('Preview')}", self.preview),
                              (f"F4 {tr('Search')}", self.search), (f"F5 {tr('Copy')}", self.copy),
                              (f"F6 {tr('Move')}", self.move), (f"F7 {tr('New Folder')}", self.mkdir),
                              ("F8", None), (f"F9 {tr('Compare')}", self.compare_selected),
                              (f"F11 {tr('Copy Path')}", self.copy_paths), (f"F12 {tr('Change Dir')}", self.change_dir)):
            button = ttk.Button(actions, text=text, command=command)
            if command is None:
                button.state(["disabled"])
            button.pack(side="left", fill="x", expand=True, padx=1)
        install_button_tooltips(self)
        defaults = {
            "rename": "<F2>", "preview": "<F3>", "search": "<F4>", "copy": "<F5>",
            "move": "<F6>", "new_folder": "<F7>", "delete": "<Delete>", "refresh": "<Control-r>",
            "enter_folder": "<Right>", "parent_folder": "<Left>", "new_tab": "<Control-Up>",
            "close_tab": "<Control-w>", "select_all": "<Control-a>",
            "copy_path": "<Control-Shift-C>", "toggle_hidden": "<Control-h>",
            "clipboard_copy": "<Control-c>", "clipboard_cut": "<Control-x>",
            "clipboard_paste": "<Control-v>",
            "next_tab": "<Control-Tab>", "previous_tab": "<Control-Shift-Tab>",
            "switch_panel": "<Tab>", "focus_path": "<Control-l>",
            "focus_files": "<Escape>", "help": "<F1>",
            "select_previous": "<Up>", "select_next": "<Down>",
            "files_menu": "<Alt-f>", "view_menu": "<Alt-v>", "versions_menu": "<Alt-h>",
            "copy_paths": "<F11>", "change_dir": "<F12>",
            "compare": "<F9>",
            "permanent_delete": "<Shift-Delete>", "toggle_favorite": "<Control-d>",
            "favorites_menu": "<Control-b>", "recent_menu": "<Control-Shift-R>",
            "quick_filter": "<Control-y>", "multi_rename": "<Control-m>",
        }
        commands = {
            "rename": self.rename, "preview": self.preview, "search": self.search, "copy": self.copy,
            "move": self.move, "new_folder": self.mkdir, "delete": self.delete_hotkey, "refresh": self.refresh,
            "enter_folder": self.enter_folder, "parent_folder": self.parent_folder, "new_tab": self.new_tab,
            "close_tab": self.close_tab, "select_all": self.select_all,
            "copy_path": self.copy_path, "toggle_hidden": self.toggle_hidden,
            "clipboard_copy": self.clipboard_copy, "clipboard_cut": self.clipboard_cut,
            "clipboard_paste": self.clipboard_paste,
            "next_tab": lambda: self.switch_tab(1),
            "previous_tab": lambda: self.switch_tab(-1),
            "switch_panel": self.switch_panel, "focus_path": self.focus_path,
            "focus_files": self.focus_files, "help": self.show_help,
            "select_previous": lambda: self.move_selection(-1),
            "select_next": lambda: self.move_selection(1),
            "files_menu": lambda: self.show_header_menu("files"),
            "view_menu": lambda: self.show_header_menu("view"),
            "versions_menu": lambda: self.show_header_menu("versions"),
            "copy_paths": self.copy_paths, "change_dir": self.change_dir,
            "compare": self.compare_selected,
            "permanent_delete": lambda: self.delete_hotkey(permanent=True),
            "toggle_favorite": self.toggle_favorite,
            "favorites_menu": lambda: self._show_folder_menu(self.favorites_menu, self._rebuild_favorites_menu),
            "recent_menu": lambda: self._show_folder_menu(self.recent_menu, self._rebuild_recent_menu),
            "quick_filter": lambda: self.panes()[0].toggle_quick_filter(),
            "multi_rename": self.multi_rename,
        }
        if not self.config_data.has_section("hotkeys"):
            self.config_data.add_section("hotkeys")
        configured_hotkeys = {}
        for name, default in defaults.items():
            key = self.config_data.get("hotkeys", name, fallback=default)
            self.config_data.set("hotkeys", name, key)
            configured_hotkeys[name] = key
            if name not in {"select_previous", "select_next", "permanent_delete"}:
                self.bind_all(key, lambda _e, fn=commands[name]: fn())
        self._install_priority_hotkeys(configured_hotkeys, commands)
        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self._ready = True
        self._save_job = None
        self._auto_refresh_job = None
        self._clipboard_job = None
        self.bind("<Configure>", self._schedule_save)
        self.set_active(self.active)
        self.save_config()
        self._schedule_auto_refresh(250)
        self._schedule_clipboard_summary(250)

    def _install_priority_hotkeys(self, hotkeys, commands) -> None:
        """Run tab navigation before Tk widget/class bindings can consume Tab."""
        tag = f"PFCKeyboard{id(self)}"
        for name in ("switch_panel", "next_tab", "previous_tab", "enter_folder", "parent_folder"):
            self.bind_class(tag, hotkeys[name], lambda _event, fn=commands[name]: fn())
        self.bind_class(tag, hotkeys["select_previous"],
                        lambda event: None if event.state & 0x5 else self.move_selection(-1))
        self.bind_class(tag, hotkeys["select_next"],
                        lambda event: None if event.state & 0x5 else self.move_selection(1))
        self.bind_class(tag, hotkeys["permanent_delete"],
                        lambda _event: (commands["permanent_delete"](), "break")[1])

        def prepend(widget):
            tags = widget.bindtags()
            if tag not in tags:
                widget.bindtags((tag, *tags))
            for child in widget.winfo_children():
                prepend(child)

        prepend(self)

    @staticmethod
    def _find_ini_path() -> Path:
        executable = Path(sys.argv[0]).resolve()
        if executable.name.casefold() == "pfc.py":
            return executable.with_name("pfc.ini")
        return Path(__file__).resolve().parents[1] / "pfc.ini"

    def _load_navigation_paths(self, key: str) -> list[Path]:
        try:
            values = json.loads(self.config_data.get("navigation", key, fallback="[]"))
            return [Path(value) for value in values if isinstance(value, str)]
        except (json.JSONDecodeError, TypeError):
            return []

    @staticmethod
    def _deduplicate_paths(paths: list[Path], limit: int | None = None) -> list[Path]:
        result, seen = [], set()
        for path in paths:
            key = os.path.normcase(str(path))
            if key not in seen:
                seen.add(key); result.append(path)
            if limit is not None and len(result) >= limit:
                break
        return result

    def _record_recent(self, path: Path) -> None:
        self.recent_folders = self._deduplicate_paths([path, *self.recent_folders], 20)

    def _saved_paths(self, side: str) -> list[Path]:
        try:
            paths = json.loads(self.config_data.get(side, "tabs", fallback="[]"))
        except (json.JSONDecodeError, TypeError):
            paths = []
        candidates = [Path(value).expanduser() for value in paths]
        valid = [path for path in candidates if path.is_dir()]
        return valid or [Path.home()]

    def _restore_tab(self, tabs: PaneTabs, side: str) -> None:
        index = self.config_data.getint(side, "selected", fallback=0)
        if tabs.tabs():
            tabs.select(tabs.tabs()[min(max(index, 0), len(tabs.tabs()) - 1)])

    def _restore_panel_options(self, tabs: PaneTabs, side: str) -> None:
        column = self.config_data.get(side, "sort_column", fallback="name")
        descending = self.config_data.getboolean(side, "sort_descending", fallback=False)
        show_hidden = self.config_data.getboolean(side, "show_hidden", fallback=False)
        show_system = self.config_data.getboolean(side, "show_system", fallback=False)
        show_extensions = self.config_data.getboolean(side, "show_extensions", fallback=True)
        try:
            colors = json.loads(self.config_data.get(side, "tab_colors", fallback="[]"))
            locks = json.loads(self.config_data.get(side, "tab_locks", fallback="[]"))
            locked_paths = json.loads(self.config_data.get(side, "locked_paths", fallback="[]"))
            filters = json.loads(self.config_data.get(side, "tab_filters", fallback="[]"))
        except (json.JSONDecodeError, TypeError):
            colors, locks, locked_paths, filters = [], [], [], []
        for index, pane in enumerate(tabs.panes()):
            pane.sort_column = column if column in pane.all_sort_columns else "name"
            pane.reverse = descending
            pane.show_hidden = show_hidden
            pane.show_system = show_system
            pane.show_extensions = show_extensions
            pane.set_quick_filter(filters[index] if index < len(filters) else "")
            color = colors[index] if index < len(colors) else self.get_tab_color(pane.path)
            tabs.set_color(pane, color, notify=False)
            mode = locks[index] if index < len(locks) else "unlocked"
            pane.lock_mode = mode if mode in {"unlocked", "locked", "reset"} else "unlocked"
            locked = Path(locked_paths[index]) if index < len(locked_paths) else pane.path
            pane.locked_path = locked if pane.lock_mode != "unlocked" and locked.is_dir() else None
            tabs.set_lock(pane, pane.lock_mode, notify=False)
            for col in pane.all_sort_columns:
                marker = (" ▼" if descending else " ▲") if col == pane.sort_column else ""
                pane.tree.heading("#0" if col == "name" else col, text=pane.heading_labels[col] + marker)
            pane.refresh()

    def _schedule_save(self, _event=None) -> None:
        if not self._ready:
            return
        if self._save_job is not None:
            self.after_cancel(self._save_job)
        self._save_job = self.after(250, self.save_config)

    def save_config(self, record_recent: bool = True) -> None:
        if not self._ready:
            return
        ensure_config_defaults(self.config_data)
        if record_recent and self.active is not None:
            self._record_recent(self.active.path)
        for side, tabs in zip(PANEL_SECTIONS, self.panel_tabs):
            if not self.config_data.has_section(side):
                self.config_data.add_section(side)
            panes = tabs.panes()
            saved_paths = [p.locked_path if p.lock_mode == "reset" and p.locked_path else p.path for p in panes]
            self.config_data.set(side, "tabs", json.dumps([str(path) for path in saved_paths]))
            self.config_data.set(side, "tab_colors", json.dumps([
                tabs._colors.get(p, "default") for p in panes]))
            self.config_data.set(side, "tab_locks", json.dumps([p.lock_mode for p in panes]))
            self.config_data.set(side, "locked_paths", json.dumps([
                str(p.locked_path or p.path) for p in panes]))
            self.config_data.set(side, "tab_filters", json.dumps([
                p.quick_filter_var.get() for p in panes], ensure_ascii=False))
            self.config_data.set(side, "selected", str(tabs.index(tabs.select())))
            current = tabs.current()
            self.config_data.set(side, "sort_column", current.sort_column)
            self.config_data.set(side, "sort_descending", str(current.reverse).lower())
            self.config_data.set(side, "show_hidden", str(current.show_hidden).lower())
            self.config_data.set(side, "show_system", str(current.show_system).lower())
            self.config_data.set(side, "show_extensions", str(current.show_extensions).lower())
        if not self.config_data.has_section("window"):
            self.config_data.add_section("window")
        if not self.config_data.has_section("state"):
            self.config_data.add_section("state")
        if not self.config_data.has_section("view"):
            self.config_data.add_section("view")
        if not self.config_data.has_section("refresh"):
            self.config_data.add_section("refresh")
        if not self.config_data.has_section("tab_colors"):
            self.config_data.add_section("tab_colors")
        self.config_data.set("window", "geometry", self.geometry())
        active_tabs = self._tabs_for(self.active) if self.active is not None else self.panel_tabs[0]
        self.config_data.set("state", "active_panel", PANEL_SECTIONS[self.panel_tabs.index(active_tabs)])
        self.config_data.set("view", "font_size", self.font_size_var.get())
        self.config_data.set("view", "tab_style", self.tab_style_var.get())
        self.config_data.set("view", "panel_count", str(self.panel_count_var.get()))
        self.config_data.set("view", "ui_language", self.ui_language_var.get())
        self.config_data.set("tab_colors", "colors", json.dumps(self._tab_colors, ensure_ascii=False))
        self.config_data.set("operations", "send_delete_to_recycle_bin", str(self.recycle_bin_var.get()).lower())
        self.config_data.set("operations", "continue_after_error", str(self.continue_errors_var.get()).lower())
        self.config_data.set("navigation", "favorites", json.dumps([str(path) for path in self.favorites], ensure_ascii=False))
        self.config_data.set("navigation", "recent_folders", json.dumps([str(path) for path in self.recent_folders], ensure_ascii=False))
        try:
            write_config_atomic(self.config_data, self.ini_path)
        except OSError:
            pass

    def close_app(self) -> None:
        if self._drag_state is not None:
            self._handle_internal_drag("cancel", self._drag_state["source"], None)
        if self._auto_refresh_job is not None:
            self.after_cancel(self._auto_refresh_job)
        if self._clipboard_job is not None:
            self.after_cancel(self._clipboard_job)
        self.save_config()
        self.destroy()

    def _schedule_auto_refresh(self, delay=None) -> None:
        if not self.winfo_exists():
            return
        if delay is None:
            focused = self.focus_displayof() is not None
            paths = tuple(pane.path for pane in self.visible_panes())
            network = any(str(path).startswith("\\\\") for path in paths)
            key = "network_interval_ms" if network else ("active_interval_ms" if focused else "background_interval_ms")
            delay = self.config_data.getint("refresh", key, fallback=5000)
        self._auto_refresh_job = self.after(max(500, delay), self._auto_refresh_tick)

    def _auto_refresh_tick(self) -> None:
        self._auto_refresh_job = None
        if self.config_data.getboolean("refresh", "auto_refresh", fallback=True):
            for pane in self.visible_panes():
                pane.refresh_if_changed()
        self._schedule_auto_refresh()

    def _build_menu(self) -> None:
        menu_font = tkfont.nametofont("TkMenuFont")
        header_bg, header_fg, active_bg = "#243b53", "#f4f8fb", "#365b78"
        header = tk.Frame(self, background=header_bg, padx=5, pady=4)
        header.pack(fill="x")
        title = tk.Label(header, text=f"Python File Commander   v{__version__}   {tr('Build')} {BUILD_DATE}",
                         font=tkfont.nametofont("TkCaptionFont"),
                         background=header_bg, foreground=header_fg, cursor="hand2")
        title.pack(side="left", padx=(2, 10))
        title.bind("<Button-1>", lambda _event: self.show_help())
        button_style = dict(font=menu_font, relief="flat", borderwidth=0, padx=7,
                            background=header_bg, foreground=header_fg,
                            activebackground=active_bg, activeforeground="#ffffff")
        files_button = tk.Menubutton(header, text=tr("Files"), **button_style)
        files_button.pack(side="left")
        files = tk.Menu(files_button, tearoff=False, font=menu_font)
        files_button.configure(menu=files)
        files.add_command(label=tr("Copy to Clipboard"), accelerator="Ctrl+C", command=self.clipboard_copy)
        files.add_command(label=tr("Cut to Clipboard"), accelerator="Ctrl+X", command=self.clipboard_cut)
        files.add_command(label=tr("Paste"), accelerator="Ctrl+V", command=self.clipboard_paste)
        files.add_separator()
        files.add_command(label=tr("Copy to Next Panel"), accelerator="F5", command=self.copy)
        files.add_command(label=tr("Move to Next Panel"), accelerator="F6", command=self.move)
        files.add_command(label=tr("Rename"), accelerator="F2", command=self.rename)
        files.add_command(label=tr("Multi-Rename"), accelerator="Ctrl+M", command=self.multi_rename)
        files.add_command(label=tr("New Folder"), accelerator="F7", command=self.mkdir)
        files.add_separator()
        files.add_command(label=tr("Delete"), accelerator="Del", command=self.delete)
        files.add_command(label=tr("Permanent Delete"), accelerator="Shift+Del", command=lambda: self.delete(permanent=True))
        files.add_checkbutton(label=tr("Send Delete to Recycle Bin"), variable=self.recycle_bin_var,
                              command=self.save_config)
        files.add_checkbutton(label=tr("Continue After File Errors"), variable=self.continue_errors_var,
                              command=self.save_config)
        files.add_separator()
        self.favorites_menu = tk.Menu(files, tearoff=False, font=menu_font,
                                      postcommand=self._rebuild_favorites_menu)
        self.recent_menu = tk.Menu(files, tearoff=False, font=menu_font,
                                   postcommand=self._rebuild_recent_menu)
        files.add_cascade(label=tr("Favorites"), menu=self.favorites_menu)
        files.add_cascade(label=tr("Recent Folders"), menu=self.recent_menu)
        files.add_separator()
        files.add_command(label=tr("Preview"), accelerator="F3", command=self.preview)
        files.add_command(label=tr("Search"), accelerator="F4", command=self.search)
        files.add_command(label=tr("Compare"), accelerator="F9", command=self.compare_selected)
        files.add_command(label=tr("Copy Path"), accelerator="F11", command=self.copy_paths)
        files.add_command(label=tr("Change Dir"), accelerator="F12", command=self.change_dir)
        files.add_separator()
        files.add_command(label=tr("Exit"), command=self.close_app)
        view_button = tk.Menubutton(header, text=tr("View"), **button_style)
        view_button.pack(side="left")
        view = tk.Menu(view_button, tearoff=False, font=menu_font)
        view_button.configure(menu=view)
        visibility = tk.Menu(view, tearoff=False, font=menu_font)
        self.show_hidden_var = tk.BooleanVar(value=False)
        self.show_system_var = tk.BooleanVar(value=False)
        self.show_extensions_var = tk.BooleanVar(value=True)
        visibility.add_checkbutton(label=tr("Show Hidden"), variable=self.show_hidden_var,
                                   command=self.set_hidden_visibility)
        visibility.add_checkbutton(label=tr("Show System"), variable=self.show_system_var,
                                   command=self.set_system_visibility)
        visibility.add_checkbutton(label=tr("Show File Extension"), variable=self.show_extensions_var,
                                   command=self.set_extension_visibility)
        view.add_cascade(label=tr("File Visibility"), menu=visibility)
        font_size = tk.Menu(view, tearoff=False, font=menu_font)
        for label, value in (("Small (100%)", "small"), ("Medium (150%)", "medium"),
                             ("Large (200%)", "large"), ("Huge (300%)", "huge")):
            font_size.add_radiobutton(label=tr(label), value=value, variable=self.font_size_var,
                                      command=self.apply_font_size)
        view.add_cascade(label=tr("Font Size"), menu=font_size)
        tab_style = tk.Menu(view, tearoff=False, font=menu_font)
        for value, label in TAB_STYLES.items():
            tab_style.add_radiobutton(label=tr(label), value=value, variable=self.tab_style_var,
                                      command=self.apply_tab_style)
        view.add_cascade(label=tr("Tab Style"), menu=tab_style)
        panel_counts = tk.Menu(view, tearoff=False, font=menu_font)
        for count in range(2, 5):
            panel_counts.add_radiobutton(label=tr("{count} Panels", count=count), value=count,
                                         variable=self.panel_count_var,
                                         command=self.apply_panel_count)
        view.add_cascade(label=tr("Panel Counts"), menu=panel_counts)
        language_menu = tk.Menu(view, tearoff=False, font=menu_font)
        for code, native_label in LANGUAGES:
            language_menu.add_radiobutton(label=native_label, value=code,
                                          variable=self.ui_language_var,
                                          command=self.apply_ui_language)
        view.add_cascade(label=tr("UI Language"), menu=language_menu)
        view.add_command(label=tr("Quick Filter"), accelerator="Ctrl+Y",
                         command=lambda: self.panes()[0].toggle_quick_filter())
        versions_button = tk.Menubutton(header, text=tr("Versions"), **button_style)
        versions_button.pack(side="left")
        versions = tk.Menu(versions_button, tearoff=False, font=menu_font)
        versions_button.configure(menu=versions)
        versions.add_command(label=tr("Current version: v{version}", version=__version__), state="disabled")
        versions.add_separator()
        version_series = []
        for version, build_date, notes in VERSION_HISTORY:
            series = version.rsplit(".", 1)[0] + ".x"
            if series not in version_series:
                version_series.append(series)
                versions.add_command(label=tr("{series} Changes", series=series),
                                     command=lambda value=series: self.show_version_series(value))
        versions.add_separator()
        versions.add_command(label=tr("Yoda — Portable App Advocate"),
                             command=self.show_yoda_note)
        self.clipboard_summary_frame = tk.Frame(header, background=header_bg)
        self.clipboard_summary_frame.pack(side="right", padx=(12, 4))
        self.clipboard_icon_canvas = tk.Canvas(self.clipboard_summary_frame, width=52, height=24,
                                               highlightthickness=0, background=header_bg)
        self.clipboard_icon_canvas.pack(side="left")
        self.clipboard_summary = tk.Label(self.clipboard_summary_frame, text=tr("Clipboard: checking…"),
                                          anchor="e", width=1,
                                          font=tkfont.nametofont("TkDefaultFont"),
                                          background=header_bg, foreground="#c9e5f5")
        self.clipboard_summary.pack(side="right")
        self.files_menu_button = files_button
        self.view_menu_button = view_button
        self.versions_menu_button = versions_button
        self.files_menu = files
        self.view_menu = view
        self.panel_counts_menu = panel_counts
        self.language_menu = language_menu
        self.versions_menu = versions
        self.version_series = tuple(version_series)
        menu_help = {
            "Copy to Clipboard": "Copy selected items for PFC or File Explorer.",
            "Cut to Clipboard": "Cut selected items for PFC or File Explorer.",
            "Paste": "Paste clipboard items into the active folder.",
            "Copy to Next Panel": "Copy selected items to the next visible panel.",
            "Move to Next Panel": "Move selected items to the next visible panel.",
            "Rename": "Rename the selected item.", "Preview": "Open PFC Preview.",
            "Multi-Rename": "Preview and rename multiple selected items; Ctrl+Z undoes the last batch.",
            "New Folder": "Create a folder in the active panel.",
            "Delete": "Delete using the selected Recycle Bin policy.",
            "Permanent Delete": "Permanently delete after a warning.",
            "Send Delete to Recycle Bin": "When enabled, Del sends items to the Windows Recycle Bin.",
            "Continue After File Errors": "Continue remaining items, then show exact failures and retry options.",
            "Favorites": "Open or maintain favorite folders.", "Recent Folders": "Open recently visited folders.",
            "Search": "Search below the current folder.", "Compare": "Compare selected items.",
            "Copy Path": "Copy all selected full paths.",
            "Change Dir": "Focus the path bar for direct paste.", "Exit": "Save settings and close PFC.",
            "Show Hidden": "Show or hide dot-prefixed files.", "Show System": "Show or hide Windows system files.",
            "Show File Extension": "Show or hide the final extension in Name; Ext remains visible.",
            "File Visibility": "Choose which file names and attributes are visible.",
            "Font Size": "Scale PFC fonts, controls, tabs and icons.",
            "Tab Style": "Choose the shape used by main and Compare tabs.",
            "Panel Counts": "Show two, three, or four file panels; F5/F6 target the next panel.",
            "Quick Filter": "Filter the active file list as you type; Esc clears it.",
        }
        menu_help = {tr(label): tr(help_text) for label, help_text in menu_help.items()}
        self._files_menu_tooltip = MenuToolTip(files, menu_help)
        self._view_menu_tooltip = MenuToolTip(view, menu_help)
        self._versions_menu_tooltip = MenuToolTip(
            versions, {**{tr("{series} Changes", series=series): f"Show every {series} release in one window."
                         for series in version_series},
                       tr("Yoda — Portable App Advocate"): "About the advocate who helped bring this portable app into being."})
        self._visibility_menu_tooltip = MenuToolTip(visibility, menu_help)
        self._font_menu_tooltip = MenuToolTip(font_size, menu_help)
        self._tab_style_menu_tooltip = MenuToolTip(tab_style, {
            tr("Right Skirt"): "Full-height tab with a vertical left edge and steep bottom-right skirt.",
            tr("Rounded"): "Rounded top corners with straight sides and a square bottom.",
            tr("Squarish"): "Straight rectangular edges with no slant or skirt.",
        })
        self._panel_count_tooltip = MenuToolTip(panel_counts, menu_help)
        self.config(menu="")

    def _schedule_clipboard_summary(self, delay=2000) -> None:
        self._clipboard_job = self.after(delay, self._update_clipboard_summary)

    def _update_clipboard_summary(self) -> None:
        self._clipboard_job = None
        try:
            paths, cut = get_file_clipboard()
            if paths:
                noun = self._clipboard_more_noun(paths[1:])
                suffix = (" " + tr("and {count} more {kind}", count=len(paths) - 1, kind=tr(noun))
                          if len(paths) > 1 else "")
                prefix = tr("Clipboard (Cut)") if cut else tr("Clipboard")
                first_name = self._short_clipboard_name(paths[0].name)
                self._set_clipboard_visual(f"{prefix}: {first_name}{suffix}", paths, "paths")
            else:
                virtual_files = get_virtual_file_descriptors()
                if virtual_files:
                    first = self._short_clipboard_name(getattr(virtual_files[0], "name", "Attachment"))
                    suffix = (" " + tr("and {count} more {kind}", count=len(virtual_files) - 1,
                                       kind=tr("attachments"))
                              if len(virtual_files) > 1 else "")
                    self._set_clipboard_visual(f"{tr('Clipboard')}: {first}{suffix}", (), "attachments",
                                               len(virtual_files))
                else:
                    try:
                        value = self.clipboard_get()
                        size = len(value.encode("utf-8"))
                        text = (tr("Clipboard: String {size} Bytes", size=f"{size:,}")
                                if value else tr("Clipboard: Empty"))
                        self._set_clipboard_visual(text, (), "text" if value else "empty")
                    except tk.TclError:
                        self._set_clipboard_visual(tr("Clipboard: OBJ"), (), "object")
        except (OSError, MemoryError):
            pass  # Keep the last useful summary while another app owns the clipboard.
        if self.winfo_exists():
            self._schedule_clipboard_summary()

    @staticmethod
    def _clipboard_more_noun(paths: list[Path]) -> str:
        if not paths:
            return "items"
        folders = sum(path.is_dir() for path in paths)
        if folders == len(paths):
            return "folder" if len(paths) == 1 else "folders"
        if folders == 0:
            return "file" if len(paths) == 1 else "files"
        return "item" if len(paths) == 1 else "items"

    @staticmethod
    def _short_clipboard_name(name: str, limit: int = 34) -> str:
        return name if len(name) <= limit else name[:limit - 1] + "…"

    def _set_clipboard_visual(self, label: str, paths=(), kind: str = "object", count: int = 1) -> None:
        normalized_paths = tuple(str(path) for path in paths[:3])
        key = (label, normalized_paths, kind, count, self._clipboard_icon_size)
        if key == self._clipboard_visual_key:
            return
        self._clipboard_visual_key = key
        canvas = self.clipboard_icon_canvas
        canvas.delete("all")
        self._clipboard_icon_images = []
        height = max(24, self._clipboard_icon_size + 6)
        width = max(42, self._clipboard_icon_size + 25)
        canvas.configure(width=width, height=height)
        center_y = height // 2
        if paths:
            for index, path in enumerate(paths[:3]):
                image = self.clipboard_icons.get(path, path.is_dir())
                canvas.create_image(2 + index * 10, center_y, anchor="w", image=image)
                self._clipboard_icon_images.append(image)
        else:
            visible = min(3, max(1, count)) if kind == "attachments" else 1
            for index in range(visible - 1, -1, -1):
                x = 3 + index * 7
                if kind == "text":
                    canvas.create_rectangle(x, center_y - 8, x + 14, center_y + 8,
                                            fill="#ffffff", outline="#9fb3c8")
                    canvas.create_text(x + 7, center_y, text="T", fill="#243b53",
                                       font=tkfont.nametofont("TkSmallCaptionFont"))
                elif kind == "empty":
                    canvas.create_rectangle(x, center_y - 7, x + 14, center_y + 7,
                                            outline="#9fb3c8")
                else:
                    canvas.create_rectangle(x, center_y - 8, x + 14, center_y + 8,
                                            fill="#e9f2f8", outline="#9fb3c8")
                    canvas.create_line(x + 4, center_y - 3, x + 11, center_y - 3,
                                       x + 11, center_y + 3, x + 4, center_y + 3,
                                       fill="#486581")
        self.clipboard_summary.configure(text=label)

    def set_active(self, pane: FilePane) -> None:
        self.active = pane
        self.show_hidden_var.set(pane.show_hidden)
        self.show_system_var.set(pane.show_system)
        self.show_extensions_var.set(pane.show_extensions)
        if hasattr(self, "panel_tabs"):
            for candidate in self.all_panes():
                candidate.set_active_appearance(candidate is pane)
        self.save_config()

    def get_tab_color(self, path: Path) -> str:
        return self._tab_colors.get(str(path), "default")

    def set_tab_color(self, path: Path, color: str) -> None:
        key = str(path)
        if color == "default":
            self._tab_colors.pop(key, None)
        else:
            self._tab_colors[key] = color
        self.save_config()

    def visible_panel_tabs(self) -> list[PaneTabs]:
        if not hasattr(self, "panel_tabs"):
            return []
        return self.panel_tabs[:max(2, min(4, self.panel_count_var.get()))]

    def apply_panel_count(self, save: bool = True) -> None:
        count = max(2, min(4, int(self.panel_count_var.get())))
        self.panel_count_var.set(count)
        if not hasattr(self, "split"):
            return
        present = set(self.split.panes())
        for index, tabs in enumerate(self.panel_tabs):
            pane_id = str(tabs)
            if index < count and pane_id not in present:
                self.split.add(tabs, weight=1)
            elif index >= count and pane_id in present:
                self.split.forget(tabs)
        if self.active is None or self._tabs_for(self.active) not in self.visible_panel_tabs():
            self.set_active(self.panel_tabs[0].current())
        else:
            self.set_active(self.active)
        self.update_idletasks()
        if save:
            self.save_config()

    def apply_ui_language(self) -> None:
        self.save_config()
        messagebox.showinfo(tr("Language saved"),
                            tr("Restart PFC to apply the selected UI language."), parent=self)

    def visible_panes(self) -> list[FilePane]:
        return [tabs.current() for tabs in self.visible_panel_tabs()]

    def all_panes(self) -> list[FilePane]:
        return [pane for tabs in self.panel_tabs for pane in tabs.panes()]

    def panes(self) -> tuple[FilePane, FilePane]:
        tabs_list = self.visible_panel_tabs()
        source = self.active or tabs_list[0].current()
        source_tabs = self._tabs_for(source)
        if source_tabs not in tabs_list:
            source_tabs = tabs_list[0]; source = source_tabs.current()
        index = tabs_list.index(source_tabs)
        return source, tabs_list[(index + 1) % len(tabs_list)].current()

    def _tabs_for(self, pane: FilePane) -> PaneTabs:
        for tabs in self.panel_tabs:
            if pane in tabs.panes():
                return tabs
        return self.left_tabs

    def _drop_target_at(self, x_root: int, y_root: int):
        for pane in self.visible_panes():
            tree = pane.tree
            if not tree.winfo_viewable():
                continue
            left, top = tree.winfo_rootx(), tree.winfo_rooty()
            if not (left <= x_root < left + tree.winfo_width() and
                    top <= y_root < top + tree.winfo_height()):
                continue
            iid = tree.identify_row(y_root - top)
            destination, folder_iid = pane.path, None
            if iid:
                tags = tree.item(iid, "tags")
                if tags:
                    candidate = Path(tags[0])
                    try:
                        if candidate.is_dir():
                            destination, folder_iid = candidate, iid
                    except OSError:
                        pass
            return pane, destination, folder_iid
        return None

    def _clear_drag_highlight(self) -> None:
        if self._drag_highlight is None:
            return
        pane, iid = self._drag_highlight
        try:
            tags = tuple(tag for tag in pane.tree.item(iid, "tags") if tag != "PFC_DROP_TARGET")
            pane.tree.item(iid, tags=tags)
        except tk.TclError:
            pass
        self._drag_highlight = None

    def _set_drag_highlight(self, pane: FilePane | None, iid: str | None) -> None:
        if self._drag_highlight == (pane, iid):
            return
        self._clear_drag_highlight()
        if pane is not None and iid:
            try:
                tags = tuple(pane.tree.item(iid, "tags"))
                pane.tree.item(iid, tags=(*tags, "PFC_DROP_TARGET"))
                self._drag_highlight = (pane, iid)
            except tk.TclError:
                pass

    def _create_drag_ghost(self) -> None:
        ghost = tk.Toplevel(self); ghost.overrideredirect(True)
        try: ghost.attributes("-topmost", True); ghost.attributes("-alpha", 0.92)
        except tk.TclError: pass
        label = tk.Label(ghost, justify="left", anchor="w", relief="solid", borderwidth=1,
                         padx=9, pady=6, wraplength=560,
                         font=tkfont.nametofont("TkDefaultFont"))
        label.pack()
        self._drag_ghost, self._drag_ghost_label = ghost, label

    def _update_internal_drag(self, event) -> None:
        if self._drag_state is None:
            return
        mode = "move" if event.state & 0x0001 else "copy"
        target = self._drop_target_at(event.x_root, event.y_root)
        self._drag_state["mode"], self._drag_state["target"] = mode, target
        self._set_drag_highlight(target[0], target[2]) if target else self._set_drag_highlight(None, None)
        count = len(self._drag_state["items"])
        item_text = (self._drag_state["items"][0].name if count == 1
                     else tr("{count} selected items", count=count))
        action = tr("Move") if mode == "move" else tr("Copy")
        destination = str(target[1]) if target else tr("Not a PFC drop target")
        color = "#ffd27a" if mode == "move" else ("#a9dcff" if target else "#e6e6e6")
        self._drag_ghost_label.configure(text=f"{action}: {item_text}\n→ {destination}",
                                         background=color, foreground="#10202c")
        self._drag_ghost.geometry(f"+{event.x_root + 16}+{event.y_root + 18}")

    def _finish_internal_drag(self) -> None:
        self._clear_drag_highlight()
        if self._drag_state is not None:
            try: self._drag_state["source"].tree.configure(cursor="")
            except tk.TclError: pass
        if self._drag_ghost is not None:
            try: self._drag_ghost.destroy()
            except tk.TclError: pass
        self._drag_ghost = None

    def _handle_internal_drag(self, action: str, pane: FilePane, event) -> None:
        if action == "external_drop":
            paths = [Path(path) for path in event["paths"] if Path(path).exists()]
            if not paths:
                return
            target = self._drop_target_at(event["x_root"], event["y_root"])
            target_pane, destination = (target[0], target[1]) if target else (pane, pane.path)
            move = bool(event["move"])
            self._execute_transfer("Explorer Drag Move" if move else "Explorer Drag Copy",
                                   move_items if move else copy_items,
                                   paths, destination, confirm=False)
            self.set_active(target_pane); target_pane.focus_file_list()
            return
        if action == "start":
            items = pane.selected_paths()
            if not items:
                return
            self._drag_state = {"source": pane, "items": items, "mode": "copy", "target": None}
            pane.tree.configure(cursor="fleur"); self._create_drag_ghost(); self._update_internal_drag(event)
            return
        if action == "motion":
            if (self._drag_state is not None and
                    not point_belongs_to_process(event.x_root, event.y_root)):
                state = self._drag_state
                self._finish_internal_drag(); self._drag_state = None
                try:
                    effect = start_shell_drag(pane.tree.winfo_id(), state["items"])
                    if effect in {DROPEFFECT_COPY, DROPEFFECT_MOVE}:
                        self.after(250, self.refresh)
                except OSError as exc:
                    messagebox.showerror(tr("Explorer drag failed"), str(exc), parent=self)
                return
            self._update_internal_drag(event); return
        if action == "cancel":
            self._finish_internal_drag(); self._drag_state = None; return
        if action != "drop" or self._drag_state is None:
            return
        self._update_internal_drag(event)
        state = self._drag_state
        target = state["target"]
        self._finish_internal_drag(); self._drag_state = None
        if target is None:
            return
        target_pane, destination, _iid = target
        move = state["mode"] == "move"
        self._execute_transfer("Drag Move" if move else "Drag Copy",
                               move_items if move else copy_items,
                               state["items"], destination, confirm=False)
        self.set_active(target_pane); target_pane.focus_file_list()

    def _build_file_context_menu(self, pane: FilePane, clicked: Path) -> tk.Menu:
        self.set_active(pane)
        items = pane.selected_paths()
        single = len(items) == 1
        clicked_folder = clicked.is_dir()
        source, target = self.panes()
        source_items = source.selected_paths()
        target_items = target.selected_paths()
        can_compare = ((len(source_items) == 1 and len(target_items) == 1) or
                       len(items) == 2)
        old_menu = getattr(self, "file_context_menu", None)
        if old_menu is not None:
            try: old_menu.destroy()
            except tk.TclError: pass
        menu = tk.Menu(self, tearoff=False, font=tkfont.nametofont("TkMenuFont"))
        self.file_context_menu = menu
        normal_if = lambda condition: "normal" if condition else "disabled"
        menu.add_command(label=tr("Open / Enter Folder"), accelerator="Enter",
                         state=normal_if(single), command=pane.open_selected)
        menu.add_command(label=tr("Open Folder in New Tab"), state=normal_if(single and clicked_folder),
                         command=lambda: self._open_folder_in_new_tab(pane, clicked))
        menu.add_command(label=tr("Preview"), accelerator="F3",
                         state=normal_if(single and clicked.is_file()), command=self.preview)
        menu.add_command(label=tr("Compare"), accelerator="F9",
                         state=normal_if(can_compare), command=self.compare_selected)
        menu.add_separator()
        menu.add_command(label=tr("Copy to Clipboard"), accelerator="Ctrl+C", command=self.clipboard_copy)
        menu.add_command(label=tr("Cut to Clipboard"), accelerator="Ctrl+X", command=self.clipboard_cut)
        paste_destination = clicked if clicked_folder else pane.path
        paste_label = tr("Paste into This Folder") if clicked_folder else tr("Paste into Current Folder")
        menu.add_command(label=paste_label, accelerator="Ctrl+V",
                         command=lambda target=paste_destination: self._clipboard_paste_to(target))
        menu.add_separator()
        menu.add_command(label=tr("Copy to Next Panel"), accelerator="F5", command=self.copy)
        menu.add_command(label=tr("Move to Next Panel"), accelerator="F6", command=self.move)
        menu.add_separator()
        menu.add_command(label=tr("Rename"), accelerator="F2",
                         state=normal_if(single), command=self.rename)
        menu.add_command(label=tr("Multi-Rename"), accelerator="Ctrl+M",
                         state=normal_if(len(items) > 1), command=self.multi_rename)
        menu.add_command(label=tr("Copy Path"), accelerator="F11", command=self.copy_paths)
        menu.add_separator()
        menu.add_command(label=tr("Delete"), accelerator="Del", command=self.delete_hotkey)
        menu.add_command(label=tr("Permanent Delete"), accelerator="Shift+Del",
                         command=lambda: self.delete_hotkey(permanent=True))
        descriptions = {
            "Open / Enter Folder": "Open the selected file or enter the selected folder.",
            "Open Folder in New Tab": "Open this folder in a new tab beside the current tab.",
            "Preview": "Open the selected file in PFC Preview.",
            "Compare": "Compare the active and next panel, or two selected items.",
            "Copy to Clipboard": "Copy selected items for PFC or File Explorer.",
            "Cut to Clipboard": "Cut selected items for PFC or File Explorer.",
            "Paste into This Folder": "Paste clipboard items directly into the clicked folder.",
            "Paste into Current Folder": "Paste clipboard items into the current panel folder.",
            "Copy to Next Panel": "Copy selected items to the next visible panel.",
            "Move to Next Panel": "Move selected items to the next visible panel.",
            "Rename": "Rename the selected item.",
            "Multi-Rename": "Preview and rename all selected items.",
            "Copy Path": "Copy all selected full paths as text.",
            "Delete": "Delete using the configured Recycle Bin policy.",
            "Permanent Delete": "Permanently delete after a warning.",
        }
        descriptions = {tr(label): tr(help_text) for label, help_text in descriptions.items()}
        self._file_context_tooltip = MenuToolTip(menu, descriptions)
        return menu

    def _show_file_context_menu(self, pane: FilePane, clicked: Path,
                                x_root: int, y_root: int) -> None:
        menu = self._build_file_context_menu(pane, clicked)
        try:
            menu.tk_popup(int(x_root), int(y_root))
        finally:
            menu.grab_release()

    def _open_folder_in_new_tab(self, pane: FilePane, path: Path) -> None:
        if path.is_dir():
            self.active = self._tabs_for(pane).add_tab(path)

    def switch_tab(self, direction: int) -> str:
        source = self.active or self.left_tabs.current()
        tabs = self._tabs_for(source)
        tab_ids = tabs.tabs()
        if tab_ids:
            index = (tabs.index(tabs.select()) + direction) % len(tab_ids)
            tabs.select(tab_ids[index])
            tabs.current().focus_file_list()
        return "break"

    def switch_panel(self) -> str:
        source, target = self.panes()
        self.set_active(target)
        target.focus_file_list()
        return "break"

    def focus_path(self) -> str:
        source = self.panes()[0]
        source.path_entry.focus_set()
        source.path_entry.selection_range(0, "end")
        return "break"

    def focus_files(self) -> str:
        if self._drag_state is not None:
            self._handle_internal_drag("cancel", self._drag_state["source"], None)
        source = self.panes()[0]
        source.focus_file_list()
        return "break"

    def move_selection(self, direction: int) -> str | None:
        source = self.panes()[0]
        if self.focus_get() is not source.tree:
            return None
        children = source.tree.get_children()
        if not children:
            return "break"
        selected = source.tree.selection()
        current = selected[0] if selected and selected[0] in children else source.tree.focus()
        try:
            index = children.index(current)
        except ValueError:
            index = 0
        target = children[max(0, min(index + direction, len(children) - 1))]
        source.tree.selection_set(target)
        source.tree.focus(target)
        source.tree.see(target)
        return "break"

    def show_help(self) -> str:
        existing = getattr(self, "help_window", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return "break"
        dialog = tk.Toplevel(self)
        self.help_window = dialog
        dialog.title(f"Python File Commander — {tr('Keyboard Guide')}")
        dialog.transient(self)
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=tr("Keyboard shortcuts not shown on the bottom action bar"),
                  font=tkfont.nametofont("TkHeadingFont")).pack(anchor="w", pady=(0, 12))
        guide = tr("Keyboard guide body")
        ttk.Label(body, text=guide, justify="left").pack(anchor="w")
        button = ttk.Button(body, text=tr("OK"), command=dialog.destroy)
        button.pack(anchor="e", pady=(16, 0))
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.bind("<Return>", lambda _event: dialog.destroy())
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.grab_set()
        button.focus_set()
        return "break"

    def show_header_menu(self, which: str) -> str:
        button, menu = {"files": (self.files_menu_button, self.files_menu),
                        "view": (self.view_menu_button, self.view_menu),
                        "versions": (self.versions_menu_button, self.versions_menu)}[which]
        menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())
        return "break"

    def version_series_notes(self, series: str) -> tuple[str, str]:
        items = [(version, date, notes) for version, date, notes in VERSION_HISTORY
                 if version.rsplit(".", 1)[0] + ".x" == series]
        title = f"Python File Commander — {series} Changes"
        body = "\n\n".join(f"{version} — Build {date}\n" +
                           "\n".join(f"• {note}" for note in notes)
                           for version, date, notes in items)
        return title, body or "No release notes available."

    def show_version_series(self, series: str) -> None:
        title, body = self.version_series_notes(series)
        messagebox.showinfo(title, body, parent=self)

    def show_yoda_note(self) -> None:
        body = (
            "Yoda is the advocate who helped bring this portable app into being.\n\n"
            "Please report any issues you encounter so they can be reviewed and improved.\n\n"
            "Use file operations carefully, especially Move, Replace, Safe Sync, and "
            "Permanent Delete."
        )
        messagebox.showinfo("Python File Commander — Yoda", body, parent=self)

    def _show_folder_menu(self, menu: tk.Menu, rebuild) -> str:
        rebuild()
        menu.tk_popup(self.files_menu_button.winfo_rootx(),
                      self.files_menu_button.winfo_rooty() + self.files_menu_button.winfo_height())
        return "break"

    def _rebuild_favorites_menu(self) -> None:
        menu = self.favorites_menu; menu.delete(0, "end")
        current = self.panes()[0].path
        normalized = os.path.normcase(str(current))
        existing = any(os.path.normcase(str(path)) == normalized for path in self.favorites)
        menu.add_command(label=tr("Remove Current Folder") if existing else tr("Add Current Folder"),
                         accelerator="Ctrl+D", command=self.toggle_favorite)
        if self.favorites:
            menu.add_separator()
            for path in self.favorites:
                menu.add_command(label=str(path), command=lambda target=path: self.navigate_to_folder(target))

    def _rebuild_recent_menu(self) -> None:
        menu = self.recent_menu; menu.delete(0, "end")
        if self.recent_folders:
            for path in self.recent_folders:
                menu.add_command(label=str(path), command=lambda target=path: self.navigate_to_folder(target))
            menu.add_separator()
            menu.add_command(label=tr("Clear Recent Folders"), command=self.clear_recent_folders)
        else:
            menu.add_command(label=tr("No recent folders"), state="disabled")

    def toggle_favorite(self) -> str:
        current = self.panes()[0].path
        normalized = os.path.normcase(str(current))
        remaining = [path for path in self.favorites if os.path.normcase(str(path)) != normalized]
        self.favorites = remaining if len(remaining) != len(self.favorites) else [current, *self.favorites]
        self.favorites = self._deduplicate_paths(self.favorites)
        self.save_config()
        return "break"

    def clear_recent_folders(self) -> None:
        self.recent_folders = []
        self.save_config(record_recent=False)

    def navigate_to_folder(self, path: Path) -> None:
        source = self.panes()[0]
        if source.navigate(path):
            self._record_recent(source.path); source.focus_file_list(); self.save_config()

    def refresh(self) -> None:
        for pane in self.visible_panes():
            pane.refresh()

    def open(self) -> None:
        self.panes()[0].open_selected()

    def enter_folder(self) -> str | None:
        source = self.panes()[0]
        if self.focus_get() is not source.tree:
            return None
        self.open()
        return "break"

    def parent_folder(self) -> str | None:
        source = self.panes()[0]
        if self.focus_get() is not source.tree:
            return None
        source.up()
        source.focus_file_list()
        return "break"

    def preview(self) -> None:
        source, _ = self.panes()
        items = source.selected_paths()
        if not items:
            return
        ordered = []
        for iid in source.tree.get_children():
            tags = source.tree.item(iid, "tags")
            if tags:
                ordered.append(Path(tags[0]))
        self.preview_paths(ordered or items, items[0])

    def preview_paths(self, paths, selected) -> None:
        if self.preview_window is None or not self.preview_window.winfo_exists():
            self.preview_window = PreviewWindow(self, self.config_data, self.save_config, paths, selected)
        else: self.preview_window.show(paths, selected)

    def search(self) -> None:
        source, _ = self.panes()
        if self.search_window is None or not self.search_window.winfo_exists():
            self.search_window = SearchWindow(self, self.config_data, self.save_config, source.path,
                                              lambda path, pane=source: self.go_to_search_result(path, pane),
                                              self.preview_paths)
        else:
            self.search_window.path_var.set(str(source.path))
            self.search_window.on_go = lambda path, pane=source: self.go_to_search_result(path, pane)
            self.search_window.activate()

    def go_to_search_result(self, path: Path, source: FilePane) -> None:
        self.set_active(source)
        if path.is_dir(): source.navigate(path)
        elif source.navigate(path.parent): source.select_path(path)
        source.update_idletasks()
        if path.is_file(): source.select_path(path)
        source.focus_file_list(); self.lift(); self.focus_force()
        if path.is_file(): self.after_idle(lambda: (source.select_path(path), source.focus_file_list()))

    def new_tab(self) -> None:
        source, _ = self.panes()
        tabs = self._tabs_for(source)
        self.active = tabs.add_tab(source.path)

    def close_tab(self) -> None:
        source, _ = self.panes()
        tabs = self._tabs_for(source)
        tabs.close_current()
        self.active = tabs.current()

    def select_all(self) -> None:
        source, _ = self.panes()
        source.tree.selection_set(source.tree.get_children())

    def copy_path(self) -> None:
        source, _ = self.panes()
        items = source.selected_paths()
        value = str(items[0] if items else source.path)
        self.clipboard_clear(); self.clipboard_append(value)

    def copy_paths(self) -> str:
        items = self.panes()[0].selected_paths()
        if not items:
            messagebox.showinfo(tr("Copy Path"), tr("Select one or more files or folders."), parent=self)
            return "break"
        self.clipboard_clear()
        self.clipboard_append("\n".join(str(item.resolve()) for item in items))
        self.update_idletasks()
        noun = "path" if len(items) == 1 else "paths"
        messagebox.showinfo(tr("Copy Path"), tr("{count} {kind} copied to clipboard.",
                                                count=len(items), kind=tr(noun)), parent=self)
        return "break"

    def change_dir(self) -> str:
        return self.focus_path()

    def clipboard_copy(self) -> None:
        self._set_file_clipboard(cut=False)

    def clipboard_cut(self) -> None:
        self._set_file_clipboard(cut=True)

    def _set_file_clipboard(self, cut: bool) -> None:
        if self._clipboard_is_text_control():
            return
        items = self.panes()[0].selected_paths()
        if not items:
            return
        try:
            set_file_clipboard(items, cut=cut)
        except (OSError, MemoryError) as exc:
            messagebox.showerror(tr("Clipboard failed"), str(exc), parent=self)

    def clipboard_paste(self) -> None:
        if self._clipboard_is_text_control():
            return
        self._clipboard_paste_to(self.panes()[0].path)

    def _clipboard_paste_to(self, destination: Path) -> None:
        if not destination.is_dir():
            return
        try:
            items, cut = get_file_clipboard()
            items = [item for item in items if item.exists()]
            if not items:
                if not get_virtual_file_descriptors():
                    return
                with tempfile.TemporaryDirectory(prefix="pfc-outlook-") as raw:
                    virtual_items, failures = extract_virtual_files(Path(raw))
                    if virtual_items:
                        self._execute_transfer("Copy Outlook attachment", copy_items, virtual_items,
                                               destination, confirm=False, allow_retry=False)
                    if failures:
                        result = OperationResult(failures=[
                            OperationFailure(Path(name), destination, message) for name, message in failures])
                        self._show_operation_result("Outlook attachment paste", result)
                return
            operation = move_items if cut else copy_items
            result = self._execute_transfer("Move" if cut else "Copy", operation, items,
                                            destination, confirm=False)
            if cut and result is not None and result.successful:
                clear_file_clipboard()
        except (OSError, MemoryError, shutil.Error) as exc:
            messagebox.showerror(tr("Paste failed"), str(exc), parent=self)

    def _clipboard_is_text_control(self) -> bool:
        focused = self.focus_get()
        return isinstance(focused, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox))

    def toggle_hidden(self) -> None:
        source = self.panes()[0]
        source.toggle_hidden()
        self.show_hidden_var.set(source.show_hidden)

    def set_hidden_visibility(self) -> None:
        source = self.panes()[0]
        source.show_hidden = self.show_hidden_var.get()
        source.refresh(); source.on_change()

    def set_system_visibility(self) -> None:
        source = self.panes()[0]
        source.show_system = self.show_system_var.get()
        source.refresh(); source.on_change()

    def set_extension_visibility(self) -> None:
        source = self.panes()[0]
        source.show_extensions = self.show_extensions_var.get()
        source.refresh(); source.on_change()

    def compare_selected(self) -> None:
        source, target = self.panes()
        source_items = source.selected_paths()
        target_items = target.selected_paths()
        if not source_items and not target_items:
            left, right = source.path, target.path
        elif len(source_items) == 1 and len(target_items) == 1:
            left, right = source_items[0], target_items[0]
        else:
            active_items = source.selected_paths()
            if len(active_items) != 2:
                messagebox.showinfo(tr("Compare"), tr("Select one item in the active and next panel, or two items in the active panel."), parent=self)
                return
            left, right = active_items
        try:
            if self.compare_window is None or not self.compare_window.winfo_exists():
                self.compare_window = CompareWindow(self, self.config_data, self.save_config,
                                                    self.execute_sync_plans)
                self.compare_window.notebook.set_style(self.tab_style_var.get())
            self.compare_window.add(left, right)
        except OSError as exc:
            messagebox.showerror(tr("Compare failed"), str(exc), parent=self)

    def execute_sync_plans(self, plans: list[tuple[Path, Path]]) -> OperationResult:
        result = OperationResult(); resolver = self._conflict_resolver()
        for index, (source, target) in enumerate(plans):
            try:
                partial = copy_items([source], target.parent, resolver, self.continue_errors_var.get())
            except (OSError, shutil.Error) as exc:
                partial = OperationResult(failures=[OperationFailure(source, target, str(exc))])
            result.completed.extend(partial.completed)
            result.skipped.extend(partial.skipped)
            result.failures.extend(partial.failures)
            if partial.failures and not self.continue_errors_var.get():
                result.skipped.extend(source for source, _target in plans[index + 1:])
                break
        self.refresh(); self._show_operation_result("Safe Sync", result)
        return result

    def apply_font_size(self, save: bool = True) -> None:
        scale = self._font_scales.get(self.font_size_var.get(), 1.0)
        if self.font_size_var.get() not in self._font_scales:
            self.font_size_var.set("small")
        for name, base in self._base_font_sizes.items():
            size = max(1, round(abs(base) * scale))
            tkfont.nametofont(name).configure(size=-size if base < 0 else size)
        row_height = max(22, round(22 * scale))
        style = ttk.Style(self)
        style.configure("Active.Treeview", rowheight=row_height)
        style.configure("Inactive.Treeview", rowheight=row_height)
        control_padding = max(1, round(3 * scale))
        style.configure("TEntry", font=tkfont.nametofont("TkTextFont"), padding=control_padding)
        style.configure("TCombobox", font=tkfont.nametofont("TkTextFont"), padding=control_padding)
        style.configure("TButton", font=tkfont.nametofont("TkDefaultFont"), padding=control_padding)
        clipboard_icon_size = max(16, round(18 * scale))
        if clipboard_icon_size != self._clipboard_icon_size:
            self._clipboard_icon_size = clipboard_icon_size
            self.clipboard_icons = ShellIconProvider(clipboard_icon_size)
            self._clipboard_visual_key = None
        if hasattr(self, "panel_tabs"):
            for pane in self.all_panes():
                pane.apply_scale(scale)
            for tabs in self.panel_tabs:
                tabs.redraw()
        if self.compare_window is not None and self.compare_window.winfo_exists():
            self.compare_window.notebook.redraw()
        self.update_idletasks()
        if save:
            self.save_config()

    def apply_tab_style(self, save: bool = True) -> None:
        style = self.tab_style_var.get()
        if style == "compact":
            style = "right_skirt"; self.tab_style_var.set(style)
        if style not in TAB_STYLES:
            style = "right_skirt"; self.tab_style_var.set(style)
        if hasattr(self, "panel_tabs"):
            for tabs in self.panel_tabs:
                tabs.set_style(style)
        if self.compare_window is not None and self.compare_window.winfo_exists():
            self.compare_window.notebook.set_style(style)
        if save:
            self.save_config()

    def _conflict_resolver(self):
        shared_action = None
        def resolve(source: Path, target: Path) -> str:
            nonlocal shared_action
            if shared_action is not None:
                return shared_action
            action, apply_all = ConflictDialog.ask(self, source, target)
            if apply_all:
                shared_action = action
            return action
        return resolve

    def _show_operation_result(self, verb: str, result: OperationResult, retry=None) -> None:
        if not result.failures and not result.skipped:
            return
        display_verb = tr(verb)
        details = [tr("{verb}: {completed} completed, {skipped} skipped, {failed} failed.",
                      verb=display_verb, completed=len(result.completed),
                      skipped=len(result.skipped), failed=len(result.failures)), ""]
        details.extend(f"SKIPPED: {path}" for path in result.skipped)
        for failure in result.failures:
            destination = f" -> {failure.target}" if failure.target else ""
            details.append(f"FAILED: {failure.source}{destination}\n  {failure.message}")
        report = "\n".join(details)
        dialog = tk.Toplevel(self); dialog.title(tr("{verb} result", verb=display_verb)); dialog.transient(self)
        dialog.geometry("760x420"); dialog.minsize(540, 280)
        ttk.Label(dialog, text=details[0], font=tkfont.nametofont("TkHeadingFont"),
                  padding=(8, 8, 8, 4)).pack(anchor="w")
        text = tk.Text(dialog, wrap="word", height=12, font=tkfont.nametofont("TkFixedFont"))
        text.insert("1.0", report); text.configure(state="disabled"); text.pack(fill="both", expand=True, padx=8)
        buttons = ttk.Frame(dialog, padding=8); buttons.pack(fill="x")
        def copy_report():
            self.clipboard_clear(); self.clipboard_append(report); self.update_idletasks()
        ttk.Button(buttons, text=tr("Copy Details"), command=copy_report).pack(side="left")
        if retry is not None and result.failures:
            def retry_failed():
                failed = [failure.source for failure in result.failures]
                dialog.destroy(); retry(failed)
            ttk.Button(buttons, text=tr("Retry Failed"), command=retry_failed).pack(side="left", padx=4)
        ttk.Button(buttons, text=tr("Close"), command=dialog.destroy).pack(side="right")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.lift(); dialog.focus_force()

    def _execute_transfer(self, verb: str, operation, items: list[Path], destination: Path,
                          confirm: bool = True, allow_retry: bool = True) -> OperationResult | None:
        if not items:
            return None
        display_verb = tr(verb)
        if confirm and not messagebox.askyesno(display_verb,
                                                tr("{verb} {count} selected item(s) to:\n{destination}?",
                                                   verb=display_verb, count=len(items), destination=destination),
                                                parent=self):
            return None
        try:
            result = operation(items, destination, self._conflict_resolver(), self.continue_errors_var.get())
        except (OSError, shutil.Error) as exc:
            result = OperationResult(failures=[OperationFailure(items[0], destination, str(exc))])
        self.refresh()
        retry = (lambda failed: self._execute_transfer(verb, operation, failed, destination,
                                                        confirm=False, allow_retry=allow_retry)) if allow_retry else None
        self._show_operation_result(verb, result, retry=retry)
        return result

    def _run(self, verb: str, operation) -> None:
        source, target = self.panes()
        self._execute_transfer(verb, operation, source.selected_paths(), target.path)

    def copy(self) -> None:
        self._run("Copy", copy_items)

    def move(self) -> None:
        self._run("Move", move_items)

    def delete(self, permanent: bool = False) -> None:
        source, _ = self.panes()
        items = source.selected_paths()
        if not items:
            return
        permanent = permanent or not self.recycle_bin_var.get()
        if permanent:
            prompt = tr("This cannot be undone.\n\nPermanently delete {count} selected item(s)?",
                        count=len(items))
            if not messagebox.askyesno(tr("Permanent delete warning"), prompt, icon="warning", parent=self):
                return
            operation, verb = delete_items, "Permanent delete"
        else:
            if not messagebox.askyesno(tr("Recycle Bin"), tr("Move {count} selected item(s) to the Recycle Bin?", count=len(items)),
                                       parent=self):
                return
            operation, verb = recycle_items, "Recycle"
        result = operation(items, self.continue_errors_var.get()); self.refresh()
        self._show_operation_result(verb, result,
                                    retry=lambda failed: self._retry_delete(failed, permanent))

    def delete_hotkey(self, permanent: bool = False) -> None:
        if not self._clipboard_is_text_control():
            self.delete(permanent=permanent)

    def _retry_delete(self, items: list[Path], permanent: bool) -> None:
        operation, verb = (delete_items, "Permanent delete") if permanent else (recycle_items, "Recycle")
        result = operation(items, self.continue_errors_var.get()); self.refresh()
        self._show_operation_result(verb, result,
                                    retry=lambda failed: self._retry_delete(failed, permanent))

    def mkdir(self) -> None:
        source, _ = self.panes()
        name = simpledialog.askstring(tr("New Folder"), tr("Folder name:"), parent=self)
        if name:
            try:
                (source.path / name).mkdir(); source.refresh()
            except OSError as exc:
                messagebox.showerror(tr("Create failed"), str(exc))

    def rename(self) -> None:
        source, _ = self.panes()
        items = source.selected_paths()
        if len(items) > 1:
            self.multi_rename(); return
        if len(items) != 1:
            messagebox.showinfo(tr("Rename"), tr("Select exactly one item.")); return
        name = simpledialog.askstring(tr("Rename"), tr("New name:"), initialvalue=items[0].name, parent=self)
        if name and name != items[0].name:
            try:
                items[0].rename(items[0].with_name(name)); self.refresh()
            except OSError as exc:
                messagebox.showerror(tr("Rename failed"), str(exc))

    def multi_rename(self) -> None:
        items = self.panes()[0].selected_paths()
        if len(items) < 2:
            messagebox.showinfo(tr("Multi-Rename"), tr("Select two or more items first."), parent=self)
            return
        if self.multi_rename_window is not None and self.multi_rename_window.winfo_exists():
            self.multi_rename_window.destroy()
        self.multi_rename_window = MultiRenameWindow(self, items, self._rename_undo, self.refresh)


def main() -> None:
    if relaunch_with_pythonw():
        return
    hide_private_console()
    Commander().mainloop()
