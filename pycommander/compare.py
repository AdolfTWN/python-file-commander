from __future__ import annotations

import csv
import difflib
import fnmatch
import hashlib
import os
import queue
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from .tabs import ChamferNotebook
from .tooltip import install_button_tooltips
from .i18n import tr


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
        self.matches, self.match_index = [], -1
        self.search_var, self.case_var = tk.StringVar(), tk.BooleanVar(value=False)
        toolbar = ttk.Frame(self); toolbar.pack(fill="x")
        diff_row = ttk.Frame(toolbar); diff_row.pack(fill="x")
        ttk.Button(diff_row, text=f"F7 {tr('Diff <<')}", command=self.previous).pack(side="left")
        ttk.Button(diff_row, text=f"F8 {tr('Diff >>')}", command=self.next).pack(side="left", padx=3)
        ttk.Label(diff_row, text=status_text).pack(side="left", padx=10)
        find_row = ttk.Frame(toolbar); find_row.pack(fill="x", pady=(3, 2))
        ttk.Label(find_row, text=tr("Find:")).pack(side="left")
        self.search = ttk.Entry(find_row, textvariable=self.search_var)
        self.search.pack(side="left", fill="x", expand=True, padx=(3, 4))
        self.search.bind("<Return>", lambda _event: self.find_next())
        self.search.bind("<Shift-Return>", lambda _event: self.find_previous())
        self.find_status = ttk.Label(find_row, width=12, anchor="e")
        self.find_status.pack(side="right", padx=(8, 3))
        find_actions = ttk.Frame(toolbar); find_actions.pack(fill="x", pady=(0, 2))
        ttk.Button(find_actions, text=tr("Find Prev"), command=self.find_previous).pack(side="left")
        ttk.Button(find_actions, text=tr("Find Next"), command=self.find_next).pack(side="left", padx=(3, 0))
        ttk.Checkbutton(find_actions, text=tr("Case sensitive"), variable=self.case_var,
                        command=self.find_all).pack(side="left", padx=(8, 0))
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
            widget.tag_configure("match", background="#fff0a6")
            widget.tag_configure("current_match", background="#ff9f43")
            for display_row, item in enumerate(lines, 1):
                source_number, line = item if isinstance(item, tuple) else (display_row, item)
                number_text = "" if source_number is None else str(source_number)
                widget.insert("end", f"{number_text:>6}  {line}\n", "diff" if display_row in differences else "")
            widget.configure(state="disabled")

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
                              tr("{count} different line(s)", count=len(differences)))
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
        status = tr("SHA-256: {result}; first offset: {offset}",
                    result=tr("identical") if file_hash(left) == file_hash(right) else tr("different"),
                    offset=f"0x{different_offsets[0]:X}" if different_offsets else tr("none"))
        SideBySideText(self, left_lines, right_lines, diff_lines, status).pack(fill="both", expand=True)


def folder_rows(left: Path, right: Path, recursive=True, masks="*", by_content=False,
                cancelled=lambda: False):
    patterns = [item.strip() for item in masks.split(";") if item.strip()] or ["*"]
    def collect(root):
        iterator = root.rglob("*") if recursive else root.iterdir()
        result = {}
        for path in iterator:
            if cancelled():
                break
            relative = str(path.relative_to(root))
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
                if a_stat.st_size != b_stat.st_size:
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


class FolderCompare(ttk.Frame):
    def __init__(self, master, left: Path, right: Path, open_detail, sync_executor=None):
        super().__init__(master)
        self.left_root, self.right_root = left, right
        self.open_detail, self.sync_executor = open_detail, sync_executor
        self.rows, self.actions, self.item_paths, self.item_keys = [], {}, {}, {}
        self.matches, self.match_index = [], -1
        self._scan_queue, self._cancel_event, self._scanning = queue.Queue(), threading.Event(), False
        self.sort_column, self.sort_reverse = "path", False
        paths = ttk.Frame(self); paths.pack(fill="x", pady=(2, 1))
        ttk.Label(paths, text=f"{tr('Left')}: {left}").pack(side="left", fill="x", expand=True)
        ttk.Label(paths, text=f"{tr('Right')}: {right}").pack(side="right", fill="x", expand=True)
        bar = ttk.Frame(self); bar.pack(fill="x")
        ttk.Label(bar, text=tr("Mask:")).pack(side="left")
        self.mask_var = tk.StringVar(value="*")
        ttk.Entry(bar, textvariable=self.mask_var, width=20).pack(side="left", fill="x", expand=True, padx=(3, 8))
        ttk.Button(bar, text=tr("Compare"), command=self.start_scan).pack(side="left", padx=(0, 2))
        ttk.Button(bar, text=tr("Cancel"), command=self.cancel_scan).pack(side="left")
        options = ttk.Frame(self); options.pack(fill="x", pady=(2, 1))
        self.recursive_var = tk.BooleanVar(value=True)
        self.content_var = tk.BooleanVar(value=False)
        self.differences_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options, text=tr("Recursive"), variable=self.recursive_var).pack(side="left")
        ttk.Checkbutton(options, text=tr("By content"), variable=self.content_var).pack(side="left", padx=(5, 0))
        ttk.Checkbutton(options, text=tr("Differences only"), variable=self.differences_var,
                        command=self.populate).pack(side="left", padx=(5, 0))
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
        self.tree = ttk.Treeview(self, columns=("action", "status", "path", "left", "right"),
                                 show="headings", selectmode="extended")
        for col, width in (("action", 70), ("status", 105), ("path", 390), ("left", 125), ("right", 125)):
            self.tree.heading(col, text=tr(col.title()), command=lambda value=col: self.change_sort(value))
            self.tree.column(col, width=width, anchor="center" if col == "action" else "w")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("find_match", background="#fff0a6")
        self.tree.tag_configure("current_match", background="#ff9f43")
        self.tree.tag_configure("different", foreground="#a00000")
        self.tree.tag_configure("left", foreground="#006c3b")
        self.tree.tag_configure("right", foreground="#005ca8")
        self.tree.bind("<Double-1>", self._open)
        self.tree.bind("<Return>", self._open)
        self.tree.bind("<Control-Right>", lambda _e: self.set_action("right"))
        self.tree.bind("<Control-Left>", lambda _e: self.set_action("left"))
        self.tree.bind("<space>", lambda _e: self.set_action("skip"))
        self.start_scan()

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
        cancel = self._cancel_event
        def worker():
            try:
                rows = list(folder_rows(self.left_root, self.right_root, recursive, masks, by_content,
                                        cancel.is_set))
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
        children = self.tree.get_children()
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
        for value in ("action", "status", "path", "left", "right"):
            marker = (" ▼" if self.sort_reverse else " ▲") if value == column else ""
            self.tree.heading(value, text=tr(value.title()) + marker)
        self.populate()
        for iid in self.tree.get_children():
            if self.item_keys.get(iid) in selected_keys:
                self.tree.selection_add(iid); self.tree.focus(iid); self.tree.see(iid)
        self.tree.focus_set()

    def populate(self):
        self.tree.delete(*self.tree.get_children())
        self.item_paths, self.item_keys = {}, {}
        action_label = {"right": "→", "left": "←", "skip": tr("Skip")}
        visible = [row for row in self.rows if not (self.differences_var.get() and row[0] == "Identical")]
        index = {"status": 0, "path": 1, "left": 2, "right": 3}
        if self.sort_column == "action":
            visible.sort(key=lambda row: self.actions.get(row[1], ""), reverse=self.sort_reverse)
        elif self.sort_column in {"left", "right"}:
            path_index = index[self.sort_column]
            def metadata_key(row):
                path = row[path_index]
                if path is None: return (0, 0, 0)
                try:
                    stat = path.stat(); return (2 if path.is_dir() else 1, stat.st_size, stat.st_mtime_ns)
                except OSError:
                    return (0, 0, 0)
            visible.sort(key=metadata_key, reverse=self.sort_reverse)
        else:
            visible.sort(key=lambda row: str(row[index[self.sort_column]]).casefold(), reverse=self.sort_reverse)
        for status, path, left, right in visible:
            tag = "left" if status in {"Left only", "Left newer"} else (
                "right" if status in {"Right only", "Right newer"} else "different")
            iid = self.tree.insert("", "end", values=(action_label.get(self.actions.get(path), ""),
                tr(status), path, self._detail(left), self._detail(right)), tags=(tag,))
            self.item_paths[iid] = (left, right)
            self.item_keys[iid] = path
        self.find_all()

    def set_action(self, action):
        selected = self.tree.selection()
        selected_keys = {self.item_keys.get(iid) for iid in selected}
        for iid in selected:
            left, right = self.item_paths.get(iid, (None, None)); key = self.item_keys.get(iid)
            if key is None: continue
            if action == "right" and left is not None:
                self.actions[key] = action
            elif action == "left" and right is not None:
                self.actions[key] = action
            elif action == "skip":
                self.actions[key] = action
        self.populate()
        for iid in self.tree.get_children():
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
        for iid in self.tree.get_children():
            base = next((tag for tag in self.tree.item(iid, "tags")
                         if tag in {"left", "right", "different"}), "different")
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
                       tr("{count} different row(s)", count=len(differences))).pack(fill="both", expand=True)


class CompareWindow(tk.Toplevel):
    def __init__(self, master, config, save_config, sync_executor=None):
        super().__init__(master)
        self.config_data, self.save_config = config, save_config
        self.sync_executor = sync_executor
        self.comparisons = {}
        self._refresh_job = None
        self.title(tr("PFC Compare"))
        self.geometry(config.get("compare", "geometry", fallback="1400x850"))
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.notebook = ChamferNotebook(self); self.notebook.pack(fill="both", expand=True)
        self.bind("<F7>", lambda _e: self._navigate("previous"))
        self.bind("<F8>", lambda _e: self._navigate("next"))
        self.bind("<Control-f>", lambda _e: self.focus_search())
        self.bind("<Escape>", lambda _e: self.close_active())
        install_button_tooltips(self)
        self._schedule_refresh()

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
            return FolderCompare(self.notebook, left, right, self.add, self.sync_executor)
        if kind == "Text": return TextCompare(self.notebook, left, right)
        if kind == "Table": return TableCompare(self.notebook, left, right)
        return BinaryCompare(self.notebook, left, right)

    def add(self, left: Path, right: Path, requested="Auto"):
        kind = detect_compare_type(left, right) if requested == "Auto" else requested
        if left.is_dir() != right.is_dir():
            messagebox.showerror(tr("Compare"), tr("Select two files or two folders."), parent=self); return
        frame = self._make_frame(left, right, kind)
        install_button_tooltips(frame)
        self.notebook.add(frame, text=f"{tr(kind)}: {left.name} ↔ {right.name}")
        self.comparisons[frame] = (left, right, kind, self._signature(left, right))
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
        if self.winfo_exists(): self._schedule_refresh()

    def _navigate(self, method):
        frame = self.nametowidget(self.notebook.select())
        for child in frame.winfo_children():
            if isinstance(child, SideBySideText): getattr(child, method)(); return

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

    def close_active(self):
        tabs = self.notebook.tabs()
        current = self.notebook.select()
        widget = self.nametowidget(current)
        if hasattr(widget, "cancel_scan") and widget.cancel_scan():
            return
        if len(tabs) <= 1:
            self.close()
            return
        self.notebook.forget(current)
        self.comparisons.pop(widget, None)
        widget.destroy()
