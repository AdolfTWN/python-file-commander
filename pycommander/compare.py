from __future__ import annotations

import csv
import difflib
import hashlib
import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from .tabs import ChamferNotebook


TEXT_SUFFIXES = {".txt", ".md", ".py", ".json", ".xml", ".html", ".htm", ".css", ".js",
                 ".ini", ".cfg", ".log", ".yaml", ".yml", ".sql", ".bat", ".ps1", ".c", ".h",
                 ".cpp", ".hpp", ".java", ".csv", ".tsv"}
TABLE_SUFFIXES = {".csv", ".tsv"}


def detect_compare_type(left: Path, right: Path) -> str:
    if left.is_dir() and right.is_dir():
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


class SideBySideText(ttk.Frame):
    def __init__(self, master, left_lines, right_lines, differences, status_text=""):
        super().__init__(master)
        self.differences = differences
        self.diff_index = -1
        toolbar = ttk.Frame(self); toolbar.pack(fill="x")
        ttk.Button(toolbar, text="F7 Previous", command=self.previous).pack(side="left")
        ttk.Button(toolbar, text="F8 Next", command=self.next).pack(side="left", padx=3)
        ttk.Label(toolbar, text=status_text).pack(side="left", padx=10)
        body = ttk.Panedwindow(self, orient="horizontal"); body.pack(fill="both", expand=True)
        self.left = tk.Text(body, wrap="none", undo=False)
        self.right = tk.Text(body, wrap="none", undo=False)
        body.add(self.left, weight=1); body.add(self.right, weight=1)
        scroll = ttk.Scrollbar(self, orient="vertical", command=self._scroll)
        scroll.pack(side="right", fill="y")
        self.left.configure(yscrollcommand=scroll.set); self.right.configure(yscrollcommand=scroll.set)
        for widget, lines in ((self.left, left_lines), (self.right, right_lines)):
            widget.tag_configure("diff", background="#ffe1a8")
            widget.tag_configure("current", background="#ffb347")
            for display_row, item in enumerate(lines, 1):
                source_number, line = item if isinstance(item, tuple) else (display_row, item)
                number_text = "" if source_number is None else str(source_number)
                widget.insert("end", f"{number_text:>6}  {line}\n", "diff" if display_row in differences else "")
            widget.configure(state="disabled")

    def _scroll(self, *args):
        self.left.yview(*args); self.right.yview(*args)

    def next(self):
        if self.differences:
            self.diff_index = (self.diff_index + 1) % len(self.differences); self._show()

    def previous(self):
        if self.differences:
            self.diff_index = (self.diff_index - 1) % len(self.differences); self._show()

    def _show(self):
        line = self.differences[self.diff_index]
        for widget in (self.left, self.right):
            widget.see(f"{line}.0")
            widget.tag_remove("current", "1.0", "end")
            widget.tag_add("current", f"{line}.0", f"{line}.end")


class TextCompare(ttk.Frame):
    def __init__(self, master, left: Path, right: Path):
        super().__init__(master)
        a = left.read_text(encoding="utf-8", errors="replace")
        b = right.read_text(encoding="utf-8", errors="replace")
        rows, differences = aligned_text(a, b)
        view = SideBySideText(self, [(row[0], row[1]) for row in rows], [(row[2], row[3]) for row in rows], differences,
                              f"{len(differences)} different line(s)")
        view.pack(fill="both", expand=True)


class BinaryCompare(ttk.Frame):
    LIMIT = 256 * 1024

    def __init__(self, master, left: Path, right: Path):
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
        status = f"SHA-256: {'identical' if file_hash(left) == file_hash(right) else 'different'}; first offset: "
        status += f"0x{different_offsets[0]:X}" if different_offsets else "none"
        SideBySideText(self, left_lines, right_lines, diff_lines, status).pack(fill="both", expand=True)


def folder_rows(left: Path, right: Path):
    left_items = {str(p.relative_to(left)).casefold(): p for p in left.rglob("*")}
    right_items = {str(p.relative_to(right)).casefold(): p for p in right.rglob("*")}
    for key in sorted(left_items.keys() | right_items.keys()):
        a, b = left_items.get(key), right_items.get(key)
        display = str((a.relative_to(left) if a else b.relative_to(right)))
        if a is None: status = "Right only"
        elif b is None: status = "Left only"
        elif a.is_dir() != b.is_dir(): status = "Type mismatch"
        elif a.is_dir(): status = "Identical"
        elif a.stat().st_size == b.stat().st_size and file_hash(a) == file_hash(b): status = "Identical"
        else: status = "Different"
        yield status, display, a, b


class FolderCompare(ttk.Frame):
    def __init__(self, master, left: Path, right: Path, open_detail):
        super().__init__(master)
        bar = ttk.Frame(self); bar.pack(fill="x")
        self.show_identical = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Show identical", variable=self.show_identical, command=self.populate).pack(side="left")
        self.tree = ttk.Treeview(self, columns=("status", "path", "left", "right"), show="headings")
        for col, width in (("status", 110), ("path", 420), ("left", 130), ("right", 130)):
            self.tree.heading(col, text=col.title()); self.tree.column(col, width=width)
        self.tree.pack(fill="both", expand=True)
        self.rows = list(folder_rows(left, right)); self.open_detail = open_detail
        self.tree.bind("<Double-1>", self._open); self.populate()

    def populate(self):
        self.tree.delete(*self.tree.get_children())
        for status, path, left, right in self.rows:
            if status == "Identical" and not self.show_identical.get(): continue
            self.tree.insert("", "end", values=(status, path,
                "—" if left is None else ("<DIR>" if left.is_dir() else left.stat().st_size),
                "—" if right is None else ("<DIR>" if right.is_dir() else right.stat().st_size)),
                tags=(str(left or ""), str(right or "")))

    def _open(self, _event=None):
        selected = self.tree.selection()
        if selected:
            left, right = self.tree.item(selected[0], "tags")
            if left and right and Path(left).is_file() and Path(right).is_file(): self.open_detail(Path(left), Path(right))


class TableCompare(TextCompare):
    def __init__(self, master, left: Path, right: Path):
        def rows(path):
            delimiter = "\t" if path.suffix.casefold() == ".tsv" else ","
            with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
                return [" | ".join(row) for row in csv.reader(stream, delimiter=delimiter)]
        ttk.Frame.__init__(self, master)
        a, b = "\n".join(rows(left)), "\n".join(rows(right))
        aligned, differences = aligned_text(a, b)
        SideBySideText(self, [(r[0], r[1]) for r in aligned], [(r[2], r[3]) for r in aligned], differences,
                       f"{len(differences)} different row(s)").pack(fill="both", expand=True)


class CompareWindow(tk.Toplevel):
    def __init__(self, master, config, save_config):
        super().__init__(master)
        self.config_data, self.save_config = config, save_config
        self.title("PFC Compare")
        self.geometry(config.get("compare", "geometry", fallback="1400x850"))
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.notebook = ChamferNotebook(self); self.notebook.pack(fill="both", expand=True)
        self.bind("<F7>", lambda _e: self._navigate("previous"))
        self.bind("<F8>", lambda _e: self._navigate("next"))
        self.bind("<Escape>", lambda _e: self.close_active())

    def add(self, left: Path, right: Path, requested="Auto"):
        kind = detect_compare_type(left, right) if requested == "Auto" else requested
        if left.is_dir() != right.is_dir():
            messagebox.showerror("Compare", "Select two files or two folders.", parent=self); return
        if kind == "Folder": frame = FolderCompare(self.notebook, left, right, self.add)
        elif kind == "Text": frame = TextCompare(self.notebook, left, right)
        elif kind == "Table": frame = TableCompare(self.notebook, left, right)
        else: frame = BinaryCompare(self.notebook, left, right)
        self.notebook.add(frame, text=f"{kind}: {left.name} ↔ {right.name}")
        self.notebook.select(frame); self.deiconify(); self.lift(); self.focus_force()

    def _navigate(self, method):
        frame = self.nametowidget(self.notebook.select())
        for child in frame.winfo_children():
            if isinstance(child, SideBySideText): getattr(child, method)(); return

    def close(self):
        if not self.config_data.has_section("compare"): self.config_data.add_section("compare")
        self.config_data.set("compare", "geometry", self.geometry())
        self.save_config(); self.destroy()

    def close_active(self):
        tabs = self.notebook.tabs()
        if len(tabs) <= 1:
            self.close()
            return
        current = self.notebook.select()
        widget = self.nametowidget(current)
        self.notebook.forget(current)
        widget.destroy()
