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
from .tooltip import MenuToolTip, install_button_tooltips
from .tabs import ChamferNotebook


# The single-file builder replaces this fallback with a fixed date literal.
BUILD_DATE = datetime.now().strftime("%Y/%m/%d")
VERSION_HISTORY = (
    ("v0.8.3", "2026/07/14", "Internal drag-and-drop with Copy/Shift+Move visuals; aligned menu accelerators; version history menu."),
    ("v0.8.2", "2026/07/14", "Paste Outlook virtual attachments and identify them in the clipboard summary."),
    ("v0.8.1", "2026/07/14", "Recycle Bin delete, safe conflict handling, Favorites/Recent folders, and operation recovery."),
    ("v0.8.0", "2026/07/13", "First versioned beta with dual panels, tabs, Preview, Search, Compare, keyboard workflow, and portable INI."),
)


def ensure_config_defaults(config: configparser.ConfigParser) -> None:
    defaults = {
        "view": {"font_size": "small"},
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
                 on_drag=lambda _action, _pane, _event: None) -> None:
        super().__init__(master)
        self.on_activate = on_activate
        self.on_change = on_change
        self.on_drag = on_drag
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
        self._drag_press_item = None
        self._drag_press_xy = None
        self._dragging = False
        self.heading_labels = {"name": "Name", "ext": "Ext", "size": "Size", "modified": "Date Modified", "attr": "Attr"}
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
        self.tree.heading("#0", text="Name ▲", command=lambda: self.change_sort("name"))
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
        self.tree.tag_configure("PFC_DROP_TARGET", background="#8ec8f0", foreground="#102b3c")
        self.status = ttk.Label(self, anchor="w")
        self.status.pack(fill="x", pady=(3, 0))
        install_button_tooltips(self)
        self.navigate(self.path)

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
            messagebox.showerror("Cannot open folder", str(exc))
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
            self.status.configure(text=f"{len(entries)} items   {format_size(total)}")
            current = self.tree.selection()
            children = self.tree.get_children()
            if not current and children:
                self.tree.selection_set(children[0])
                self.tree.focus(children[0])
                self.tree.see(children[0])
            elif children:
                self.tree.yview_moveto(scroll_position)
        except OSError as exc:
            messagebox.showerror("Cannot read folder", str(exc))

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
                messagebox.showerror("Cannot open file", str(exc))

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
            messagebox.showerror("Preview failed", str(exc))

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
            messagebox.showerror("Search failed", str(exc))

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
                 on_drag=lambda _action, _pane, _event: None) -> None:
        self.color_for = color_for
        self.on_tab_color = on_tab_color
        self.on_drag = on_drag
        super().__init__(master, on_color_changed=self._color_changed,
                         on_lock_changed=self._lock_changed)
        self.on_activate = on_activate
        self.on_change = on_change
        self.bind("<<NotebookTabChanged>>", lambda _e: self._tab_changed())
        for path in initial_paths or [Path.home()]:
            self.add_tab(path, notify=False)

    def add_tab(self, path: Path, notify: bool = True) -> FilePane:
        position = self.index(self.select()) + 1 if self.tabs() else 0
        pane = FilePane(self, self.on_activate, on_drag=self.on_drag)
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


class ConflictDialog(tk.Toplevel):
    def __init__(self, parent, source: Path, target: Path) -> None:
        super().__init__(parent)
        self.result = ("cancel", False)
        self.apply_all = tk.BooleanVar(value=False)
        self.title("File conflict"); self.resizable(False, False); self.transient(parent)
        body = ttk.Frame(self, padding=12); body.pack(fill="both", expand=True)
        ttk.Label(body, text="An item with the same name already exists.",
                  font=tkfont.nametofont("TkHeadingFont")).pack(anchor="w", pady=(0, 8))
        ttk.Label(body, text=f"Source: {source}\nTarget: {target}", justify="left",
                  wraplength=720).pack(anchor="w")
        ttk.Checkbutton(body, text="Apply this choice to all remaining conflicts",
                        variable=self.apply_all).pack(anchor="w", pady=(12, 8))
        buttons = ttk.Frame(body); buttons.pack(fill="x")
        first_button = None
        for text, action in (("Replace", "replace"), ("Skip", "skip"),
                             ("Keep Both", "keep_both"), ("Cancel", "cancel")):
            button = ttk.Button(buttons, text=text, command=lambda value=action: self.choose(value))
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
        self._drag_state = None
        self._drag_ghost = None
        self._drag_highlight = None
        self.font_size_var = tk.StringVar(value=self.config_data.get("view", "font_size", fallback="small"))
        self.recycle_bin_var = tk.BooleanVar(
            value=self.config_data.getboolean("operations", "send_delete_to_recycle_bin", fallback=True))
        self.continue_errors_var = tk.BooleanVar(
            value=self.config_data.getboolean("operations", "continue_after_error", fallback=True))
        self.favorites = self._load_navigation_paths("favorites")
        self.recent_folders = self._load_navigation_paths("recent_folders")
        self._font_scales = {"small": 1.0, "medium": 1.5, "large": 2.0, "huge": 3.0}
        self._base_font_sizes = {}
        for name in ("TkDefaultFont", "TkTextFont", "TkFixedFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
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
        left_paths = self._saved_paths("left")
        right_paths = self._saved_paths("right")
        self.left_tabs = PaneTabs(split, self.set_active, self.save_config, left_paths,
                                  self.get_tab_color, self.set_tab_color, self._handle_internal_drag)
        self.right_tabs = PaneTabs(split, self.set_active, self.save_config, right_paths,
                                   self.get_tab_color, self.set_tab_color, self._handle_internal_drag)
        self.left = self.left_tabs.current()
        self.right = self.right_tabs.current()
        split.add(self.left_tabs, weight=1)
        split.add(self.right_tabs, weight=1)
        self._restore_tab(self.left_tabs, "left")
        self._restore_tab(self.right_tabs, "right")
        self._restore_panel_options(self.left_tabs, "left")
        self._restore_panel_options(self.right_tabs, "right")
        self.active = self.right_tabs.current() if self.config_data.get("state", "active_panel", fallback="left") == "right" else self.left_tabs.current()
        self.apply_font_size(save=False)
        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=5, pady=(0, 5))
        for text, command in (("F2 Rename", self.rename), ("F3 Preview", self.preview),
                              ("F4 Search", self.search), ("F5 Copy", self.copy),
                              ("F6 Move", self.move), ("F7 New folder", self.mkdir),
                              ("F8", None), ("F9 Compare", self.compare_selected),
                              ("F11 Copy Path", self.copy_paths), ("F12 Change Dir", self.change_dir)):
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
        except (json.JSONDecodeError, TypeError):
            colors, locks, locked_paths = [], [], []
        for index, pane in enumerate(tabs.panes()):
            pane.sort_column = column if column in pane.all_sort_columns else "name"
            pane.reverse = descending
            pane.show_hidden = show_hidden
            pane.show_system = show_system
            pane.show_extensions = show_extensions
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
        for side, tabs in (("left", self.left_tabs), ("right", self.right_tabs)):
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
        self.config_data.set("state", "active_panel", "left" if self.active in self.left_tabs.panes() else "right")
        self.config_data.set("view", "font_size", self.font_size_var.get())
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
            paths = (self.left_tabs.current().path, self.right_tabs.current().path)
            network = any(str(path).startswith("\\\\") for path in paths)
            key = "network_interval_ms" if network else ("active_interval_ms" if focused else "background_interval_ms")
            delay = self.config_data.getint("refresh", key, fallback=5000)
        self._auto_refresh_job = self.after(max(500, delay), self._auto_refresh_tick)

    def _auto_refresh_tick(self) -> None:
        self._auto_refresh_job = None
        if self.config_data.getboolean("refresh", "auto_refresh", fallback=True):
            self.left_tabs.current().refresh_if_changed()
            self.right_tabs.current().refresh_if_changed()
        self._schedule_auto_refresh()

    def _build_menu(self) -> None:
        menu_font = tkfont.nametofont("TkMenuFont")
        header_bg, header_fg, active_bg = "#243b53", "#f4f8fb", "#365b78"
        header = tk.Frame(self, background=header_bg, padx=5, pady=4)
        header.pack(fill="x")
        title = tk.Label(header, text=f"Python File Commander   v{__version__}   Build {BUILD_DATE}",
                         font=tkfont.nametofont("TkCaptionFont"),
                         background=header_bg, foreground=header_fg, cursor="hand2")
        title.pack(side="left", padx=(2, 10))
        title.bind("<Button-1>", lambda _event: self.show_help())
        button_style = dict(font=menu_font, relief="flat", borderwidth=0, padx=7,
                            background=header_bg, foreground=header_fg,
                            activebackground=active_bg, activeforeground="#ffffff")
        files_button = tk.Menubutton(header, text="Files", **button_style)
        files_button.pack(side="left")
        files = tk.Menu(files_button, tearoff=False, font=menu_font)
        files_button.configure(menu=files)
        files.add_command(label="Copy to Clipboard", accelerator="Ctrl+C", command=self.clipboard_copy)
        files.add_command(label="Cut to Clipboard", accelerator="Ctrl+X", command=self.clipboard_cut)
        files.add_command(label="Paste", accelerator="Ctrl+V", command=self.clipboard_paste)
        files.add_separator()
        files.add_command(label="Copy to Other Panel", accelerator="F5", command=self.copy)
        files.add_command(label="Move to Other Panel", accelerator="F6", command=self.move)
        files.add_command(label="Rename", accelerator="F2", command=self.rename)
        files.add_command(label="New Folder", accelerator="F7", command=self.mkdir)
        files.add_separator()
        files.add_command(label="Delete", accelerator="Del", command=self.delete)
        files.add_command(label="Permanent Delete", accelerator="Shift+Del", command=lambda: self.delete(permanent=True))
        files.add_checkbutton(label="Send Delete to Recycle Bin", variable=self.recycle_bin_var,
                              command=self.save_config)
        files.add_checkbutton(label="Continue After File Errors", variable=self.continue_errors_var,
                              command=self.save_config)
        files.add_separator()
        self.favorites_menu = tk.Menu(files, tearoff=False, font=menu_font,
                                      postcommand=self._rebuild_favorites_menu)
        self.recent_menu = tk.Menu(files, tearoff=False, font=menu_font,
                                   postcommand=self._rebuild_recent_menu)
        files.add_cascade(label="Favorites", menu=self.favorites_menu)
        files.add_cascade(label="Recent Folders", menu=self.recent_menu)
        files.add_separator()
        files.add_command(label="Preview", accelerator="F3", command=self.preview)
        files.add_command(label="Search", accelerator="F4", command=self.search)
        files.add_command(label="Compare", accelerator="F9", command=self.compare_selected)
        files.add_command(label="Copy Path", accelerator="F11", command=self.copy_paths)
        files.add_command(label="Change Dir", accelerator="F12", command=self.change_dir)
        files.add_separator()
        files.add_command(label="Exit", command=self.close_app)
        view_button = tk.Menubutton(header, text="View", **button_style)
        view_button.pack(side="left")
        view = tk.Menu(view_button, tearoff=False, font=menu_font)
        view_button.configure(menu=view)
        visibility = tk.Menu(view, tearoff=False, font=menu_font)
        self.show_hidden_var = tk.BooleanVar(value=False)
        self.show_system_var = tk.BooleanVar(value=False)
        self.show_extensions_var = tk.BooleanVar(value=True)
        visibility.add_checkbutton(label="Show Hidden", variable=self.show_hidden_var,
                                   command=self.set_hidden_visibility)
        visibility.add_checkbutton(label="Show System", variable=self.show_system_var,
                                   command=self.set_system_visibility)
        visibility.add_checkbutton(label="Show File Extension", variable=self.show_extensions_var,
                                   command=self.set_extension_visibility)
        view.add_cascade(label="File Visibility", menu=visibility)
        font_size = tk.Menu(view, tearoff=False, font=menu_font)
        for label, value in (("Small (100%)", "small"), ("Medium (150%)", "medium"),
                             ("Large (200%)", "large"), ("Huge (300%)", "huge")):
            font_size.add_radiobutton(label=label, value=value, variable=self.font_size_var,
                                      command=self.apply_font_size)
        view.add_cascade(label="Font Size", menu=font_size)
        versions_button = tk.Menubutton(header, text="Versions", **button_style)
        versions_button.pack(side="left")
        versions = tk.Menu(versions_button, tearoff=False, font=menu_font)
        versions_button.configure(menu=versions)
        versions.add_command(label=f"Current version: v{__version__}", state="disabled")
        versions.add_separator()
        for version, build_date, notes in VERSION_HISTORY:
            versions.add_command(label=version, accelerator=build_date,
                                 command=lambda value=version: self.show_version_notes(value))
        self.clipboard_summary = tk.Label(header, text="Clipboard: checking…", anchor="e", width=1,
                                          font=tkfont.nametofont("TkDefaultFont"),
                                          background=header_bg, foreground="#c9e5f5")
        self.clipboard_summary.pack(side="right", fill="x", expand=True, padx=(12, 4))
        self.files_menu_button = files_button
        self.view_menu_button = view_button
        self.versions_menu_button = versions_button
        self.files_menu = files
        self.view_menu = view
        self.versions_menu = versions
        menu_help = {
            "Copy to Clipboard": "Copy selected items for PFC or File Explorer.",
            "Cut to Clipboard": "Cut selected items for PFC or File Explorer.",
            "Paste": "Paste clipboard items into the active folder.",
            "Copy to Other Panel": "Copy selected items to the opposite panel.",
            "Move to Other Panel": "Move selected items to the opposite panel.",
            "Rename": "Rename the selected item.", "Preview": "Open PFC Preview.",
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
        }
        self._files_menu_tooltip = MenuToolTip(files, menu_help)
        self._view_menu_tooltip = MenuToolTip(view, menu_help)
        self._versions_menu_tooltip = MenuToolTip(
            versions, {version: notes for version, _date, notes in VERSION_HISTORY})
        self._visibility_menu_tooltip = MenuToolTip(visibility, menu_help)
        self._font_menu_tooltip = MenuToolTip(font_size, menu_help)
        self.config(menu="")

    def _schedule_clipboard_summary(self, delay=2000) -> None:
        self._clipboard_job = self.after(delay, self._update_clipboard_summary)

    def _update_clipboard_summary(self) -> None:
        self._clipboard_job = None
        try:
            paths, _cut = get_file_clipboard()
            if paths:
                folders = sum(path.is_dir() for path in paths)
                files = len(paths) - folders
                parts = []
                if files: parts.append(f"{files} {'File' if files == 1 else 'Files'}")
                if folders: parts.append(f"{folders} {'Folder' if folders == 1 else 'Folders'}")
                summary = f"Clipboard: {', '.join(parts)}"
            else:
                virtual_files = get_virtual_file_descriptors()
                if virtual_files:
                    count = len(virtual_files)
                    summary = f"Clipboard: {count} {'Attachment' if count == 1 else 'Attachments'}"
                else:
                    try:
                        value = self.clipboard_get()
                        size = len(value.encode("utf-8"))
                        summary = f"Clipboard: Strings {size:,} Bytes" if value else "Clipboard: Empty"
                    except tk.TclError:
                        summary = "Clipboard: OBJ"
            self.clipboard_summary.configure(text=summary)
        except (OSError, MemoryError):
            pass  # Keep the last useful summary while another app owns the clipboard.
        if self.winfo_exists():
            self._schedule_clipboard_summary()

    def set_active(self, pane: FilePane) -> None:
        self.active = pane
        self.show_hidden_var.set(pane.show_hidden)
        self.show_system_var.set(pane.show_system)
        self.show_extensions_var.set(pane.show_extensions)
        if hasattr(self, "left_tabs") and hasattr(self, "right_tabs"):
            for candidate in self.left_tabs.panes() + self.right_tabs.panes():
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

    def panes(self) -> tuple[FilePane, FilePane]:
        source = self.active or self.left_tabs.current()
        left_panes = [self.left_tabs.nametowidget(tab) for tab in self.left_tabs.tabs()]
        return (source, self.right_tabs.current() if source in left_panes else self.left_tabs.current())

    def _tabs_for(self, pane: FilePane) -> PaneTabs:
        return self.left_tabs if pane in self.left_tabs.panes() else self.right_tabs

    def _drop_target_at(self, x_root: int, y_root: int):
        for pane in (self.left_tabs.current(), self.right_tabs.current()):
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
        item_text = self._drag_state["items"][0].name if count == 1 else f"{count} selected items"
        action = "Move" if mode == "move" else "Copy"
        destination = str(target[1]) if target else "Not a PFC drop target"
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
        if action == "start":
            items = pane.selected_paths()
            if not items:
                return
            self._drag_state = {"source": pane, "items": items, "mode": "copy", "target": None}
            pane.tree.configure(cursor="fleur"); self._create_drag_ghost(); self._update_internal_drag(event)
            return
        if action == "motion":
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
        source = self.active or self.left_tabs.current()
        target = self.right_tabs.current() if source in self.left_tabs.panes() else self.left_tabs.current()
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
        dialog.title("Python File Commander — Keyboard Guide")
        dialog.transient(self)
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Keyboard shortcuts not shown on the bottom action bar",
                  font=tkfont.nametofont("TkHeadingFont")).pack(anchor="w", pady=(0, 12))
        guide = (
            "Navigation\n"
            "↑ / ↓  Select item\n"
            "Right / Left  Enter folder / return to parent\n"
            "Tab  Switch panel\n"
            "Ctrl+Tab / Ctrl+Shift+Tab  Next / previous tab\n"
            "Ctrl+Up  Clone current folder in a new tab\n"
            "Ctrl+W  Close current tab\n"
            "Ctrl+L  Focus and select the path\n"
            "Esc  Return focus to the file list\n\n"
            "Favorite and recent folders\n"
            "Ctrl+D  Add/remove current folder as a favorite\n"
            "Ctrl+B  Open Favorites    Ctrl+Shift+R  Open Recent Folders\n\n"
            "Mouse drag inside PFC\n"
            "Drag to a panel or folder row to Copy    Hold Shift to Move\n\n"
            "Selection and clipboard\n"
            "Ctrl+C / Ctrl+X / Ctrl+V  Copy / cut / paste with File Explorer\n"
            "Ctrl+A  Select all    Shift+Del  Permanent delete with warning\n"
            "Ctrl+Shift+C  Copy selected or current path\n"
            "Ctrl+H  Toggle hidden files\n"
            "Alt+F / Alt+V / Alt+H  Open Files / View / Versions menu"
        )
        ttk.Label(body, text=guide, justify="left").pack(anchor="w")
        button = ttk.Button(body, text="OK", command=dialog.destroy)
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

    def show_version_notes(self, version: str) -> None:
        item = next(((date, notes) for label, date, notes in VERSION_HISTORY if label == version), None)
        date, notes = item if item else ("Unknown", "No notes available.")
        messagebox.showinfo(f"Python File Commander {version}", f"Build {date}\n\n{notes}", parent=self)

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
        menu.add_command(label="Remove Current Folder" if existing else "Add Current Folder",
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
            menu.add_command(label="Clear Recent Folders", command=self.clear_recent_folders)
        else:
            menu.add_command(label="No recent folders", state="disabled")

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
        self.left_tabs.current().refresh(); self.right_tabs.current().refresh()

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
        tabs = self.left_tabs if source in [self.left_tabs.nametowidget(t) for t in self.left_tabs.tabs()] else self.right_tabs
        self.active = tabs.add_tab(source.path)

    def close_tab(self) -> None:
        source, _ = self.panes()
        tabs = self.left_tabs if source in [self.left_tabs.nametowidget(t) for t in self.left_tabs.tabs()] else self.right_tabs
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
            messagebox.showinfo("Copy Path", "Select one or more files or folders.", parent=self)
            return "break"
        self.clipboard_clear()
        self.clipboard_append("\n".join(str(item.resolve()) for item in items))
        self.update_idletasks()
        noun = "path" if len(items) == 1 else "paths"
        messagebox.showinfo("Copy Path", f"{len(items)} {noun} copied to clipboard.", parent=self)
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
            messagebox.showerror("Clipboard failed", str(exc), parent=self)

    def clipboard_paste(self) -> None:
        if self._clipboard_is_text_control():
            return
        destination = self.panes()[0].path
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
            messagebox.showerror("Paste failed", str(exc), parent=self)

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
        left_items = self.left_tabs.current().selected_paths()
        right_items = self.right_tabs.current().selected_paths()
        if len(left_items) == 1 and len(right_items) == 1:
            left, right = left_items[0], right_items[0]
        else:
            active_items = source.selected_paths()
            if len(active_items) != 2:
                messagebox.showinfo("Compare", "Select one item in each panel, or two items in the active panel.", parent=self)
                return
            left, right = active_items
        try:
            if self.compare_window is None or not self.compare_window.winfo_exists():
                self.compare_window = CompareWindow(self, self.config_data, self.save_config)
            self.compare_window.add(left, right)
        except OSError as exc:
            messagebox.showerror("Compare failed", str(exc), parent=self)

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
        if hasattr(self, "left_tabs"):
            for pane in self.left_tabs.panes() + self.right_tabs.panes():
                pane.apply_scale(scale)
            self.left_tabs.redraw(); self.right_tabs.redraw()
        if self.compare_window is not None and self.compare_window.winfo_exists():
            self.compare_window.notebook.redraw()
        self.update_idletasks()
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
        details = [f"{verb}: {len(result.completed)} completed, {len(result.skipped)} skipped, "
                   f"{len(result.failures)} failed.", ""]
        details.extend(f"SKIPPED: {path}" for path in result.skipped)
        for failure in result.failures:
            destination = f" -> {failure.target}" if failure.target else ""
            details.append(f"FAILED: {failure.source}{destination}\n  {failure.message}")
        report = "\n".join(details)
        dialog = tk.Toplevel(self); dialog.title(f"{verb} result"); dialog.transient(self)
        dialog.geometry("760x420"); dialog.minsize(540, 280)
        ttk.Label(dialog, text=details[0], font=tkfont.nametofont("TkHeadingFont"),
                  padding=(8, 8, 8, 4)).pack(anchor="w")
        text = tk.Text(dialog, wrap="word", height=12, font=tkfont.nametofont("TkFixedFont"))
        text.insert("1.0", report); text.configure(state="disabled"); text.pack(fill="both", expand=True, padx=8)
        buttons = ttk.Frame(dialog, padding=8); buttons.pack(fill="x")
        def copy_report():
            self.clipboard_clear(); self.clipboard_append(report); self.update_idletasks()
        ttk.Button(buttons, text="Copy Details", command=copy_report).pack(side="left")
        if retry is not None and result.failures:
            def retry_failed():
                failed = [failure.source for failure in result.failures]
                dialog.destroy(); retry(failed)
            ttk.Button(buttons, text="Retry Failed", command=retry_failed).pack(side="left", padx=4)
        ttk.Button(buttons, text="Close", command=dialog.destroy).pack(side="right")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.lift(); dialog.focus_force()

    def _execute_transfer(self, verb: str, operation, items: list[Path], destination: Path,
                          confirm: bool = True, allow_retry: bool = True) -> OperationResult | None:
        if not items:
            return None
        if confirm and not messagebox.askyesno(verb, f"{verb} {len(items)} selected item(s) to:\n{destination}?",
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
            prompt = ("This cannot be undone.\n\n"
                      f"Permanently delete {len(items)} selected item(s)?")
            if not messagebox.askyesno("Permanent delete warning", prompt, icon="warning", parent=self):
                return
            operation, verb = delete_items, "Permanent delete"
        else:
            if not messagebox.askyesno("Recycle Bin", f"Move {len(items)} selected item(s) to the Recycle Bin?",
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
        name = simpledialog.askstring("New folder", "Folder name:", parent=self)
        if name:
            try:
                (source.path / name).mkdir(); source.refresh()
            except OSError as exc:
                messagebox.showerror("Create failed", str(exc))

    def rename(self) -> None:
        source, _ = self.panes()
        items = source.selected_paths()
        if len(items) != 1:
            messagebox.showinfo("Rename", "Select exactly one item."); return
        name = simpledialog.askstring("Rename", "New name:", initialvalue=items[0].name, parent=self)
        if name and name != items[0].name:
            try:
                items[0].rename(items[0].with_name(name)); self.refresh()
            except OSError as exc:
                messagebox.showerror("Rename failed", str(exc))


def main() -> None:
    if relaunch_with_pythonw():
        return
    hide_private_console()
    Commander().mainloop()
