from __future__ import annotations

import csv
import difflib
import fnmatch
import hashlib
import os
import queue
import subprocess
import tempfile
import threading
import unicodedata
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont, messagebox, ttk

from .tabs import ChamferNotebook, color_scheme
from .tooltip import ToolTip, install_button_tooltips
from .i18n import retranslate_widgets, tr
from .archivefs import extract_archive_to


TEXT_SUFFIXES = {".txt", ".md", ".py", ".json", ".xml", ".html", ".htm", ".css", ".js",
                 ".ini", ".cfg", ".log", ".yaml", ".yml", ".sql", ".bat", ".ps1", ".c", ".h",
                 ".cpp", ".hpp", ".java", ".csv", ".tsv"}
TABLE_SUFFIXES = {".csv", ".tsv"}
ARCHIVE_SUFFIXES = {".zip", ".7z"}


def is_compare_archive(path: Path) -> bool:
    return path.is_file() and path.suffix.casefold() in ARCHIVE_SUFFIXES


def is_compare_container(path: Path) -> bool:
    return path.is_dir() or is_compare_archive(path)


def nested_source_label(source: Path, relative: str) -> str:
    """Present extracted archive members using their logical source path."""
    relative = str(relative).strip("/\\")
    if not relative:
        return str(source)
    separator = " :: " if source.suffix.casefold() in ARCHIVE_SUFFIXES else os.sep
    return f"{source}{separator}{relative}"


def extract_compare_archive(path: Path):
    """Extract ZIP/7z into an isolated temporary folder for read-only comparison."""
    workspace = tempfile.TemporaryDirectory(prefix="pfc-compare-")
    destination = Path(workspace.name)
    try:
        extract_archive_to(path, destination)
        return workspace, destination
    except Exception:
        workspace.cleanup()
        raise


def detect_compare_type(left: Path, right: Path) -> str:
    if is_compare_container(left) and is_compare_container(right):
        return "Folder"
    if left.suffix.casefold() in TABLE_SUFFIXES and right.suffix.casefold() in TABLE_SUFFIXES:
        return "Table"
    if left.suffix.casefold() in TEXT_SUFFIXES or right.suffix.casefold() in TEXT_SUFFIXES:
        return "Text"
    try:
        for path in (left, right):
            sample = path.read_bytes()[:4096]
            if b"\0" in sample:
                return "Binary"
            sample.decode("utf-8")
        return "Text"
    except (OSError, UnicodeDecodeError):
        return "Binary"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def text_files_equivalent(left: Path, right: Path) -> bool:
    """Compare visible text while ignoring non-printing representation details.

    This intentionally ignores BOMs, CRLF/LF choice, Unicode composition,
    zero-width/control characters, trailing spaces, and the final newline.  It
    does not ignore words, punctuation, indentation, or internal whitespace.
    """
    if left.suffix.casefold() not in TEXT_SUFFIXES or right.suffix.casefold() not in TEXT_SUFFIXES:
        return False
    try:
        if max(left.stat().st_size, right.stat().st_size) > 64 * 1024 * 1024:
            return False

        def normalized(path: Path) -> tuple[str, ...]:
            data = path.read_bytes()
            if data.startswith((b"\xff\xfe", b"\xfe\xff")):
                text = data.decode("utf-16")
            else:
                text = data.decode("utf-8-sig")
            text = unicodedata.normalize("NFC", text).replace("\u00a0", " ")
            text = "".join(character for character in text
                           if character in {"\n", "\r", "\t"} or
                           unicodedata.category(character) not in {"Cc", "Cf"})
            return tuple(line.rstrip(" \t") for line in text.splitlines())

        return normalized(left) == normalized(right)
    except (OSError, UnicodeDecodeError):
        return False


def aligned_text(left: str, right: str) -> tuple[list[tuple[int | None, str, int | None, str]], list[int]]:
    a, b = left.splitlines(), right.splitlines()
    rows: list[tuple[int | None, str, int | None, str]] = []
    differences: list[int] = []
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        length = max(a1 - a0, b1 - b0)
        for offset in range(length):
            has_left, has_right = a0 + offset < a1, b0 + offset < b1
            rows.append((a0 + offset + 1 if has_left else None, a[a0 + offset] if has_left else "",
                         b0 + offset + 1 if has_right else None, b[b0 + offset] if has_right else ""))
            if tag != "equal":
                differences.append(len(rows))
    return rows, differences


def compare_row_height(linespace: int, scale: float) -> int:
    """Keep compare rows readable at every PFC font scale."""
    return max(24, int(linespace) + max(8, round(6 * scale)))


class DifferenceMap(tk.Canvas):
    """Compact overview of differences; clicking a marker jumps to that row."""
    def __init__(self, master, command):
        super().__init__(master, width=38, background="#dce6ed", highlightthickness=1,
                         highlightbackground="#50697b", cursor="hand2", takefocus=True)
        self.command = command
        self.rows, self.total_rows, self.current_row = [], 1, None
        self.viewport = (0.0, 1.0)
        self.bind("<Configure>", lambda _event: self.redraw())
        self.bind("<Button-1>", self._click)
        self.palette = color_scheme("light")

    def apply_color_scheme(self, palette):
        self.palette = palette
        self.configure(background=palette["gutter"], highlightbackground=palette["border"])
        self.redraw()

    def set_rows(self, rows, total_rows, current_row=None):
        self.rows = list(rows)
        self.total_rows = max(1, int(total_rows))
        self.current_row = current_row
        self.redraw()

    def set_current(self, row):
        self.current_row = row
        self.redraw()

    def apply_scale(self, scale):
        self.configure(width=max(38, round(38 * scale)))

    def set_viewport(self, first, last):
        self.viewport = (max(0.0, float(first)), min(1.0, float(last)))
        self.redraw()

    def _y(self, row):
        height = max(8, self.winfo_height())
        return 3 + ((max(1, row) - 1) / max(1, self.total_rows - 1)) * (height - 6)

    def redraw(self):
        self.delete("all")
        width, height = max(8, self.winfo_width()), max(8, self.winfo_height())
        self.create_rectangle(3, 3, width - 4, height - 4,
                              fill=self.palette["content"], outline=self.palette["border"])
        marker_width = max(2, width - 9)
        blocks = []
        for row in sorted(self.rows):
            if blocks and row <= blocks[-1][1] + 1:
                blocks[-1] = (blocks[-1][0], row)
            else:
                blocks.append((row, row))
        for start, end in blocks:
            top, bottom = self._y(start), self._y(end)
            self.create_rectangle(5, top - 1, 5 + marker_width, max(top + 2, bottom + 1),
                                  fill="#e45a52", outline="")
        view_top = 3 + self.viewport[0] * (height - 6)
        view_bottom = 3 + self.viewport[1] * (height - 6)
        self.create_rectangle(2, view_top, width - 3, max(view_top + 5, view_bottom),
                              outline=self.palette["selection"], width=2)
        if self.current_row is not None:
            y = self._y(self.current_row)
            self.create_rectangle(2, y - 3, width - 3, y + 3,
                                  outline=self.palette["text"], width=2)

    def _click(self, event):
        if not self.rows:
            return "break"
        target = 1 + (event.y / max(1, self.winfo_height())) * max(1, self.total_rows - 1)
        self.command(min(self.rows, key=lambda row: abs(row - target)))
        return "break"


class SideBySideText(ttk.Frame):
    def __init__(self, master, left_lines, right_lines, differences, status_text="", status_factory=None,
                 left_title="", right_title="", marker_position="middle", marker_changed=None):
        super().__init__(master)
        self.all_left_lines, self.all_right_lines = list(left_lines), list(right_lines)
        self.all_differences = list(differences)
        self.differences = list(differences)
        self.diff_index = -1
        self.matches, self.match_index = [], -1
        self.search_var, self.case_var = tk.StringVar(), tk.BooleanVar(value=False)
        self.view_mode_var = tk.StringVar(value="all")
        self.marker_position_var = tk.StringVar(
            value=marker_position if marker_position in {"left", "middle", "right"} else "middle")
        self.marker_changed = marker_changed
        self.left_title, self.right_title = str(left_title), str(right_title)
        toolbar = ttk.Frame(self); toolbar.pack(fill="x")
        diff_row = ttk.Frame(toolbar); diff_row.pack(fill="x")
        self.status_factory = status_factory or (lambda: status_text)
        self.previous_button = ttk.Button(diff_row, text=f"F7 {tr('Diff <<')}", command=self.previous)
        self.previous_button.pack(side="left")
        self.next_button = ttk.Button(diff_row, text=f"F8 {tr('Diff >>')}", command=self.next)
        self.next_button.pack(side="left", padx=3)
        self.view_button = ttk.Menubutton(diff_row)
        self.view_menu = tk.Menu(self.view_button, tearoff=False)
        self.view_button.configure(menu=self.view_menu)
        self.view_button.pack(side="left", padx=(8, 0))
        self._build_view_menu()
        self.diff_status = ttk.Label(diff_row, text=self.status_factory())
        self.diff_status.pack(side="left", padx=10)
        self.marker_button = ttk.Menubutton(diff_row)
        self.marker_menu = tk.Menu(self.marker_button, tearoff=False)
        self.marker_button.configure(menu=self.marker_menu)
        self.marker_button.pack(side="right")
        self._build_marker_menu(); self._update_marker_button()
        find_row = ttk.Frame(toolbar); find_row.pack(fill="x", pady=(3, 2))
        ttk.Label(find_row, text=tr("Find:")).pack(side="left")
        self.search = ttk.Entry(find_row, textvariable=self.search_var)
        self.search.pack(side="left", fill="x", expand=True, padx=(3, 4))
        self.search.bind("<Return>", lambda _event: self.find_next())
        self.search.bind("<Shift-Return>", lambda _event: self.find_previous())
        ttk.Button(find_row, text=tr("Find Prev"), command=self.find_previous).pack(side="left")
        ttk.Button(find_row, text=tr("Find Next"), command=self.find_next).pack(side="left", padx=(3, 0))
        self.case_button = ttk.Button(find_row, command=self._toggle_case)
        self.case_button.pack(side="left", padx=(8, 0))
        self.find_status = ttk.Label(find_row, width=12, anchor="e")
        self.find_status.pack(side="right", padx=(8, 3))
        self._update_case_button()
        body = ttk.Frame(self); self.body = body
        body.pack(fill="both", expand=True, pady=(3, 0))
        body.rowconfigure(1, weight=1)
        self.left_frame = tk.Frame(body, background="#f5f8fa", highlightthickness=2,
                                   highlightbackground="#2d668f")
        self.right_frame = tk.Frame(body, background="#f5f8fa", highlightthickness=2,
                                    highlightbackground="#9b5d2e")
        self.left_frame.columnconfigure(1, weight=1); self.left_frame.rowconfigure(0, weight=1)
        self.right_frame.columnconfigure(1, weight=1); self.right_frame.rowconfigure(0, weight=1)
        self.left_path_label = tk.Label(body, anchor="w", background="#2d668f",
                                        foreground="white", font="TkHeadingFont", padx=6, pady=3)
        self.right_path_label = tk.Label(body, anchor="w", background="#9b5d2e",
                                         foreground="white", font="TkHeadingFont", padx=6, pady=3)
        self.left_path_label.configure(text=f"{tr('Left')}: {self.left_title}")
        self.right_path_label.configure(text=f"{tr('Right')}: {self.right_title}")
        self.map_header = tk.Label(body, text="↔", background="#263d4c", foreground="white",
                                   font="TkHeadingFont", pady=3)
        self.left = tk.Text(self.left_frame, wrap="none", undo=False, borderwidth=0)
        self.right = tk.Text(self.right_frame, wrap="none", undo=False, borderwidth=0)
        self.left_numbers = tk.Text(self.left_frame, width=6, wrap="none", undo=False, borderwidth=0,
                                    padx=4, takefocus=False, background="#e5ebef", foreground="#526575")
        self.right_numbers = tk.Text(self.right_frame, width=6, wrap="none", undo=False, borderwidth=0,
                                     padx=4, takefocus=False, background="#e5ebef", foreground="#526575")
        self.left_numbers.grid(row=0, column=0, sticky="ns")
        self.right_numbers.grid(row=0, column=0, sticky="ns")
        self.left.grid(row=0, column=1, sticky="nsew"); self.right.grid(row=0, column=1, sticky="nsew")
        left_x = ttk.Scrollbar(self.left_frame, orient="horizontal", command=self.left.xview)
        right_x = ttk.Scrollbar(self.right_frame, orient="horizontal", command=self.right.xview)
        left_x.grid(row=1, column=1, sticky="ew"); right_x.grid(row=1, column=1, sticky="ew")
        self.left.configure(xscrollcommand=left_x.set); self.right.configure(xscrollcommand=right_x.set)
        self.difference_map = DifferenceMap(body, self._jump_to_row)
        self.scroll = ttk.Scrollbar(body, orient="vertical", command=self._scroll)
        self.left.configure(yscrollcommand=self._left_scrolled)
        self.right.configure(yscrollcommand=self._right_scrolled)
        for widget in (self.left, self.right):
            widget.tag_configure("diff", background="#ffe1a8")
            widget.tag_configure("current", background="#ffb347")
            widget.tag_configure("match", background="#fff0a6")
            widget.tag_configure("current_match", background="#ff9f43")
            widget.bind("<MouseWheel>", self._mousewheel)
            widget.bind("<Button-4>", lambda _event: self._wheel_units(-3))
            widget.bind("<Button-5>", lambda _event: self._wheel_units(3))
        for widget in (self.left_numbers, self.right_numbers):
            widget.tag_configure("diff", background="#f2c08d", foreground="#35434d")
            widget.tag_configure("current", background="#e8843b", foreground="white")
            widget.bind("<MouseWheel>", self._mousewheel)
            widget.bind("<Button-4>", lambda _event: self._wheel_units(-3))
            widget.bind("<Button-5>", lambda _event: self._wheel_units(3))
        self._layout_marker()
        self.apply_color_scheme(getattr(master.winfo_toplevel(), "palette", color_scheme("light")))
        self.populate()

    def apply_color_scheme(self, palette):
        menu_options = {
            "background": palette["content"], "foreground": palette["text"],
            "activebackground": palette["selection"], "activeforeground": "#ffffff",
        }
        self.view_menu.configure(**menu_options); self.marker_menu.configure(**menu_options)
        self.left_frame.configure(background=palette["content"],
                                  highlightbackground=palette["left_header"])
        self.right_frame.configure(background=palette["content"],
                                   highlightbackground=palette["right_header"])
        self.left_path_label.configure(background=palette["left_header"], foreground="#ffffff")
        self.right_path_label.configure(background=palette["right_header"], foreground="#ffffff")
        self.map_header.configure(background=palette["map_header"], foreground="#ffffff")
        for widget in (self.left, self.right):
            widget.configure(background=palette["content"], foreground=palette["text"],
                             insertbackground=palette["text"],
                             selectbackground=palette["selection"], selectforeground="#ffffff")
            widget.tag_configure("diff", background=palette["diff"], foreground=palette["text"])
            widget.tag_configure("current", background=palette["current_diff"], foreground="#ffffff")
            widget.tag_configure("match", background=palette["match"], foreground=palette["text"])
            widget.tag_configure("current_match", background=palette["current_diff"], foreground="#ffffff")
        for widget in (self.left_numbers, self.right_numbers):
            widget.configure(background=palette["gutter"], foreground=palette["gutter_text"],
                             selectbackground=palette["selection"], selectforeground="#ffffff")
            widget.tag_configure("diff", background=palette["diff"], foreground=palette["gutter_text"])
            widget.tag_configure("current", background=palette["current_diff"], foreground="#ffffff")
        self.difference_map.apply_color_scheme(palette)

    def populate(self):
        only_differences = self.view_mode_var.get() == "differences"
        visible_rows = (self.all_differences if only_differences else
                        list(range(1, len(self.all_left_lines) + 1)))
        self.differences = (list(range(1, len(visible_rows) + 1)) if only_differences else
                            list(self.all_differences))
        self.diff_index = -1
        for widget, number_widget, lines in (
                (self.left, self.left_numbers, self.all_left_lines),
                (self.right, self.right_numbers, self.all_right_lines)):
            widget.configure(state="normal"); widget.delete("1.0", "end")
            number_widget.configure(state="normal"); number_widget.delete("1.0", "end")
            for output_row, source_row in enumerate(visible_rows, 1):
                item = lines[source_row - 1]
                source_number, line = item if isinstance(item, tuple) else (source_row, item)
                number_text = "" if source_number is None else str(source_number)
                tag = "diff" if output_row in self.differences else ""
                number_widget.insert("end", f"{number_text:>5}\n", tag)
                widget.insert("end", f" {line}\n", tag)
            widget.configure(state="disabled"); number_widget.configure(state="disabled")
        self.difference_map.set_rows(self.differences, len(visible_rows))
        self._build_view_menu()
        self.find_all()

    def _select_view_mode(self, value):
        self.view_mode_var.set(value); self.populate()

    def _build_view_menu(self):
        self.view_menu.delete(0, "end")
        selected = self.view_mode_var.get()
        for value, label in (("all", "All"), ("differences", "Differences only")):
            prefix = "● " if value == selected else "   "
            self.view_menu.add_command(label=prefix + tr(label),
                                       command=lambda mode=value: self._select_view_mode(mode))
        label = "All" if selected == "all" else "Differences only"
        self.view_button.configure(text=tr(label))

    def _build_marker_menu(self):
        self.marker_menu.delete(0, "end")
        selected = self.marker_position_var.get()
        for value, label in (("left", "Left"), ("middle", "Middle"), ("right", "Right")):
            prefix = "● " if value == selected else "   "
            self.marker_menu.add_command(label=prefix + tr(label),
                                         command=lambda position=value:
                                         self.set_marker_position(position, notify=True))

    def _update_marker_button(self):
        labels = {"left": "Left", "middle": "Middle", "right": "Right"}
        self.marker_button.configure(
            text=f"{tr('Map:')} {tr(labels.get(self.marker_position_var.get(), 'Middle'))}")

    def _toggle_case(self):
        self.case_var.set(not self.case_var.get()); self._update_case_button(); self.find_all()
        return "break"

    def _update_case_button(self):
        self.case_button.configure(
            text=f"{'✓' if self.case_var.get() else '–'} {tr('Case sensitive')}")

    def apply_scale(self, scale: float) -> None:
        self.difference_map.apply_scale(scale)
        padding = max(3, round(3 * scale))
        self.left_path_label.configure(padx=padding * 2, pady=padding)
        self.right_path_label.configure(padx=padding * 2, pady=padding)

    def set_marker_position(self, position: str, notify: bool = False) -> None:
        if position not in {"left", "middle", "right"}:
            position = "middle"
        self.marker_position_var.set(position)
        self._layout_marker()
        self._build_marker_menu(); self._update_marker_button()
        if notify and self.marker_changed is not None:
            self.marker_changed(position)

    def _marker_position_changed(self) -> None:
        self.set_marker_position(self.marker_position_var.get(), notify=True)

    def _layout_marker(self) -> None:
        for column in range(4):
            self.body.columnconfigure(column, weight=0, uniform="")
        position = self.marker_position_var.get()
        if position == "left":
            map_column, left_column, right_column = 0, 1, 2
        elif position == "right":
            left_column, right_column, map_column = 0, 1, 2
        else:
            left_column, map_column, right_column = 0, 1, 2
        for column in (left_column, right_column):
            self.body.columnconfigure(column, weight=1, uniform="compare")
        self.left_path_label.grid(row=0, column=left_column, sticky="ew")
        self.left_frame.grid(row=1, column=left_column, sticky="nsew")
        self.right_path_label.grid(row=0, column=right_column, sticky="ew")
        self.right_frame.grid(row=1, column=right_column, sticky="nsew")
        self.map_header.grid(row=0, column=map_column, sticky="ew", padx=4)
        self.difference_map.grid(row=1, column=map_column, sticky="ns", padx=4)
        self.scroll.grid(row=1, column=3, sticky="ns")

    def apply_language(self, old_language: str) -> None:
        retranslate_widgets(self, old_language)
        self.left_path_label.configure(text=f"{tr('Left')}: {self.left_title}")
        self.right_path_label.configure(text=f"{tr('Right')}: {self.right_title}")
        self.previous_button.configure(text=f"F7 {tr('Diff <<')}")
        self.next_button.configure(text=f"F8 {tr('Diff >>')}")
        self.diff_status.configure(text=self.status_factory())
        self._build_view_menu(); self._build_marker_menu(); self._update_marker_button()
        self._update_case_button()
        self.find_all()

    def focus_search(self):
        self.search.focus_set(); self.search.selection_range(0, "end"); return "break"

    def find_all(self):
        self.matches, self.match_index = [], -1
        needle = self.search_var.get()
        for widget in (self.left, self.right):
            widget.tag_remove("match", "1.0", "end"); widget.tag_remove("current_match", "1.0", "end")
            if not needle: continue
            start = "1.0"
            while True:
                found = widget.search(needle, start, stopindex="end", nocase=not self.case_var.get())
                if not found: break
                end = f"{found}+{len(needle)}c"
                self.matches.append((widget, found, end)); widget.tag_add("match", found, end); start = end
        self.find_status.configure(text=tr("{count} match(es)", count=len(self.matches)) if needle else "")

    def _find(self, direction):
        previous = self.match_index; self.find_all()
        if not self.matches: return "break"
        self.match_index = (previous + direction) % len(self.matches)
        for widget in (self.left, self.right): widget.tag_remove("current_match", "1.0", "end")
        widget, start, end = self.matches[self.match_index]
        widget.tag_add("current_match", start, end); widget.see(start)
        other = self.right if widget is self.left else self.left; other.yview_moveto(widget.yview()[0])
        self.find_status.configure(text=f"{self.match_index + 1}/{len(self.matches)}")
        return "break"

    def find_next(self): return self._find(1)
    def find_previous(self): return self._find(-1)

    def _scroll(self, *args):
        for widget in (self.left, self.left_numbers, self.right, self.right_numbers):
            widget.yview(*args)

    def _left_scrolled(self, first, last):
        self.scroll.set(first, last)
        self.difference_map.set_viewport(first, last)
        self.left_numbers.yview_moveto(first)
        if abs(self.right.yview()[0] - float(first)) > 0.0001:
            self.right.yview_moveto(first)
        self.right_numbers.yview_moveto(first)

    def _right_scrolled(self, first, last):
        self.scroll.set(first, last)
        self.difference_map.set_viewport(first, last)
        self.right_numbers.yview_moveto(first)
        if abs(self.left.yview()[0] - float(first)) > 0.0001:
            self.left.yview_moveto(first)
        self.left_numbers.yview_moveto(first)

    def _wheel_units(self, units):
        for widget in (self.left, self.left_numbers, self.right, self.right_numbers):
            widget.yview_scroll(units, "units")
        return "break"

    def _mousewheel(self, event):
        units = -int(event.delta / 120) if event.delta else 0
        return self._wheel_units(units)

    def _jump_to_row(self, line):
        if line not in self.differences:
            return
        self.diff_index = self.differences.index(line)
        self._show()

    def next(self):
        if self.differences:
            self.diff_index = (self.diff_index + 1) % len(self.differences); self._show()

    def previous(self):
        if self.differences:
            self.diff_index = (self.diff_index - 1) % len(self.differences); self._show()

    def _show(self):
        line = self.differences[self.diff_index]
        for widget in (self.left, self.left_numbers, self.right, self.right_numbers):
            widget.see(f"{line}.0")
            widget.tag_remove("current", "1.0", "end")
            widget.tag_add("current", f"{line}.0", f"{line}.end")
        self.difference_map.set_current(line)
        self.diff_status.configure(text=f"{self.diff_index + 1}/{len(self.differences)}")


class TextCompare(ttk.Frame):
    def __init__(self, master, left: Path, right: Path, marker_position="middle", marker_changed=None,
                 left_title=None, right_title=None):
        super().__init__(master)
        a = left.read_text(encoding="utf-8", errors="replace")
        b = right.read_text(encoding="utf-8", errors="replace")
        rows, differences = aligned_text(a, b)
        self.view = SideBySideText(
            self, [(row[0], row[1]) for row in rows], [(row[2], row[3]) for row in rows], differences,
            status_factory=lambda count=len(differences): tr("{count} different line(s)", count=count),
            left_title=left_title or left, right_title=right_title or right,
            marker_position=marker_position,
            marker_changed=marker_changed)
        self.view.pack(fill="both", expand=True)

    def apply_language(self, old_language: str) -> None:
        self.view.apply_language(old_language)

    def apply_scale(self, scale: float) -> None:
        self.view.apply_scale(scale)


class BinaryCompare(ttk.Frame):
    LIMIT = 256 * 1024

    def __init__(self, master, left: Path, right: Path, marker_position="middle", marker_changed=None,
                 left_title=None, right_title=None):
        super().__init__(master)
        a, b = left.read_bytes()[:self.LIMIT], right.read_bytes()[:self.LIMIT]
        length = max(len(a), len(b)); different_offsets = []
        left_lines, right_lines, diff_lines = [], [], []
        for offset in range(0, length, 16):
            ca, cb = a[offset:offset + 16], b[offset:offset + 16]
            if ca != cb:
                different_offsets.extend(offset + index for index in range(max(len(ca), len(cb)))
                                         if (ca[index:index + 1] != cb[index:index + 1]))
                diff_lines.append(len(left_lines) + 1)
            def render(chunk):
                hexdump = " ".join(f"{byte:02X}" for byte in chunk)
                text = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
                return f"{offset:08X}  {hexdump:<47}  {text}"
            left_lines.append(render(ca)); right_lines.append(render(cb))
        identical = file_hash(left) == file_hash(right)
        first_offset = f"0x{different_offsets[0]:X}" if different_offsets else None
        status_factory = lambda: tr(
            "SHA-256: {result}; first offset: {offset}",
            result=tr("identical") if identical else tr("different"),
            offset=first_offset or tr("none"))
        self.view = SideBySideText(self, left_lines, right_lines, diff_lines,
                                   status_factory=status_factory,
                                   left_title=left_title or left, right_title=right_title or right,
                                   marker_position=marker_position, marker_changed=marker_changed)
        self.view.pack(fill="both", expand=True)

    def apply_language(self, old_language: str) -> None:
        self.view.apply_language(old_language)

    def apply_scale(self, scale: float) -> None:
        self.view.apply_scale(scale)


def folder_rows(left: Path, right: Path, recursive=True, masks="*", by_content=False,
                ignore_invisible_text=False, cancelled=lambda: False):
    patterns = [item.strip() for item in masks.split(";") if item.strip()] or ["*"]
    def collect(root):
        if recursive:
            def paths():
                for folder, directories, filenames in os.walk(root, topdown=True,
                                                                onerror=lambda _error: None):
                    directories[:] = [name for name in directories
                                      if name.casefold() not in {".git", ".svn"}]
                    base = Path(folder)
                    yield from (base / name for name in directories)
                    yield from (base / name for name in filenames)
            iterator = paths()
        else:
            iterator = root.iterdir()
        result = {}
        for path in iterator:
            if cancelled():
                break
            try:
                relative_path = path.relative_to(root)
            except ValueError:
                continue
            if any(part.casefold() in {".git", ".svn"} for part in relative_path.parts):
                continue
            relative = str(relative_path)
            if path.is_dir() or any(fnmatch.fnmatch(path.name.casefold(), pattern.casefold())
                                    for pattern in patterns):
                result[relative.casefold()] = path
        return result
    left_items, right_items = collect(left), collect(right)
    for key in sorted(left_items.keys() | right_items.keys()):
        if cancelled():
            return
        a, b = left_items.get(key), right_items.get(key)
        display = str((a.relative_to(left) if a else b.relative_to(right)))
        try:
            if a is None: status = "Right only"
            elif b is None: status = "Left only"
            elif a.is_dir() != b.is_dir(): status = "Type mismatch"
            elif a.is_dir(): status = "Identical"
            else:
                a_stat, b_stat = a.stat(), b.stat()
                if ignore_invisible_text and text_files_equivalent(a, b):
                    status = "Identical"
                elif a_stat.st_size != b_stat.st_size:
                    status = "Different"
                elif by_content and file_hash(a) == file_hash(b):
                    status = "Identical"
                elif by_content:
                    status = "Left newer" if a_stat.st_mtime_ns > b_stat.st_mtime_ns else (
                        "Right newer" if b_stat.st_mtime_ns > a_stat.st_mtime_ns else "Different")
                elif a_stat.st_mtime_ns == b_stat.st_mtime_ns:
                    status = "Identical"
                else:
                    status = "Left newer" if a_stat.st_mtime_ns > b_stat.st_mtime_ns else "Right newer"
        except OSError:
            status = "Unknown"
        yield status, display, a, b


class SyncPlanDialog(tk.Toplevel):
    def __init__(self, parent, plans):
        super().__init__(parent)
        self.result = False
        self.title(tr("Safe Sync — Dry Run"))
        self.geometry("1000x560"); self.minsize(680, 380); self.transient(parent)
        ttk.Label(self, text=tr("Review all {count} copy operation(s)", count=len(plans)),
                  font="TkHeadingFont", padding=(8, 8, 8, 2)).pack(anchor="w")
        ttk.Label(self, text=tr("Copy only — no files or folders will be deleted."),
                  padding=(8, 0, 8, 6)).pack(anchor="w")
        self.tree = ttk.Treeview(self, columns=("source", "destination"), show="headings")
        self.tree.heading("source", text=tr("Source")); self.tree.heading("destination", text=tr("Destination"))
        self.tree.column("source", width=470); self.tree.column("destination", width=470)
        for source, target in plans:
            self.tree.insert("", "end", values=(str(source), str(target)))
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y", padx=(0, 8)); self.tree.pack(fill="both", expand=True, padx=(8, 0))
        buttons = ttk.Frame(self, padding=8); buttons.pack(fill="x")
        ttk.Button(buttons, text=tr("Cancel"), command=self.cancel).pack(side="right")
        execute = ttk.Button(buttons, text=tr("Execute Copy Plan"), command=self.execute)
        execute.pack(side="right", padx=(0, 4))
        self.bind("<Escape>", lambda _event: self.cancel())
        self.bind("<Control-Return>", lambda _event: self.execute())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.grab_set(); self.lift(); self.focus_force(); execute.focus_set()

    def execute(self):
        self.result = True; self.destroy()

    def cancel(self):
        self.result = False; self.destroy()

    @classmethod
    def ask(cls, parent, plans):
        dialog = cls(parent, plans); parent.wait_window(dialog); return dialog.result


class _FolderCompareLogic(ttk.Frame):
    DIFF_FILTERS = {
        "all": None,
        "differences": {"Different", "Type mismatch", "Unknown", "Left newer", "Right newer",
                        "Left only", "Right only"},
        "no_orphans": {"Identical", "Different", "Type mismatch", "Unknown", "Left newer", "Right newer"},
        "differences_no_orphans": {"Different", "Type mismatch", "Unknown", "Left newer", "Right newer"},
        "orphans": {"Left only", "Right only"},
        "left_newer": {"Left newer"},
        "right_newer": {"Right newer"},
        "left_newer_orphans": {"Left newer", "Left only"},
        "right_newer_orphans": {"Right newer", "Right only"},
        "left_orphans": {"Left only"},
        "right_orphans": {"Right only"},
    }
    DIFF_LABELS = {
        "all": "Show All", "differences": "Show Differences",
        "no_orphans": "Show No Orphans",
        "differences_no_orphans": "Show Differences but No Orphans",
        "orphans": "Show Orphans", "left_newer": "Show Left Newer",
        "right_newer": "Show Right Newer",
        "left_newer_orphans": "Show Left Newer and Left Orphans",
        "right_newer_orphans": "Show Right Newer and Right Orphans",
        "left_orphans": "Show Left Orphans", "right_orphans": "Show Right Orphans",
    }

    def __init__(self, master, left: Path, right: Path, open_detail, sync_executor=None,
                 left_label=None, right_label=None, left_read_only=False, right_read_only=False):
        super().__init__(master)
        self.left_root, self.right_root = left, right
        self.left_base_root, self.right_base_root = left, right
        self.left_label = Path(left_label) if left_label is not None else left
        self.right_label = Path(right_label) if right_label is not None else right
        self.left_read_only, self.right_read_only = left_read_only, right_read_only
        self.open_detail, self.sync_executor = open_detail, sync_executor
        self.rows, self.actions, self.item_paths, self.item_keys = [], {}, {}, {}
        self._expand_state = True
        self.matches, self.match_index = [], -1
        self.difference_items, self.difference_index = [], -1
        self._scan_queue, self._cancel_event, self._scanning = queue.Queue(), threading.Event(), False
        self.sort_column, self.sort_reverse = "left_path", False
        paths = ttk.Frame(self); paths.pack(fill="x", pady=(2, 3))
        paths.columnconfigure(0, weight=1, uniform="folder-side")
        paths.columnconfigure(2, weight=1, uniform="folder-side")
        self.left_path_label = tk.Label(paths, text=f"{tr('Left')}: {self._base_label('left')}", anchor="w",
                                        background="#2d668f", foreground="white",
                                        font="TkHeadingFont", padx=6, pady=3)
        self.left_path_label.grid(row=0, column=0, sticky="ew")
        self.path_divider = tk.Label(paths, text="↔", background="#263d4c", foreground="white",
                                     font="TkHeadingFont", padx=10, pady=3)
        self.path_divider.grid(row=0, column=1, sticky="ns")
        self.right_path_label = tk.Label(paths, text=f"{tr('Right')}: {self._base_label('right')}", anchor="w",
                                         background="#9b5d2e", foreground="white",
                                         font="TkHeadingFont", padx=6, pady=3)
        self.right_path_label.grid(row=0, column=2, sticky="ew")
        bar = ttk.Frame(self); bar.pack(fill="x")
        ttk.Label(bar, text=tr("Mask:")).pack(side="left")
        self.mask_var = tk.StringVar(value="*")
        ttk.Entry(bar, textvariable=self.mask_var, width=20).pack(side="left", fill="x", expand=True, padx=(3, 8))
        ttk.Button(bar, text=tr("Compare"), command=self.start_scan).pack(side="left", padx=(0, 2))
        ttk.Button(bar, text=tr("Cancel"), command=self.cancel_scan).pack(side="left")
        options = ttk.Frame(self); options.pack(fill="x", pady=(2, 1))
        self.recursive_var = tk.BooleanVar(value=True)
        # Archive timestamps are often rounded or regenerated.  Compare archive
        # contents by bytes by default so a repacked folder is not reported as
        # different solely because of container metadata.
        self.content_var = tk.BooleanVar(value=self.left_read_only or self.right_read_only)
        self.text_equivalent_var = tk.BooleanVar(value=True)
        self.view_mode_var = tk.StringVar(value="all")
        ttk.Checkbutton(options, text=tr("Recursive"), variable=self.recursive_var).pack(side="left")
        ttk.Checkbutton(options, text=tr("By content"), variable=self.content_var).pack(side="left", padx=(5, 0))
        ttk.Checkbutton(options, text=tr("Text equivalent"),
                        variable=self.text_equivalent_var).pack(side="left", padx=(5, 0))
        self.diff_button = ttk.Menubutton(options, text=tr("All"))
        self.diff_menu = tk.Menu(self.diff_button, tearoff=False)
        self.diff_button.configure(menu=self.diff_menu)
        self.diff_button.pack(side="left", padx=(8, 0))
        self._build_diff_menu()
        folder_tools = ttk.Frame(self); folder_tools.pack(fill="x", pady=(1, 1))
        ttk.Button(folder_tools, text=tr("Expand All"), command=self.expand_all).pack(side="left")
        ttk.Button(folder_tools, text=tr("Collapse All"), command=self.collapse_all).pack(side="left", padx=(3, 0))
        ttk.Button(folder_tools, text=tr("Set Base Folder"), command=self.set_base_folder).pack(side="left", padx=(8, 0))
        ttk.Button(folder_tools, text=tr("Swap Sides"), command=self.swap_sides).pack(side="left", padx=(3, 0))
        navigation = ttk.Frame(self); navigation.pack(fill="x", pady=(1, 2))
        self.previous_button = ttk.Button(navigation, text=f"F7 {tr('Diff <<')}", command=self.previous)
        self.previous_button.pack(side="left")
        self.next_button = ttk.Button(navigation, text=f"F8 {tr('Diff >>')}", command=self.next)
        self.next_button.pack(side="left", padx=3)
        self.diff_status = ttk.Label(navigation); self.diff_status.pack(side="left", padx=5)
        self.search_var, self.case_var = tk.StringVar(), tk.BooleanVar(value=False)
        find_row = ttk.Frame(self); find_row.pack(fill="x", pady=(3, 2))
        ttk.Label(find_row, text=tr("Find:")).pack(side="left")
        self.search = ttk.Entry(find_row, textvariable=self.search_var)
        self.search.pack(side="left", fill="x", expand=True, padx=(3, 4))
        self.search.bind("<Return>", lambda _event: self.find_next())
        self.search.bind("<Shift-Return>", lambda _event: self.find_previous())
        self.find_status = ttk.Label(find_row, width=10, anchor="e"); self.find_status.pack(side="right", padx=4)
        find_actions = ttk.Frame(self); find_actions.pack(fill="x", pady=(0, 2))
        ttk.Button(find_actions, text=tr("Find Prev"), command=self.find_previous).pack(side="left")
        ttk.Button(find_actions, text=tr("Find Next"), command=self.find_next).pack(side="left", padx=(3, 0))
        ttk.Checkbutton(find_actions, text=tr("Case sensitive"), variable=self.case_var,
                        command=self.find_all).pack(side="left", padx=(8, 0))
        actions = ttk.Frame(self); actions.pack(fill="x", pady=(0, 3))
        ttk.Button(actions, text=f"Ctrl+→ {tr('Copy')} →", command=lambda: self.set_action("right")).pack(side="left")
        ttk.Button(actions, text=f"Ctrl+← ← {tr('Copy')}", command=lambda: self.set_action("left")).pack(side="left", padx=3)
        ttk.Button(actions, text=tr("Space Skip"), command=lambda: self.set_action("skip")).pack(side="left")
        sync_row = ttk.Frame(self); sync_row.pack(fill="x", pady=(0, 3))
        ttk.Button(sync_row, text=tr("Dry Run && Sync"), command=self.dry_run).pack(side="left")
        ttk.Label(sync_row, text=tr("Copy only — no automatic delete")).pack(side="left", padx=(8, 0))
        self.scan_status = ttk.Label(sync_row, text=tr("Ready"), anchor="e")
        self.scan_status.pack(side="right", fill="x", expand=True, padx=8)
        tree_area = ttk.Frame(self); tree_area.pack(fill="both", expand=True)
        tree_area.columnconfigure(0, weight=1); tree_area.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(tree_area, columns=("action", "left_path", "left_detail", "status",
                                                     "right_path", "right_detail"),
                                 show=("tree", "headings"), selectmode="extended",
                                 style="PFCCompare.Treeview")
        headings = {
            "action": tr("Action"), "left_path": tr("Left"),
            "left_detail": f"{tr('Size')} / {tr('Modified')}", "status": tr("Status"),
            "right_path": tr("Right"), "right_detail": f"{tr('Size')} / {tr('Modified')}",
        }
        self._column_widths = {"action": 65, "left_path": 300, "left_detail": 190,
                               "status": 130, "right_path": 300, "right_detail": 190}
        for col, width in self._column_widths.items():
            self.tree.heading(col, text=headings[col], command=lambda value=col: self.change_sort(value))
            self.tree.column(col, width=width, minwidth=50,
                             stretch=col in {"left_path", "right_path"},
                             anchor="center" if col in {"action", "status"} else "w")
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=32, minwidth=24, stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree_y_scroll = ttk.Scrollbar(tree_area, orient="vertical", command=self.tree.yview)
        self.tree_x_scroll = ttk.Scrollbar(tree_area, orient="horizontal", command=self.tree.xview)
        self.tree_y_scroll.grid(row=0, column=1, sticky="ns")
        self.tree_x_scroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=self.tree_y_scroll.set, xscrollcommand=self.tree_x_scroll.set)
        self.tree.tag_configure("find_match", background="#fff0a6")
        self.tree.tag_configure("current_match", background="#ff9f43")
        self.tree.tag_configure("different", foreground="#a00000")
        self.tree.tag_configure("left", foreground="#006c3b")
        self.tree.tag_configure("right", foreground="#005ca8")
        self.tree.tag_configure("identical", foreground="#555555")
        self.tree.bind("<Double-1>", self._open)
        self.tree.bind("<Return>", self._open)
        self.tree.bind("<Control-Right>", lambda _e: self.set_action("right"))
        self.tree.bind("<Control-Left>", lambda _e: self.set_action("left"))
        self.tree.bind("<space>", lambda _e: self.set_action("skip"))
        self.apply_scale(1.0)
        self.apply_color_scheme(getattr(master.winfo_toplevel(), "palette", color_scheme("light")))
        self.start_scan()

    def _base_label(self, side):
        root = self.left_root if side == "left" else self.right_root
        initial = self.left_base_root if side == "left" else self.right_base_root
        label = self.left_label if side == "left" else self.right_label
        try:
            relative = root.relative_to(initial)
        except ValueError:
            relative = Path()
        if relative == Path("."):
            return str(label)
        separator = " :: " if is_compare_archive(label) else os.sep
        return f"{label}{separator}{relative}"

    def _build_diff_menu(self):
        self.diff_menu.delete(0, "end")
        for key in self.DIFF_FILTERS:
            self.diff_menu.add_radiobutton(label=tr(self.DIFF_LABELS[key]), value=key,
                                           variable=self.view_mode_var,
                                           command=self._set_diff_filter)
        self._update_diff_button()

    def _update_diff_button(self):
        key = self.view_mode_var.get()
        self.diff_button.configure(text=f"{tr('Diffs')}: {tr(self.DIFF_LABELS.get(key, 'Show All'))}")

    def _set_diff_filter(self):
        self._update_diff_button()
        self.populate()

    def expand_all(self):
        self._expand_state = True
        for iid in self.tree.get_children(""):
            self._set_open_recursive(iid, True)
        return "break"

    def collapse_all(self):
        self._expand_state = False
        for iid in self.tree.get_children(""):
            self._set_open_recursive(iid, False)
        return "break"

    def _set_open_recursive(self, iid, opened):
        self.tree.item(iid, open=opened)
        for child in self.tree.get_children(iid):
            self._set_open_recursive(child, opened)

    def _all_tree_items(self, parent=""):
        for iid in self.tree.get_children(parent):
            yield iid
            yield from self._all_tree_items(iid)

    def set_base_folder(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(tr("Set Base Folder"), tr("Select a folder row first."), parent=self)
            return "break"
        left, right = self.item_paths.get(selected[0], (None, None))
        changed = False
        if left is not None and left.is_dir():
            self.left_root = left; changed = True
        if right is not None and right.is_dir():
            self.right_root = right; changed = True
        if not changed:
            messagebox.showinfo(tr("Set Base Folder"), tr("The selected row is not a folder."), parent=self)
            return "break"
        self._update_path_labels()
        self.start_scan()
        return "break"

    def swap_sides(self):
        if self._scanning:
            self.cancel_scan()
        self.left_root, self.right_root = self.right_root, self.left_root
        self.left_base_root, self.right_base_root = self.right_base_root, self.left_base_root
        self.left_label, self.right_label = self.right_label, self.left_label
        self.left_read_only, self.right_read_only = self.right_read_only, self.left_read_only
        self.actions = {}
        self._update_path_labels()
        self.start_scan()
        return "break"

    def _update_path_labels(self):
        self.left_path_label.configure(text=f"{tr('Left')}: {self._base_label('left')}")
        self.right_path_label.configure(text=f"{tr('Right')}: {self._base_label('right')}")

    def apply_color_scheme(self, palette):
        self.left_path_label.configure(background=palette["left_header"], foreground="#ffffff")
        self.right_path_label.configure(background=palette["right_header"], foreground="#ffffff")
        self.path_divider.configure(background=palette["map_header"], foreground="#ffffff")
        self.tree.tag_configure("find_match", background=palette["match"], foreground=palette["text"])
        self.tree.tag_configure("current_match", background=palette["current_diff"], foreground="#ffffff")
        self.tree.tag_configure("different", foreground="#ff7770" if palette["window"] == "#20262c" else "#a00000")
        self.tree.tag_configure("left", foreground="#73d6a1" if palette["window"] == "#20262c" else "#006c3b")
        self.tree.tag_configure("right", foreground="#73bfff" if palette["window"] == "#20262c" else "#005ca8")
        self.tree.tag_configure("identical", foreground=palette["muted"])
        self.diff_menu.configure(background=palette["menu"], foreground=palette["menu_text"],
                                 activebackground=palette["menu_active"],
                                 activeforeground=palette["menu_active_text"])
    def apply_scale(self, scale: float) -> None:
        style = ttk.Style(self)
        linespace = tkfont.nametofont("TkDefaultFont").metrics("linespace")
        style.configure("PFCCompare.Treeview", font="TkDefaultFont",
                        rowheight=compare_row_height(linespace, scale))
        style.configure("PFCCompare.Treeview.Heading", font="TkHeadingFont")
        for column, width in self._column_widths.items():
            self.tree.column(column, width=max(50, round(width * scale)))
        padding = max(3, round(3 * scale))
        for label in (self.left_path_label, self.right_path_label):
            label.configure(padx=padding * 2, pady=padding)
        self.path_divider.configure(padx=max(8, round(8 * scale)), pady=padding)

    def apply_language(self, old_language: str) -> None:
        selected_keys = {self.item_keys.get(iid) for iid in self.tree.selection()}
        retranslate_widgets(self, old_language)
        self.previous_button.configure(text=f"F7 {tr('Diff <<')}")
        self.next_button.configure(text=f"F8 {tr('Diff >>')}")
        self._update_path_labels()
        self._build_diff_menu()
        labels = {"action": tr("Action"), "left_path": tr("Left"),
                  "left_detail": f"{tr('Size')} / {tr('Modified')}", "status": tr("Status"),
                  "right_path": tr("Right"), "right_detail": f"{tr('Size')} / {tr('Modified')}"}
        for column in ("action", "left_path", "left_detail", "status", "right_path", "right_detail"):
            marker = (" ▲" if not self.sort_reverse else " ▼") if column == self.sort_column else ""
            self.tree.heading(column, text=labels[column] + marker)
        self.populate()
        for iid in self._all_tree_items():
            if self.item_keys.get(iid) in selected_keys:
                self.tree.selection_add(iid)
        if self._scanning:
            self.scan_status.configure(text=tr("Scanning…  Esc cancels"))
        elif self.rows:
            different = sum(1 for row in self.rows if row[0] != "Identical")
            self.scan_status.configure(text=tr("{count} item(s), {different} different",
                                                count=len(self.rows), different=different))

    @staticmethod
    def _detail(path):
        if path is None: return "—"
        try:
            if path.is_dir(): return "<DIR>"
            stat = path.stat()
            return f"{stat.st_size:,} B  {datetime.fromtimestamp(stat.st_mtime):%Y-%m-%d %H:%M}"
        except OSError:
            return "?"

    def start_scan(self):
        if self._scanning:
            self._cancel_event.set()
        self._cancel_event = threading.Event(); self._scanning = True
        self.scan_status.configure(text=tr("Scanning…  Esc cancels"))
        recursive, masks, by_content = self.recursive_var.get(), self.mask_var.get(), self.content_var.get()
        text_equivalent = self.text_equivalent_var.get()
        cancel = self._cancel_event
        def worker():
            try:
                rows = list(folder_rows(self.left_root, self.right_root, recursive, masks, by_content,
                                        text_equivalent, cancel.is_set))
                self._scan_queue.put((cancel, rows, None))
            except OSError as exc:
                self._scan_queue.put((cancel, [], str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self.after(60, self._poll_scan)
        return "break"

    def _poll_scan(self):
        try:
            cancel, rows, error = self._scan_queue.get_nowait()
        except queue.Empty:
            if self.winfo_exists() and self._scanning: self.after(60, self._poll_scan)
            return
        if cancel is not self._cancel_event:
            if self.winfo_exists() and self._scanning: self.after(60, self._poll_scan)
            return
        self._scanning = False
        if cancel.is_set():
            self.scan_status.configure(text=tr("Scan cancelled"))
            return
        if error:
            self.scan_status.configure(text=tr("Scan failed"))
            messagebox.showerror(tr("Folder Compare"), error, parent=self)
            return
        self.rows, self.actions = rows, {}
        different = sum(status != "Identical" for status, *_rest in rows)
        self.scan_status.configure(text=tr("{count} item(s), {different} different",
                                           count=len(rows), different=different))
        self.populate()
        children = tuple(self._all_tree_items())
        if children:
            self.tree.selection_set(children[0]); self.tree.focus(children[0]); self.tree.see(children[0])
        self.tree.focus_set()

    def cancel_scan(self):
        if not self._scanning:
            return False
        self._cancel_event.set(); self._scanning = False
        self.scan_status.configure(text=tr("Scan cancelled"))
        return True

    def change_sort(self, column):
        selected_keys = {self.item_keys.get(iid) for iid in self.tree.selection()}
        self.sort_reverse = not self.sort_reverse if column == self.sort_column else False
        self.sort_column = column
        labels = {"action": tr("Action"), "left_path": tr("Left"),
                  "left_detail": f"{tr('Size')} / {tr('Modified')}", "status": tr("Status"),
                  "right_path": tr("Right"), "right_detail": f"{tr('Size')} / {tr('Modified')}"}
        for value in ("action", "left_path", "left_detail", "status", "right_path", "right_detail"):
            marker = (" ▼" if self.sort_reverse else " ▲") if value == column else ""
            self.tree.heading(value, text=labels[value] + marker)
        self.populate()
        for iid in self._all_tree_items():
            if self.item_keys.get(iid) in selected_keys:
                self.tree.selection_add(iid); self.tree.focus(iid); self.tree.see(iid)
        self.tree.focus_set()

    def populate(self):
        self.tree.delete(*self.tree.get_children())
        self.item_paths, self.item_keys = {}, {}
        self.difference_items, self.difference_index = [], -1
        action_label = {"right": "→", "left": "←", "skip": tr("Skip")}
        allowed = self.DIFF_FILTERS.get(self.view_mode_var.get())
        initially_visible = list(self.rows) if allowed is None else [row for row in self.rows if row[0] in allowed]
        rows_by_key = {row[1].casefold(): row for row in self.rows}
        needed = {row[1].casefold() for row in initially_visible}
        for _status, relative, _left, _right in initially_visible:
            parent = Path(relative).parent
            while parent != Path("."):
                key = str(parent).casefold()
                if key in rows_by_key:
                    needed.add(key)
                parent = parent.parent
        visible = [row for row in self.rows if row[1].casefold() in needed]
        if self.sort_column == "action":
            visible.sort(key=lambda row: self.actions.get(row[1], ""), reverse=self.sort_reverse)
        elif self.sort_column in {"left_detail", "right_detail"}:
            path_index = 2 if self.sort_column == "left_detail" else 3
            def metadata_key(row):
                path = row[path_index]
                if path is None: return (0, 0, 0)
                try:
                    stat = path.stat(); return (2 if path.is_dir() else 1, stat.st_size, stat.st_mtime_ns)
                except OSError:
                    return (0, 0, 0)
            visible.sort(key=metadata_key, reverse=self.sort_reverse)
        elif self.sort_column == "status":
            visible.sort(key=lambda row: row[0].casefold(), reverse=self.sort_reverse)
        else:
            visible.sort(key=lambda row: row[1].casefold(), reverse=self.sort_reverse)
        visible.sort(key=lambda row: len(Path(row[1]).parts))
        item_ids = {}
        for status, path, left, right in visible:
            tag = "left" if status in {"Left only", "Left newer"} else (
                "right" if status in {"Right only", "Right newer"} else (
                    "identical" if status == "Identical" else "different"))
            parent_key = str(Path(path).parent).casefold()
            parent_iid = item_ids.get(parent_key, "")
            iid = self.tree.insert(parent_iid, "end", text="", open=self._expand_state,
                values=(action_label.get(self.actions.get(path), ""),
                path if left is not None else "", self._detail(left), tr(status),
                path if right is not None else "", self._detail(right)), tags=(tag,))
            item_ids[path.casefold()] = iid
            self.item_paths[iid] = (left, right)
            self.item_keys[iid] = path
            if status != "Identical":
                self.difference_items.append(iid)
        self.diff_status.configure(text=f"0/{len(self.difference_items)}")
        self.find_all()

    def _difference(self, direction):
        if not self.difference_items:
            return "break"
        self.difference_index = (self.difference_index + direction) % len(self.difference_items)
        iid = self.difference_items[self.difference_index]
        self.tree.selection_set(iid); self.tree.focus(iid); self.tree.see(iid); self.tree.focus_set()
        self.diff_status.configure(text=f"{self.difference_index + 1}/{len(self.difference_items)}")
        return "break"

    def next(self): return self._difference(1)
    def previous(self): return self._difference(-1)

    def set_action(self, action):
        selected = self.tree.selection()
        selected_keys = {self.item_keys.get(iid) for iid in selected}
        for iid in selected:
            left, right = self.item_paths.get(iid, (None, None)); key = self.item_keys.get(iid)
            if key is None: continue
            if action == "right" and left is not None and not self.right_read_only:
                self.actions[key] = action
            elif action == "left" and right is not None and not self.left_read_only:
                self.actions[key] = action
            elif action == "skip":
                self.actions[key] = action
        self.populate()
        for iid in self._all_tree_items():
            if self.item_keys.get(iid) in selected_keys:
                self.tree.selection_add(iid)
        return "break"

    def _plans(self):
        plans = []
        by_key = {path: (left, right) for _status, path, left, right in self.rows}
        for key, action in self.actions.items():
            left, right = by_key.get(key, (None, None))
            if action == "right" and left is not None:
                plans.append((left, self.right_root / key))
            elif action == "left" and right is not None:
                plans.append((right, self.left_root / key))
        plans.sort(key=lambda item: len(item[1].parts))
        filtered = []
        for source, target in plans:
            if any(parent_source.is_dir() and parent_target in target.parents
                   for parent_source, parent_target in filtered):
                continue
            filtered.append((source, target))
        return filtered

    def dry_run(self):
        plans = self._plans()
        if not plans:
            messagebox.showinfo(tr("Safe Sync"), tr("Select rows and assign Copy → or ← Copy first."), parent=self)
            return "break"
        if not SyncPlanDialog.ask(self, plans):
            return "break"
        if self.sync_executor is not None:
            self.sync_executor(plans)
            self.start_scan()
        return "break"

    def focus_search(self):
        self.search.focus_set(); self.search.selection_range(0, "end"); return "break"

    def find_all(self):
        self.matches, self.match_index = [], -1; needle = self.search_var.get()
        for iid in self._all_tree_items():
            base = next((tag for tag in self.tree.item(iid, "tags")
                         if tag in {"left", "right", "different", "identical"}), "different")
            haystack = " ".join(str(value) for value in self.tree.item(iid, "values"))
            matched = needle in haystack if self.case_var.get() else needle.casefold() in haystack.casefold()
            if needle and matched:
                self.matches.append(iid); self.tree.item(iid, tags=(base, "find_match"))
            else:
                self.tree.item(iid, tags=(base,))
        self.find_status.configure(text=tr("{count} match(es)", count=len(self.matches)) if needle else "")

    def _find(self, direction):
        previous = self.match_index; self.find_all()
        if not self.matches: return "break"
        self.match_index = (previous + direction) % len(self.matches); iid = self.matches[self.match_index]
        self.tree.item(iid, tags=(*self.tree.item(iid, "tags"), "current_match"))
        self.tree.selection_set(iid); self.tree.focus(iid); self.tree.see(iid)
        self.find_status.configure(text=f"{self.match_index + 1}/{len(self.matches)}"); return "break"

    def find_next(self): return self._find(1)
    def find_previous(self): return self._find(-1)

    def _open(self, _event=None):
        selected = self.tree.selection()
        if selected:
            left, right = self.item_paths.get(selected[0], (None, None))
            if left and right and left.is_file() and right.is_file(): self.open_detail(left, right)


class FolderCompare(_FolderCompareLogic):
    """Folder/archive comparison using the same two-pane + mapper layout as file compare."""

    def __init__(self, master, left: Path, right: Path, open_detail, sync_executor=None,
                 left_label=None, right_label=None, left_read_only=False, right_read_only=False,
                 marker_position="middle", marker_changed=None):
        ttk.Frame.__init__(self, master)
        self.view = self
        self.left_root, self.right_root = left, right
        self.left_base_root, self.right_base_root = left, right
        self.left_label = Path(left_label) if left_label is not None else left
        self.right_label = Path(right_label) if right_label is not None else right
        self.left_read_only, self.right_read_only = left_read_only, right_read_only
        self.open_detail, self.sync_executor = open_detail, sync_executor
        self.marker_position_var = tk.StringVar(
            value=marker_position if marker_position in {"left", "middle", "right"} else "middle")
        self.marker_changed = marker_changed
        self.rows, self.actions, self.item_paths, self.item_keys = [], {}, {}, {}
        self._expand_state = True
        self._syncing_selection = False
        self._syncing_scroll = False
        self._syncing_open = False
        self.matches, self.match_index = [], -1
        self.difference_items, self.difference_index = [], -1
        self._scan_queue, self._cancel_event, self._scanning = queue.Queue(), threading.Event(), False
        self.sort_column, self.sort_reverse = "path", False
        self.scale = 1.0
        self.palette = getattr(master.winfo_toplevel(), "palette", color_scheme("light"))
        self._diff_icons = {}
        self.nested_details = {}

        self.session_tabs = ChamferNotebook(self)
        self.session_tabs.pack(fill="both", expand=True)
        self.session_tabs.set_theme(self.palette)
        self.summary = ttk.Frame(self.session_tabs)
        self.session_tabs.add(self.summary, text=tr("Folder Overview"))

        self.recursive_var = tk.BooleanVar(value=True)
        self.content_var = tk.BooleanVar(value=self.left_read_only or self.right_read_only)
        self.text_equivalent_var = tk.BooleanVar(value=True)
        self.view_mode_var = tk.StringVar(value="all")

        bar = ttk.Frame(self.summary, padding=(3, 3, 3, 1)); bar.pack(fill="x")
        ttk.Label(bar, text=tr("Mask:")).pack(side="left", padx=(0, 3))
        self.mask_var = tk.StringVar(value="*")
        ttk.Entry(bar, textvariable=self.mask_var, width=32).pack(side="left", padx=(0, 6))
        ttk.Button(bar, text=tr("Compare"), command=self.start_scan).pack(side="left", padx=(0, 3))
        ttk.Button(bar, text=tr("Cancel"), command=self.cancel_scan).pack(side="left", padx=(0, 8))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=(0, 7))
        self.recursive_button = ttk.Button(bar, command=lambda: self._toggle_option("recursive"))
        self.recursive_button.pack(side="left", padx=(0, 3))
        self.content_button = ttk.Button(bar, command=lambda: self._toggle_option("content"))
        self.content_button.pack(side="left", padx=(0, 3))
        self.text_equivalent_button = ttk.Button(
            bar, command=lambda: self._toggle_option("text_equivalent"))
        self.text_equivalent_button.pack(side="left")
        self.text_equivalent_button._pfc_tooltip = ToolTip(
            self.text_equivalent_button,
            lambda: tr("Ignore BOM, line-ending, trailing-space, Unicode-composition, and invisible-control differences in text files."))

        self.body = ttk.Frame(self.summary)
        self.center_header = ttk.Frame(self.body)
        options = ttk.Frame(self.summary, padding=(3, 1)); options.pack(fill="x")
        self.diff_button = ttk.Menubutton(self.center_header, text=tr("Diffs"))
        self.diff_menu = tk.Menu(self.diff_button, tearoff=False)
        self.diff_button.configure(menu=self.diff_menu, compound="left")
        self.diff_button.pack(side="top", fill="x")
        self._build_diff_menu()
        ttk.Button(options, text=tr("Expand All"), command=self.expand_all).pack(side="left", padx=(0, 3))
        ttk.Button(options, text=tr("Collapse All"), command=self.collapse_all).pack(side="left", padx=(0, 3))
        ttk.Button(options, text=tr("Set Base Folder"), command=self.set_base_folder).pack(side="left", padx=(0, 3))
        ttk.Separator(options, orient="vertical").pack(side="left", fill="y", padx=7)
        self.marker_button = ttk.Menubutton(options)
        self.marker_menu = tk.Menu(self.marker_button, tearoff=False)
        self.marker_button.configure(menu=self.marker_menu); self.marker_button.pack(side="left")
        self._build_marker_menu(); self._update_marker_button()

        navigation = ttk.Frame(self.summary, padding=(3, 1)); navigation.pack(fill="x")
        self.previous_button = ttk.Button(navigation, text=f"F7 {tr('Diff <<')}", command=self.previous)
        self.previous_button.pack(side="left", padx=(0, 3))
        self.next_button = ttk.Button(navigation, text=f"F8 {tr('Diff >>')}", command=self.next)
        self.next_button.pack(side="left", padx=(0, 3))
        self.diff_status = ttk.Label(navigation, width=18, anchor="w")
        self.diff_status.pack(side="left", padx=(0, 8))
        self.search_var, self.case_var = tk.StringVar(), tk.BooleanVar(value=False)
        ttk.Label(navigation, text=tr("Find:")).pack(side="left", padx=(0, 3))
        self.search = ttk.Entry(navigation, textvariable=self.search_var, width=32)
        self.search.pack(side="left", padx=(0, 4))
        self.search.bind("<Return>", lambda _event: self.find_next())
        self.search.bind("<Shift-Return>", lambda _event: self.find_previous())
        ttk.Button(navigation, text=tr("Find Prev"), command=self.find_previous).pack(side="left", padx=(0, 3))
        ttk.Button(navigation, text=tr("Find Next"), command=self.find_next).pack(side="left", padx=(0, 3))
        self.find_status = ttk.Label(navigation, anchor="w")
        self.find_status.pack(side="left", padx=(2, 6))
        self.case_button = ttk.Button(navigation, command=lambda: self._toggle_option("case"))
        self.case_button.pack(side="left")
        self._update_toggle_buttons()

        status_row = ttk.Frame(self.summary, padding=(5, 3)); status_row.pack(side="bottom", fill="x")
        self.scan_status = ttk.Label(status_row, text=tr("Ready"), anchor="w")
        self.scan_status.pack(side="left")
        ttk.Label(status_row, text=tr("Copy only — no automatic delete")).pack(side="left", padx=(12, 0))
        ttk.Button(status_row, text=tr("Dry Run && Sync"), command=self.dry_run).pack(side="right")

        self.body.pack(fill="both", expand=True, pady=(3, 0))
        self.body.rowconfigure(1, weight=1)
        self.left_path_label = tk.Label(self.body, anchor="w", background="#2d668f",
                                        foreground="white", font="TkHeadingFont", padx=6, pady=3)
        self.right_path_label = tk.Label(self.body, anchor="w", background="#9b5d2e",
                                         foreground="white", font="TkHeadingFont", padx=6, pady=3)
        self.map_header = tk.Button(self.center_header, text="⇄", command=self.swap_sides,
                                    background="#263d4c", foreground="white",
                                    activebackground="#36566b", activeforeground="white",
                                    font="TkHeadingFont", relief="flat", borderwidth=0,
                                    cursor="hand2", pady=3)
        self.map_header._pfc_tooltip = ToolTip(self.map_header, tr("Swap Sides"))
        self.map_header.pack(side="top", fill="x")
        self._update_path_labels()
        self.left_frame = ttk.Frame(self.body); self.right_frame = ttk.Frame(self.body)
        for frame in (self.left_frame, self.right_frame):
            frame.rowconfigure(0, weight=1); frame.columnconfigure(0, weight=1)
        self.left_tree = ttk.Treeview(self.left_frame, columns=("action", "detail"),
                                      show=("tree", "headings"), selectmode="extended",
                                      style="PFCCompare.Treeview")
        self.right_tree = ttk.Treeview(self.right_frame, columns=("detail", "action"),
                                       show=("tree", "headings"), selectmode="extended",
                                       style="PFCCompare.Treeview")
        self.tree = self.left_tree
        self.left_tree.heading("#0", text=tr("Name"), command=lambda: self.change_sort("path"))
        self.left_tree.heading("action", text=tr("Action"), command=lambda: self.change_sort("action"))
        self.left_tree.heading("detail", text=f"{tr('Size')} / {tr('Modified')}",
                               command=lambda: self.change_sort("left_detail"))
        self.right_tree.heading("#0", text=tr("Name"), command=lambda: self.change_sort("path"))
        self.right_tree.heading("detail", text=f"{tr('Size')} / {tr('Modified')}",
                                command=lambda: self.change_sort("right_detail"))
        self.right_tree.heading("action", text=tr("Action"), command=lambda: self.change_sort("action"))
        for tree in (self.left_tree, self.right_tree):
            tree.column("#0", width=340, minwidth=100, stretch=True)
            tree.column("action", width=70, minwidth=45, stretch=False, anchor="center")
            tree.column("detail", width=205, minwidth=95, stretch=False)
            tree.grid(row=0, column=0, sticky="nsew")
            tree.bind("<<TreeviewSelect>>", lambda event, source=tree: self._sync_selection(source))
            tree.bind("<<TreeviewOpen>>", lambda event, source=tree: self._sync_open(source, True))
            tree.bind("<<TreeviewClose>>", lambda event, source=tree: self._sync_open(source, False))
            tree.bind("<Double-1>", self._open); tree.bind("<Return>", self._open)
            tree.bind("<Control-Right>", lambda _e: self.set_action("right"))
            tree.bind("<Control-Left>", lambda _e: self.set_action("left"))
            tree.bind("<space>", lambda _e: self.set_action("skip"))
            tree.bind("<MouseWheel>", self._mousewheel)
            tree._pfc_sync_tooltip = ToolTip(
                tree, tr("Enter opens nested file compare • Ctrl+→ copy to right • "
                         "Ctrl+← copy to left • Space skip"), delay=5000)
        left_x = ttk.Scrollbar(self.left_frame, orient="horizontal", command=self.left_tree.xview)
        right_x = ttk.Scrollbar(self.right_frame, orient="horizontal", command=self.right_tree.xview)
        left_x.grid(row=1, column=0, sticky="ew"); right_x.grid(row=1, column=0, sticky="ew")
        self.left_tree.configure(xscrollcommand=left_x.set, yscrollcommand=self._left_scrolled)
        self.right_tree.configure(xscrollcommand=right_x.set, yscrollcommand=self._right_scrolled)
        self.difference_map = DifferenceMap(self.body, self._jump_to_row)
        self.center_divider = ttk.Separator(self.body, orient="vertical")
        self.scroll = ttk.Scrollbar(self.body, orient="vertical", command=self._scroll)
        self._layout_marker()
        self.apply_scale(1.0)
        self.apply_color_scheme(getattr(master.winfo_toplevel(), "palette", color_scheme("light")))
        self.start_scan()

    def _trees(self):
        return (self.left_tree, self.right_tree)

    def _toggle_option(self, option):
        if option == "recursive":
            self.recursive_var.set(not self.recursive_var.get())
        elif option == "content":
            self.content_var.set(not self.content_var.get())
        elif option == "text_equivalent":
            self.text_equivalent_var.set(not self.text_equivalent_var.get())
        elif option == "case":
            self.case_var.set(not self.case_var.get()); self.find_all()
        self._update_toggle_buttons()
        return "break"

    def _update_toggle_buttons(self):
        self.recursive_button.configure(
            text=f"{'✓' if self.recursive_var.get() else '–'} {tr('Recursive')}")
        self.content_button.configure(
            text=f"{'✓' if self.content_var.get() else '–'} {tr('By content')}")
        self.text_equivalent_button.configure(
            text=f"{'✓' if self.text_equivalent_var.get() else '–'} {tr('Text equivalent')}")
        self.case_button.configure(
            text=f"{'✓' if self.case_var.get() else '–'} {tr('Case sensitive')}")

    def _build_diff_menu(self):
        self.diff_menu.delete(0, "end")
        selected = self.view_mode_var.get()
        self._diff_icons = {value: self._make_diff_icon(value) for value in self.DIFF_FILTERS}
        separators_after = {"orphans", "right_newer"}
        for value in self.DIFF_FILTERS:
            prefix = "● " if value == selected else "   "
            self.diff_menu.add_command(
                label=prefix + tr(self.DIFF_LABELS[value]), image=self._diff_icons[value],
                compound="left", command=lambda mode=value: self._select_diff_filter(mode))
            if value in separators_after:
                self.diff_menu.add_separator()
        self._update_diff_button()

    def _make_diff_icon(self, value):
        """Two columns encode left/right; red means changed/newer, purple means orphan."""
        scale = max(1.0, self.scale)
        block, gap = max(5, round(6 * scale)), max(2, round(2 * scale))
        width, height = block * 2 + gap * 3, block * 2 + gap * 3
        icon = tk.PhotoImage(master=self, width=width, height=height)
        dark = self.palette.get("window") == "#20262c"
        colors = {
            "neutral": "#a9b3ba" if dark else "#7b858c",
            "difference": "#ff625d" if dark else "#d92f2f",
            "orphan": "#b985ff" if dark else "#7d42bd",
        }
        layouts = {
            "all": (("neutral", "neutral"), ("neutral", "neutral")),
            "differences": (("difference", "difference"), ("difference", "difference")),
            "no_orphans": (("difference", "difference"), ("neutral", "neutral")),
            "differences_no_orphans": (("difference", "difference"), (None, None)),
            "orphans": (("orphan", "orphan"), ("orphan", "orphan")),
            "left_newer": (("difference", None), ("difference", None)),
            "right_newer": ((None, "difference"), (None, "difference")),
            "left_newer_orphans": (("difference", None), ("orphan", None)),
            "right_newer_orphans": ((None, "difference"), (None, "orphan")),
            "left_orphans": (("orphan", None), ("orphan", None)),
            "right_orphans": ((None, "orphan"), (None, "orphan")),
        }
        for row, pair in enumerate(layouts[value]):
            for column, token in enumerate(pair):
                if token is None:
                    continue
                x = gap + column * (block + gap); y = gap + row * (block + gap)
                icon.put(colors[token], to=(x, y, x + block, y + block))
        return icon

    def _update_diff_button(self):
        key = self.view_mode_var.get()
        image = self._diff_icons.get(key)
        self.diff_button.configure(text=tr("Diffs"), image=image or "", compound="left")
        tooltip_text = tr(self.DIFF_LABELS.get(key, "Show All"))
        if hasattr(self, "_diff_tooltip"):
            self._diff_tooltip.text = tooltip_text
        else:
            self._diff_tooltip = ToolTip(self.diff_button, tooltip_text)

    def _select_diff_filter(self, value):
        self.view_mode_var.set(value); self._set_diff_filter()

    def _build_marker_menu(self):
        self.marker_menu.delete(0, "end")
        selected = self.marker_position_var.get()
        for value, label in (("left", "Left"), ("middle", "Middle"), ("right", "Right")):
            prefix = "● " if value == selected else "   "
            self.marker_menu.add_command(label=prefix + tr(label),
                                         command=lambda position=value:
                                         self.set_marker_position(position, notify=True))

    def _update_marker_button(self):
        labels = {"left": "Left", "middle": "Middle", "right": "Right"}
        self.marker_button.configure(
            text=f"{tr('Map:')} {tr(labels.get(self.marker_position_var.get(), 'Middle'))}")

    def _selected_items(self):
        return self.left_tree.selection() or self.right_tree.selection()

    def _sync_selection(self, source):
        if self._syncing_selection:
            return
        self._syncing_selection = True
        try:
            target = self.right_tree if source is self.left_tree else self.left_tree
            selected = source.selection()
            if tuple(target.selection()) != tuple(selected):
                target.selection_set(selected)
            focus = source.focus()
            if focus and target.focus() != focus:
                target.focus(focus); target.see(focus)
        finally:
            self._syncing_selection = False

    def _sync_open(self, source, opened):
        if self._syncing_open:
            return
        iid = source.focus()
        target = self.right_tree if source is self.left_tree else self.left_tree
        if iid and target.exists(iid) and bool(target.item(iid, "open")) != opened:
            self._syncing_open = True
            try:
                target.item(iid, open=opened)
            finally:
                self._syncing_open = False

    def _scroll(self, *args):
        for tree in self._trees(): tree.yview(*args)

    def _left_scrolled(self, first, last):
        self.scroll.set(first, last); self.difference_map.set_viewport(first, last)
        if self._syncing_scroll:
            return
        self._syncing_scroll = True
        try:
            self.right_tree.yview_moveto(first)
        finally:
            self._syncing_scroll = False

    def _right_scrolled(self, first, last):
        self.scroll.set(first, last); self.difference_map.set_viewport(first, last)
        if self._syncing_scroll:
            return
        self._syncing_scroll = True
        try:
            self.left_tree.yview_moveto(first)
        finally:
            self._syncing_scroll = False

    def _mousewheel(self, event):
        units = -int(event.delta / 120) if event.delta else 0
        for tree in self._trees(): tree.yview_scroll(units, "units")
        return "break"

    def set_marker_position(self, position: str, notify: bool = False):
        if position not in {"left", "middle", "right"}: position = "middle"
        self.marker_position_var.set(position); self._layout_marker()
        self._build_marker_menu(); self._update_marker_button()
        for details in self.nested_details.values():
            view = getattr(details["detail"], "view", details["detail"])
            if hasattr(view, "set_marker_position"):
                view.set_marker_position(position)
        if notify and self.marker_changed is not None: self.marker_changed(position)

    def _marker_position_changed(self):
        self.set_marker_position(self.marker_position_var.get(), notify=True)

    def _layout_marker(self):
        for column in range(6): self.body.columnconfigure(column, weight=0, uniform="")
        position = self.marker_position_var.get()
        map_column = 0 if position == "left" else (4 if position == "right" else 2)
        left_column, center_column, right_column = 1, 2, 3
        for column in (left_column, right_column):
            self.body.columnconfigure(column, weight=1, uniform="compare")
        self.left_path_label.grid(row=0, column=left_column, sticky="ew")
        self.left_frame.grid(row=1, column=left_column, sticky="nsew")
        self.right_path_label.grid(row=0, column=right_column, sticky="ew")
        self.right_frame.grid(row=1, column=right_column, sticky="nsew")
        self.center_header.grid(row=0, column=center_column, sticky="ew", padx=4)
        self.difference_map.grid(row=1, column=map_column, sticky="ns", padx=4)
        if position == "middle":
            self.center_divider.grid_forget()
        else:
            self.center_divider.grid(row=1, column=center_column, sticky="ns")
        self.scroll.grid(row=1, column=5, sticky="ns")

    def expand_all(self):
        self._expand_state = True
        for iid in self.left_tree.get_children(""): self._set_open_recursive(iid, True)
        return "break"

    def collapse_all(self):
        self._expand_state = False
        for iid in self.left_tree.get_children(""): self._set_open_recursive(iid, False)
        return "break"

    def _set_open_recursive(self, iid, opened):
        for tree in self._trees(): tree.item(iid, open=opened)
        for child in self.left_tree.get_children(iid): self._set_open_recursive(child, opened)

    def _all_tree_items(self, parent=""):
        for iid in self.left_tree.get_children(parent):
            yield iid
            yield from self._all_tree_items(iid)

    def apply_color_scheme(self, palette):
        self.palette = palette
        self.session_tabs.set_theme(palette)
        self.left_path_label.configure(background=palette["left_header"], foreground="#ffffff")
        self.right_path_label.configure(background=palette["right_header"], foreground="#ffffff")
        self.map_header.configure(background=palette["map_header"], foreground="#ffffff",
                                  activebackground=palette["menu_active"],
                                  activeforeground=palette["menu_active_text"])
        self.difference_map.apply_color_scheme(palette)
        dark = palette["window"] == "#20262c"
        for tree in self._trees():
            tree.tag_configure("find_match", background=palette["match"], foreground=palette["text"])
            tree.tag_configure("current_match", background=palette["current_diff"], foreground="#ffffff")
            tree.tag_configure("different", foreground="#ff7770" if dark else "#a00000")
            tree.tag_configure("newer_left", foreground="#ff7770" if dark else "#a00000")
            tree.tag_configure("newer_right", foreground="#ff7770" if dark else "#a00000")
            tree.tag_configure("orphan_left", foreground="#c391ff" if dark else "#7137a8")
            tree.tag_configure("orphan_right", foreground="#c391ff" if dark else "#7137a8")
            tree.tag_configure("identical", foreground=palette["muted"])
        self._build_diff_menu()
        self.diff_menu.configure(background=palette["menu"], foreground=palette["menu_text"],
                                 activebackground=palette["menu_active"],
                                 activeforeground=palette["menu_active_text"])
        self.marker_menu.configure(background=palette["menu"], foreground=palette["menu_text"],
                                   activebackground=palette["menu_active"],
                                   activeforeground=palette["menu_active_text"])
        for details in self.nested_details.values():
            view = getattr(details["detail"], "view", details["detail"])
            handler = getattr(view, "apply_color_scheme", None)
            if callable(handler):
                handler(palette)

    def apply_scale(self, scale: float):
        self.scale = scale
        self.session_tabs.redraw()
        style = ttk.Style(self)
        linespace = tkfont.nametofont("TkDefaultFont").metrics("linespace")
        style.configure("PFCCompare.Treeview", font="TkDefaultFont",
                        rowheight=compare_row_height(linespace, scale))
        style.configure("PFCCompare.Treeview.Heading", font="TkHeadingFont")
        for tree in self._trees():
            tree.column("#0", width=max(130, round(340 * scale)))
            tree.column("action", width=max(50, round(70 * scale)))
            tree.column("detail", width=max(110, round(205 * scale)))
        padding = max(3, round(3 * scale))
        for label in (self.left_path_label, self.right_path_label): label.configure(padx=padding * 2, pady=padding)
        self.map_header.configure(pady=padding); self.difference_map.apply_scale(scale)
        self._build_diff_menu()
        for details in self.nested_details.values():
            handler = getattr(details["detail"], "apply_scale", None)
            if callable(handler):
                handler(scale)

    def apply_language(self, old_language: str):
        selected_keys = {self.item_keys.get(iid) for iid in self._selected_items()}
        retranslate_widgets(self, old_language)
        self.previous_button.configure(text=f"F7 {tr('Diff <<')}")
        self.next_button.configure(text=f"F8 {tr('Diff >>')}")
        self._update_path_labels(); self._build_diff_menu(); self._build_marker_menu()
        self._update_marker_button(); self._update_toggle_buttons(); self._update_headings(); self.populate()
        selected = [iid for iid in self._all_tree_items() if self.item_keys.get(iid) in selected_keys]
        self._select_items(selected)
        self.session_tabs.tab(self.summary, text=tr("Folder Overview"))
        for page, details in self.nested_details.items():
            details["back"].configure(text=tr("← Folder Overview"))
            details["caption"].configure(text=tr("Nested file compare"))
            handler = getattr(details["detail"], "apply_language", None)
            if callable(handler):
                handler(old_language)
            self.session_tabs.tab(
                page, text=f"{tr(details['kind'])}: {details['left'].name} ↔ {details['right'].name}")
        self.session_tabs.redraw()

    def _update_headings(self):
        direction = " ▼" if self.sort_reverse else " ▲"
        path_mark = direction if self.sort_column == "path" else ""
        action_mark = direction if self.sort_column == "action" else ""
        self.left_tree.heading("#0", text=tr("Name") + path_mark)
        self.right_tree.heading("#0", text=tr("Name") + path_mark)
        self.left_tree.heading("action", text=tr("Action") + action_mark)
        self.right_tree.heading("action", text=tr("Action") + action_mark)
        self.left_tree.heading("detail", text=f"{tr('Size')} / {tr('Modified')}" +
                               (direction if self.sort_column == "left_detail" else ""))
        self.right_tree.heading("detail", text=f"{tr('Size')} / {tr('Modified')}" +
                                (direction if self.sort_column == "right_detail" else ""))

    def change_sort(self, column):
        selected_keys = {self.item_keys.get(iid) for iid in self._selected_items()}
        self.sort_reverse = not self.sort_reverse if column == self.sort_column else False
        self.sort_column = column; self._update_headings(); self.populate()
        self._select_items([iid for iid in self._all_tree_items()
                            if self.item_keys.get(iid) in selected_keys])

    def populate(self):
        for tree in self._trees(): tree.delete(*tree.get_children())
        self.item_paths, self.item_keys = {}, {}
        self.difference_items, self.difference_index = [], -1
        action_label = {"right": "→", "left": "←", "skip": tr("Skip")}
        allowed = self.DIFF_FILTERS.get(self.view_mode_var.get())
        initially_visible = list(self.rows) if allowed is None else [row for row in self.rows if row[0] in allowed]
        rows_by_key = {row[1].casefold(): row for row in self.rows}
        needed = {row[1].casefold() for row in initially_visible}
        for _status, relative, _left, _right in initially_visible:
            parent = Path(relative).parent
            while parent != Path("."):
                key = str(parent).casefold()
                if key in rows_by_key: needed.add(key)
                parent = parent.parent
        visible = [row for row in self.rows if row[1].casefold() in needed]
        if self.sort_column == "action":
            visible.sort(key=lambda row: self.actions.get(row[1], ""), reverse=self.sort_reverse)
        elif self.sort_column in {"left_detail", "right_detail"}:
            path_index = 2 if self.sort_column == "left_detail" else 3
            def metadata_key(row):
                path = row[path_index]
                if path is None: return (0, 0, 0)
                try:
                    stat = path.stat(); return (2 if path.is_dir() else 1, stat.st_size, stat.st_mtime_ns)
                except OSError: return (0, 0, 0)
            visible.sort(key=metadata_key, reverse=self.sort_reverse)
        else:
            visible.sort(key=lambda row: row[1].casefold(), reverse=self.sort_reverse)
        visible.sort(key=lambda row: len(Path(row[1]).parts))
        item_ids = {}
        for index, (status, path, left, right) in enumerate(visible):
            iid = f"folder-row-{index}"
            tag = ("orphan_left" if status == "Left only" else
                   "orphan_right" if status == "Right only" else
                   "newer_left" if status == "Left newer" else
                   "newer_right" if status == "Right newer" else
                   "identical" if status == "Identical" else "different")
            parent_iid = item_ids.get(str(Path(path).parent).casefold(), "")
            action = action_label.get(self.actions.get(path), "")
            self.left_tree.insert(parent_iid, "end", iid=iid, text=path if left is not None else "",
                                  open=self._expand_state,
                                  values=(action if self.actions.get(path) in {"right", "skip"} else "",
                                          self._detail(left)), tags=(tag,))
            self.right_tree.insert(parent_iid, "end", iid=iid, text=path if right is not None else "",
                                   open=self._expand_state,
                                   values=(self._detail(right),
                                           action if self.actions.get(path) in {"left", "skip"} else ""),
                                   tags=(tag,))
            item_ids[path.casefold()] = iid; self.item_paths[iid] = (left, right); self.item_keys[iid] = path
            if status != "Identical": self.difference_items.append(iid)
        ordered = list(self._all_tree_items())
        difference_rows = [ordered.index(iid) + 1 for iid in self.difference_items if iid in ordered]
        self.difference_map.set_rows(difference_rows, len(ordered))
        self._update_difference_status(0); self.find_all()

    def _select_items(self, items):
        items = tuple(items)
        self._syncing_selection = True
        try:
            for tree in self._trees():
                tree.selection_set(items)
                if items: tree.focus(items[0]); tree.see(items[0])
        finally:
            self._syncing_selection = False
        if items: self.left_tree.focus_set()

    def _difference(self, direction):
        if not self.difference_items: return "break"
        self.difference_index = (self.difference_index + direction) % len(self.difference_items)
        iid = self.difference_items[self.difference_index]; self._select_items((iid,))
        ordered = list(self._all_tree_items())
        if iid in ordered: self.difference_map.set_current(ordered.index(iid) + 1)
        self._update_difference_status(self.difference_index + 1)
        return "break"

    def _update_difference_status(self, current):
        self.diff_status.configure(text=tr("{current} of {count} differences",
                                           current=current, count=len(self.difference_items)))

    def _jump_to_row(self, row):
        ordered = list(self._all_tree_items())
        if 1 <= row <= len(ordered) and ordered[row - 1] in self.difference_items:
            self.difference_index = self.difference_items.index(ordered[row - 1])
            self._difference(0)

    def find_all(self):
        self.matches, self.match_index = [], -1; needle = self.search_var.get()
        for iid in self._all_tree_items():
            tags = self.left_tree.item(iid, "tags")
            semantic_tags = {"orphan_left", "orphan_right", "newer_left", "newer_right",
                             "different", "identical"}
            base = next((tag for tag in tags if tag in semantic_tags), "different")
            haystack = " ".join((self.left_tree.item(iid, "text"), self.right_tree.item(iid, "text"),
                                 *(str(v) for v in self.left_tree.item(iid, "values")),
                                 *(str(v) for v in self.right_tree.item(iid, "values"))))
            matched = needle in haystack if self.case_var.get() else needle.casefold() in haystack.casefold()
            row_tags = (base, "find_match") if needle and matched else (base,)
            for tree in self._trees(): tree.item(iid, tags=row_tags)
            if needle and matched: self.matches.append(iid)
        self.find_status.configure(text=tr("{count} match(es)", count=len(self.matches)) if needle else "")

    def _find(self, direction):
        previous = self.match_index; self.find_all()
        if not self.matches: return "break"
        self.match_index = (previous + direction) % len(self.matches); iid = self.matches[self.match_index]
        for tree in self._trees(): tree.item(iid, tags=(*tree.item(iid, "tags"), "current_match"))
        self._select_items((iid,))
        self.find_status.configure(text=tr("{current} of {count} matches",
                                           current=self.match_index + 1, count=len(self.matches)))
        return "break"

    def set_action(self, action):
        selected = self._selected_items(); selected_keys = {self.item_keys.get(iid) for iid in selected}
        for iid in selected:
            left, right = self.item_paths.get(iid, (None, None)); key = self.item_keys.get(iid)
            if key is None: continue
            if action == "right" and left is not None and not self.right_read_only: self.actions[key] = action
            elif action == "left" and right is not None and not self.left_read_only: self.actions[key] = action
            elif action == "skip": self.actions[key] = action
        self.populate(); self._select_items([iid for iid in self._all_tree_items()
                                             if self.item_keys.get(iid) in selected_keys])
        return "break"

    def set_base_folder(self):
        selected = self._selected_items()
        if not selected:
            messagebox.showinfo(tr("Set Base Folder"), tr("Select a folder row first."), parent=self)
            return "break"
        left, right = self.item_paths.get(selected[0], (None, None)); changed = False
        if left is not None and left.is_dir(): self.left_root = left; changed = True
        if right is not None and right.is_dir(): self.right_root = right; changed = True
        if not changed:
            messagebox.showinfo(tr("Set Base Folder"), tr("The selected row is not a folder."), parent=self)
            return "break"
        self._update_path_labels(); self.start_scan(); return "break"

    def _update_path_labels(self):
        self.left_path_label.configure(text=f"{tr('Left')}: {self._base_label('left')}")
        self.right_path_label.configure(text=f"{tr('Right')}: {self._base_label('right')}")

    def _active_detail_view(self):
        selected = self.session_tabs.select()
        if not selected:
            return None
        page = self.nametowidget(selected)
        details = self.nested_details.get(page)
        if details is None:
            return None
        return getattr(details["detail"], "view", details["detail"])

    def _show_summary(self):
        self.session_tabs.select(self.summary)
        self.after_idle(self.left_tree.focus_set)

    def open_nested_detail(self, left: Path, right: Path, relative: str):
        key = (str(left), str(right))
        for page, details in self.nested_details.items():
            if details["key"] == key:
                self.session_tabs.select(page)
                view = getattr(details["detail"], "view", details["detail"])
                self.after_idle(lambda target=getattr(view, "left", view): target.focus_set())
                return "break"

        page = ttk.Frame(self.session_tabs)
        breadcrumb = ttk.Frame(page, padding=(4, 3))
        breadcrumb.pack(fill="x")
        back = ttk.Button(breadcrumb, text=tr("← Folder Overview"), command=self._show_summary)
        back.pack(side="left", padx=(0, 8))
        caption = ttk.Label(breadcrumb, text=tr("Nested file compare"), style="Heading.TLabel")
        caption.pack(side="left")
        host = ttk.Frame(page)
        host.pack(fill="both", expand=True)
        left_title = nested_source_label(self.left_label, relative)
        right_title = nested_source_label(self.right_label, relative)
        kind, detail = self.open_detail(
            host, left, right, left_title=left_title, right_title=right_title)
        detail.pack(fill="both", expand=True)
        install_button_tooltips(page)
        details = {
            "key": key, "detail": detail, "kind": kind, "left": left, "right": right,
            "back": back, "caption": caption,
        }
        self.nested_details[page] = details
        self.session_tabs.add(page, text=f"{tr(kind)}: {left.name} ↔ {right.name}")
        view = getattr(detail, "view", detail)
        color_handler = getattr(view, "apply_color_scheme", None)
        if callable(color_handler):
            color_handler(self.palette)
        scale_handler = getattr(detail, "apply_scale", None)
        if callable(scale_handler):
            scale_handler(self.scale)
        self.after_idle(lambda: getattr(view, "left", view).focus_set())
        return "break"

    def close_nested_detail(self):
        selected = self.session_tabs.select()
        if not selected:
            return False
        page = self.nametowidget(selected)
        if page is self.summary:
            return False
        if page not in self.nested_details:
            return False
        self.session_tabs.forget(page)
        self.nested_details.pop(page, None)
        page.destroy()
        self._show_summary()
        return True

    def next(self):
        view = self._active_detail_view()
        if view is not None and hasattr(view, "next"):
            return view.next()
        return self._difference(1)

    def previous(self):
        view = self._active_detail_view()
        if view is not None and hasattr(view, "previous"):
            return view.previous()
        return self._difference(-1)

    def focus_search(self):
        view = self._active_detail_view()
        if view is not None and hasattr(view, "focus_search"):
            return view.focus_search()
        self.search.focus_set(); self.search.selection_range(0, "end")
        return "break"

    def _open(self, _event=None):
        selected = self._selected_items()
        if selected:
            left, right = self.item_paths.get(selected[0], (None, None))
            relative = self.item_keys.get(selected[0], "")
            if left and right and left.is_file() and right.is_file():
                return self.open_nested_detail(left, right, relative)
        return "break"


class TableCompare(TextCompare):
    def __init__(self, master, left: Path, right: Path, marker_position="middle", marker_changed=None,
                 left_title=None, right_title=None):
        def rows(path):
            delimiter = "\t" if path.suffix.casefold() == ".tsv" else ","
            with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
                return [" | ".join(row) for row in csv.reader(stream, delimiter=delimiter)]
        ttk.Frame.__init__(self, master)
        a, b = "\n".join(rows(left)), "\n".join(rows(right))
        aligned, differences = aligned_text(a, b)
        self.view = SideBySideText(
            self, [(r[0], r[1]) for r in aligned], [(r[2], r[3]) for r in aligned], differences,
            status_factory=lambda count=len(differences): tr("{count} different row(s)", count=count),
            left_title=left_title or left, right_title=right_title or right,
            marker_position=marker_position,
            marker_changed=marker_changed)
        self.view.pack(fill="both", expand=True)


class CompareWindow(tk.Toplevel):
    def __init__(self, master, config, save_config, sync_executor=None):
        super().__init__(master)
        self.config_data, self.save_config = config, save_config
        self.palette = getattr(master, "palette", color_scheme("light"))
        self.sync_executor = sync_executor
        self.comparisons = {}
        self._archive_workspaces = []
        self.scale = 1.0
        self.marker_position = config.get("compare", "marker_position", fallback="middle")
        if self.marker_position not in {"left", "middle", "right"}:
            self.marker_position = "middle"
        self._refresh_job = None
        self.title(tr("PFC Compare"))
        self.geometry(config.get("compare", "geometry", fallback="1400x850"))
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.notebook = ChamferNotebook(self); self.notebook.pack(fill="both", expand=True)
        self.notebook.set_theme(self.palette)
        self.configure(background=self.palette["window"])
        self.bind("<F7>", lambda _e: self._navigate("previous"))
        self.bind("<F8>", lambda _e: self._navigate("next"))
        self.bind("<Control-f>", lambda _e: self.focus_search())
        self.bind("<Escape>", lambda _e: self.close_active())
        install_button_tooltips(self)
        self._schedule_refresh()

    def apply_scale(self, scale: float) -> None:
        self.scale = scale
        self.notebook.redraw()
        for frame in self.comparisons:
            handler = getattr(frame, "apply_scale", None)
            if callable(handler):
                handler(scale)

    def apply_color_scheme(self, palette) -> None:
        self.palette = palette
        self.configure(background=palette["window"])
        self.notebook.set_theme(palette)
        for frame in self.comparisons:
            target = getattr(frame, "view", frame)
            handler = getattr(target, "apply_color_scheme", None)
            if callable(handler):
                handler(palette)

    def apply_language(self, old_language: str) -> None:
        retranslate_widgets(self, old_language)
        self.title(tr("PFC Compare"))
        for frame, (left, right, kind, _signature) in self.comparisons.items():
            if hasattr(frame, "apply_language"):
                frame.apply_language(old_language)
            self.notebook.tab(frame, text=f"{tr(kind)}: {left.name} ↔ {right.name}")
        self.notebook.redraw()

    @staticmethod
    def _signature(left: Path, right: Path):
        if left.is_dir() or right.is_dir():
            return None
        try:
            return tuple((path.stat().st_mtime_ns, path.stat().st_size) for path in (left, right))
        except OSError:
            return None

    def _make_frame(self, left: Path, right: Path, kind: str):
        if kind == "Folder":
            left_root, left_read_only = self._prepare_folder_source(left)
            right_root, right_read_only = self._prepare_folder_source(right)
            return FolderCompare(self.notebook, left_root, right_root, self._make_file_frame,
                                 self.sync_executor,
                                 left_label=left, right_label=right,
                                 left_read_only=left_read_only, right_read_only=right_read_only,
                                 marker_position=self.marker_position,
                                 marker_changed=self.set_marker_position)
        return self._make_file_frame(self.notebook, left, right, kind)[1]

    def _make_file_frame(self, master, left: Path, right: Path, kind=None,
                         left_title=None, right_title=None):
        kind = kind or detect_compare_type(left, right)
        options = {
            "marker_position": self.marker_position,
            "marker_changed": self.set_marker_position,
            "left_title": left_title,
            "right_title": right_title,
        }
        if kind == "Text":
            return kind, TextCompare(master, left, right, **options)
        if kind == "Table":
            return kind, TableCompare(master, left, right, **options)
        return "Binary", BinaryCompare(master, left, right, **options)

    def _prepare_folder_source(self, path: Path):
        if not is_compare_archive(path):
            return path, False
        workspace, root = extract_compare_archive(path)
        self._archive_workspaces.append(workspace)
        return root, True

    def set_marker_position(self, position: str) -> None:
        if position not in {"left", "middle", "right"}:
            return
        self.marker_position = position
        for frame in self.comparisons:
            view = getattr(frame, "view", None)
            if view is not None and hasattr(view, "set_marker_position"):
                view.set_marker_position(position)
        if not self.config_data.has_section("compare"):
            self.config_data.add_section("compare")
        self.config_data.set("compare", "marker_position", position)
        self.save_config()

    def add(self, left: Path, right: Path, requested="Auto"):
        left_container, right_container = is_compare_container(left), is_compare_container(right)
        kind = detect_compare_type(left, right) if requested == "Auto" else requested
        if left_container != right_container:
            messagebox.showerror(tr("Compare"), tr("Select two files or two folders."), parent=self); return
        if left_container and right_container:
            kind = "Folder"
        frame = self._make_frame(left, right, kind)
        install_button_tooltips(frame)
        self.notebook.add(frame, text=f"{tr(kind)}: {left.name} ↔ {right.name}")
        self.comparisons[frame] = (left, right, kind, self._signature(left, right))
        target = getattr(frame, "view", frame)
        handler = getattr(target, "apply_color_scheme", None)
        if callable(handler):
            handler(self.palette)
        handler = getattr(frame, "apply_scale", None)
        if callable(handler):
            handler(self.scale)
        self.notebook.select(frame); self.after_idle(self.activate)

    def activate(self):
        self.deiconify(); self.lift(); self.focus_force()

    def _schedule_refresh(self):
        self._refresh_job = self.after(2000, self._auto_refresh)

    def _auto_refresh(self):
        self._refresh_job = None
        if self.notebook.tabs():
            frame = self.nametowidget(self.notebook.select())
            details = self.comparisons.get(frame)
            if details:
                left, right, kind, previous = details
                current = self._signature(left, right)
                if current is not None and current != previous:
                    index = self.notebook.index(frame)
                    title = self.notebook.tab(frame)["text"]
                    self.notebook.forget(frame); self.comparisons.pop(frame, None); frame.destroy()
                    replacement = self._make_frame(left, right, kind)
                    install_button_tooltips(replacement)
                    self.notebook.add(replacement, text=title, position=index)
                    self.comparisons[replacement] = (left, right, kind, current)
                    target = getattr(replacement, "view", replacement)
                    theme_handler = getattr(target, "apply_color_scheme", None)
                    if callable(theme_handler):
                        theme_handler(self.palette)
                    handler = getattr(replacement, "apply_scale", None)
                    if callable(handler):
                        handler(self.scale)
        if self.winfo_exists(): self._schedule_refresh()

    def _navigate(self, method):
        frame = self.nametowidget(self.notebook.select())
        pending = [frame]
        while pending:
            widget = pending.pop(0)
            handler = getattr(widget, method, None)
            if callable(handler):
                handler(); return
            pending.extend(widget.winfo_children())

    def focus_search(self):
        frame = self.nametowidget(self.notebook.select())
        pending = [frame]
        while pending:
            widget = pending.pop(0)
            if hasattr(widget, "focus_search"): return widget.focus_search()
            pending.extend(widget.winfo_children())
        return "break"

    def close(self):
        if self._refresh_job is not None:
            self.after_cancel(self._refresh_job); self._refresh_job = None
        if not self.config_data.has_section("compare"): self.config_data.add_section("compare")
        self.config_data.set("compare", "geometry", self.geometry())
        for frame in list(self.comparisons):
            if hasattr(frame, "cancel_scan"): frame.cancel_scan()
        self.save_config(); self.destroy()
        for workspace in self._archive_workspaces:
            workspace.cleanup()
        self._archive_workspaces.clear()

    def close_active(self):
        tabs = self.notebook.tabs()
        current = self.notebook.select()
        widget = self.nametowidget(current)
        if hasattr(widget, "close_nested_detail") and widget.close_nested_detail():
            return
        if hasattr(widget, "cancel_scan") and widget.cancel_scan():
            return
        if len(tabs) <= 1:
            self.close()
            return
        self.notebook.forget(current)
        self.comparisons.pop(widget, None)
        widget.destroy()
