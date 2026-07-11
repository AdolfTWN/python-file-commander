from __future__ import annotations

import os
import configparser
import ctypes
import json
import shutil
import subprocess
import sys
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from .fileops import copy_items, delete_items, format_size, is_system, move_items, roots
from .clipboard import clear_file_clipboard, get_file_clipboard, set_file_clipboard
from .icons import ShellIconProvider
from .compare import CompareWindow
from .tabs import ChamferNotebook


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

    def __init__(self, master: tk.Misc, on_activate, on_change=lambda: None) -> None:
        super().__init__(master)
        self.on_activate = on_activate
        self.on_change = on_change
        self.path = Path.home()
        self.history: list[Path] = []
        self.sort_column = "name"
        self.reverse = False
        self.show_hidden = False
        self.show_system = False
        self.mode = "files"
        self.display_title = self.path.name or str(self.path)
        self.lock_mode = "unlocked"
        self.locked_path: Path | None = None
        self.on_locked_navigation = lambda _path: None
        self._signature = None
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
        self.status = ttk.Label(self, anchor="w")
        self.status.pack(fill="x", pady=(3, 0))
        self.navigate(self.path)

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
                    name = f"[{p.name}]" if is_dir else p.name
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
                    self.tree.insert("", "end", text=str(item.relative_to(self.path)), image=self.icons.get(item, is_dir), values=(
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
                 color_for=lambda _path: "default", on_tab_color=lambda _path, _color: None) -> None:
        self.color_for = color_for
        self.on_tab_color = on_tab_color
        super().__init__(master, on_color_changed=self._color_changed,
                         on_lock_changed=self._lock_changed)
        self.on_activate = on_activate
        self.on_change = on_change
        self.bind("<<NotebookTabChanged>>", lambda _e: self._tab_changed())
        for path in initial_paths or [Path.home()]:
            self.add_tab(path, notify=False)

    def add_tab(self, path: Path, notify: bool = True) -> FilePane:
        position = self.index(self.select()) + 1 if self.tabs() else 0
        pane = FilePane(self, self.on_activate)
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


class Commander(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self._ready = False
        self.ini_path = self._find_ini_path()
        self.config_data = configparser.ConfigParser()
        self.config_data.read(self.ini_path, encoding="utf-8")
        try:
            self._tab_colors = json.loads(self.config_data.get("tab_colors", "colors", fallback="{}"))
        except (json.JSONDecodeError, TypeError):
            self._tab_colors = {}
        self.title("Python File Commander")
        self.geometry(self.config_data.get("window", "geometry", fallback="1200x720"))
        self.minsize(800, 480)
        self.active: FilePane | None = None
        self.compare_window = None
        self.font_size_var = tk.StringVar(value=self.config_data.get("view", "font_size", fallback="small"))
        self._font_scales = {"small": 1.0, "medium": 1.5, "large": 2.0, "huge": 3.0}
        self._base_font_sizes = {}
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
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
                                  self.get_tab_color, self.set_tab_color)
        self.right_tabs = PaneTabs(split, self.set_active, self.save_config, right_paths,
                                   self.get_tab_color, self.set_tab_color)
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
            "files_menu": "<Alt-f>", "view_menu": "<Alt-v>",
            "copy_paths": "<F11>", "change_dir": "<F12>",
            "compare": "<F9>",
        }
        commands = {
            "rename": self.rename, "preview": self.preview, "search": self.search, "copy": self.copy,
            "move": self.move, "new_folder": self.mkdir, "delete": self.delete, "refresh": self.refresh,
            "enter_folder": self.enter_folder, "parent_folder": self.parent_folder, "new_tab": self.new_tab,
            "close_tab": self.close_tab, "select_all": self.select_all,
            "copy_path": self.copy_path, "toggle_hidden": self.toggle_hidden,
            "clipboard_copy": self.clipboard_copy, "clipboard_cut": self.clipboard_cut,
            "clipboard_paste": self.clipboard_paste,
            "next_tab": lambda: self.switch_tab(1),
            "previous_tab": lambda: self.switch_tab(-1),
            "switch_panel": self.switch_panel, "focus_path": self.focus_path,
            "focus_files": self.focus_files, "help": self.show_help,
            "files_menu": lambda: self.show_header_menu("files"),
            "view_menu": lambda: self.show_header_menu("view"),
            "copy_paths": self.copy_paths, "change_dir": self.change_dir,
            "compare": self.compare_selected,
        }
        if not self.config_data.has_section("hotkeys"):
            self.config_data.add_section("hotkeys")
        configured_hotkeys = {}
        for name, default in defaults.items():
            key = self.config_data.get("hotkeys", name, fallback=default)
            self.config_data.set("hotkeys", name, key)
            configured_hotkeys[name] = key
            self.bind_all(key, lambda _e, fn=commands[name]: fn())
        self._install_priority_hotkeys(configured_hotkeys, commands)
        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self._ready = True
        self._save_job = None
        self._auto_refresh_job = None
        self.bind("<Configure>", self._schedule_save)
        self.set_active(self.active)
        self.save_config()
        self._schedule_auto_refresh(250)

    def _install_priority_hotkeys(self, hotkeys, commands) -> None:
        """Run tab navigation before Tk widget/class bindings can consume Tab."""
        tag = f"PFCKeyboard{id(self)}"
        for name in ("switch_panel", "next_tab", "previous_tab", "enter_folder", "parent_folder"):
            self.bind_class(tag, hotkeys[name], lambda _event, fn=commands[name]: fn())

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

    def save_config(self) -> None:
        if not self._ready:
            return
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
        refresh_defaults = {"auto_refresh": "true", "active_interval_ms": "2000",
                            "background_interval_ms": "10000", "network_interval_ms": "5000"}
        for key, value in refresh_defaults.items():
            if not self.config_data.has_option("refresh", key):
                self.config_data.set("refresh", key, value)
        temporary = self.ini_path.with_suffix(".ini.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                self.config_data.write(stream)
            temporary.replace(self.ini_path)
        except OSError:
            pass

    def close_app(self) -> None:
        if self._auto_refresh_job is not None:
            self.after_cancel(self._auto_refresh_job)
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
        header = ttk.Frame(self, padding=(5, 2))
        header.pack(fill="x")
        title = ttk.Label(header, text="Python File Commander", font=tkfont.nametofont("TkCaptionFont"),
                          cursor="hand2")
        title.pack(side="left", padx=(2, 10))
        title.bind("<Button-1>", lambda _event: self.show_help())
        files_button = tk.Menubutton(header, text="Files", font=menu_font, relief="flat", padx=6)
        files_button.pack(side="left")
        files = tk.Menu(files_button, tearoff=False, font=menu_font)
        files_button.configure(menu=files)
        files.add_command(label="Rename\tF2", command=self.rename)
        files.add_command(label="Preview in other panel\tF3", command=self.preview)
        files.add_command(label="Search\tF4", command=self.search)
        files.add_command(label="Compare\tF9", command=self.compare_selected)
        files.add_command(label="Copy Path\tF11", command=self.copy_paths)
        files.add_command(label="Change Dir\tF12", command=self.change_dir)
        files.add_separator()
        files.add_command(label="Exit", command=self.destroy)
        view_button = tk.Menubutton(header, text="View", font=menu_font, relief="flat", padx=6)
        view_button.pack(side="left")
        view = tk.Menu(view_button, tearoff=False, font=menu_font)
        view_button.configure(menu=view)
        visibility = tk.Menu(view, tearoff=False, font=menu_font)
        self.show_hidden_var = tk.BooleanVar(value=False)
        self.show_system_var = tk.BooleanVar(value=False)
        visibility.add_checkbutton(label="Show Hidden", variable=self.show_hidden_var,
                                   command=self.set_hidden_visibility)
        visibility.add_checkbutton(label="Show System", variable=self.show_system_var,
                                   command=self.set_system_visibility)
        view.add_cascade(label="File Visibility", menu=visibility)
        font_size = tk.Menu(view, tearoff=False, font=menu_font)
        for label, value in (("Small (100%)", "small"), ("Medium (150%)", "medium"),
                             ("Large (200%)", "large"), ("Huge (300%)", "huge")):
            font_size.add_radiobutton(label=label, value=value, variable=self.font_size_var,
                                      command=self.apply_font_size)
        view.add_cascade(label="Font Size", menu=font_size)
        self.files_menu_button = files_button
        self.view_menu_button = view_button
        self.files_menu = files
        self.view_menu = view
        self.config(menu="")

    def set_active(self, pane: FilePane) -> None:
        self.active = pane
        self.show_hidden_var.set(pane.show_hidden)
        self.show_system_var.set(pane.show_system)
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
        source = self.panes()[0]
        source.focus_file_list()
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
            "Selection and clipboard\n"
            "Ctrl+C / Ctrl+X / Ctrl+V  Copy / cut / paste with File Explorer\n"
            "Ctrl+A  Select all    Del  Permanently delete\n"
            "Ctrl+Shift+C  Copy selected or current path\n"
            "Ctrl+H  Toggle hidden files\n"
            "Alt+F / Alt+V  Open Files / View menu"
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
        button = self.files_menu_button if which == "files" else self.view_menu_button
        menu = self.files_menu if which == "files" else self.view_menu
        menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())
        return "break"

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
        return "break"

    def preview(self) -> None:
        source, target = self.panes()
        items = source.selected_paths()
        if items:
            target.show_preview(items[0])

    def search(self) -> None:
        source, _ = self.panes()
        query = simpledialog.askstring("Search", "File or folder name contains:", parent=self)
        if query:
            source.search(query)

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
        if items:
            self.clipboard_clear()
            self.clipboard_append("\n".join(str(item.resolve()) for item in items))
            self.update_idletasks()
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
                return
            operation = move_items if cut else copy_items
            operation(items, destination)
            if cut:
                clear_file_clipboard()
            self.refresh()
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

    def _run(self, verb: str, operation) -> None:
        source, target = self.panes()
        items = source.selected_paths()
        if not items:
            return
        if not messagebox.askyesno(verb, f"{verb} {len(items)} selected item(s) to:\n{target.path}?"):
            return
        try:
            operation(items, target.path)
            self.refresh()
        except OSError as exc:
            messagebox.showerror(f"{verb} failed", str(exc))

    def copy(self) -> None:
        self._run("Copy", copy_items)

    def move(self) -> None:
        self._run("Move", move_items)

    def delete(self) -> None:
        source, _ = self.panes()
        items = source.selected_paths()
        if items and messagebox.askyesno("Permanent delete", f"Permanently delete {len(items)} selected item(s)?"):
            try:
                delete_items(items); self.refresh()
            except OSError as exc:
                messagebox.showerror("Delete failed", str(exc))

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
