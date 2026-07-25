from __future__ import annotations

import fnmatch
import os
import queue
import threading
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

from .tooltip import install_button_tooltips
from .i18n import retranslate_widgets, tr
from .tabs import color_scheme


OFFICE_XML = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}
CONTENT_LIMIT = 32 * 1024 * 1024
RESULT_LIMIT = 10000


def search_row_height(linespace: int, scale: float) -> int:
    """Leave enough vertical padding for scaled Search result text."""
    return max(24, int(linespace) + max(8, round(6 * float(scale))))


def search_column_widths(available: int, desired: dict[str, int]) -> dict[str, int]:
    """Fit result columns while reserving useful space for both name and folder."""
    available = max(520, int(available))
    fixed = {
        "size": min(max(desired.get("size", 80), 72), 125),
        "modified": min(max(desired.get("modified", 150), 148), 200),
        "ext": min(max(desired.get("ext", 54), 48), 105),
    }
    flexible = max(280, available - sum(fixed.values()) - 8)
    wanted_name = min(max(desired.get("name", 160), 130), int(available * .48))
    wanted_folder = min(max(desired.get("folder", 220), 150), int(available * .52))
    wanted_total = wanted_name + wanted_folder
    if wanted_total <= flexible:
        name = wanted_name
        folder = flexible - name
    else:
        name = max(130, round(flexible * wanted_name / wanted_total))
        folder = max(150, flexible - name)
        if name + folder > flexible:
            name = max(130, flexible - folder)
    return {"name": name, "folder": folder, **fixed}


def name_matches(name: str, masks: str, case_sensitive: bool) -> bool:
    patterns = [part.strip() for part in masks.split(";") if part.strip()] or ["*"]
    patterns = [pattern if any(char in pattern for char in "*?[]") else f"*{pattern}*" for pattern in patterns]
    if not case_sensitive:
        name, patterns = name.casefold(), [pattern.casefold() for pattern in patterns]
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def content_matches(path: Path, needle: str, case_sensitive: bool) -> bool:
    if not needle: return True
    target = needle if case_sensitive else needle.casefold()
    try:
        if path.suffix.casefold() in OFFICE_XML and zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                chunks = []
                for info in archive.infolist():
                    if info.filename.endswith(".xml") and sum(map(len, chunks)) < CONTENT_LIMIT:
                        chunks.append(archive.read(info)[:CONTENT_LIMIT])
                data = b" ".join(chunks)[:CONTENT_LIMIT]
        else:
            with path.open("rb") as stream: data = stream.read(CONTENT_LIMIT)
        if b"\x00" in data[:4096] and not data.startswith((b"\xff\xfe", b"\xfe\xff")): return False
        if data.startswith((b"\xff\xfe", b"\xfe\xff")): text = data.decode("utf-16", errors="replace")
        else:
            try: text = data.decode("utf-8-sig")
            except UnicodeDecodeError: text = data.decode("cp1252", errors="replace")
        return target in (text if case_sensitive else text.casefold())
    except (OSError, zipfile.BadZipFile):
        return False


class SearchWindow(tk.Toplevel):
    def __init__(self, master, config, save_config, start_path, on_go, on_preview):
        super().__init__(master)
        self.config_data, self.save_config = config, save_config
        self.on_go, self.on_preview = on_go, on_preview
        self.results, self.worker = [], None
        self.item_data = {}
        self.sort_column, self.sort_reverse = "name", False
        self.cancel_event = threading.Event(); self.messages = queue.Queue(); self.poll_job = None
        self._column_resize_job = None
        self._column_desired = {}
        self.path_var = tk.StringVar(value=str(start_path))
        self.mask_var = tk.StringVar(value=config.get("search", "mask", fallback="*"))
        self.content_var = tk.StringVar(value=config.get("search", "content", fallback=""))
        self.case_var = tk.BooleanVar(value=config.getboolean("search", "case_sensitive", fallback=False))
        saved_depth = config.get("search", "depth", fallback="All")
        self.depth_values = {tr("Current"): "Current", "1": "1", "2": "2", "3": "3", "5": "5", tr("All"): "All"}
        self.depth_var = tk.StringVar(value=next((label for label, value in self.depth_values.items()
                                                  if value == saved_depth), tr("All")))
        self.files_var = tk.BooleanVar(value=config.getboolean("search", "files", fallback=True))
        self.folders_var = tk.BooleanVar(value=config.getboolean("search", "folders", fallback=True))
        self.min_size_var = tk.StringVar(value=config.get("search", "min_size_kb", fallback=""))
        self.max_size_var = tk.StringVar(value=config.get("search", "max_size_kb", fallback=""))
        self.days_var = tk.StringVar(value=config.get("search", "modified_days", fallback=""))
        self.title(tr("PFC Search")); self.geometry(config.get("search", "geometry", fallback="1100x720")); self.minsize(720, 480)
        self.protocol("WM_DELETE_WINDOW", self.close); self.bind("<Escape>", lambda _e: self.escape())
        self.bind("<F3>", lambda _e: self.preview_selected())

        form = ttk.Frame(self, padding=7); form.pack(fill="x")
        self.mask_entry = None
        for row, (label, variable) in enumerate((("Start in:", self.path_var), ("Name/mask:", self.mask_var),
                                                 ("Containing text:", self.content_var))):
            ttk.Label(form, text=tr(label)).grid(row=row, column=0, sticky="w", padx=(0, 5), pady=2)
            entry = ttk.Entry(form, textvariable=variable); entry.grid(row=row, column=1, columnspan=7, sticky="ew", pady=2)
            entry.bind("<Return>", lambda _event: self.start())
            if row == 1: self.mask_entry = entry
        options = ttk.Frame(form); options.grid(row=3, column=0, columnspan=8, sticky="ew", pady=(5, 2))
        ttk.Label(options, text=tr("Depth:")).pack(side="left")
        self.depth_combo = ttk.Combobox(options, textvariable=self.depth_var, state="readonly", width=8,
                                        values=tuple(self.depth_values))
        self.depth_combo.pack(side="left", padx=(3, 10))
        ttk.Checkbutton(options, text=tr("Files"), variable=self.files_var).pack(side="left")
        ttk.Checkbutton(options, text=tr("Folders"), variable=self.folders_var).pack(side="left", padx=(3, 10))
        ttk.Checkbutton(options, text=tr("Case sensitive"), variable=self.case_var).pack(side="left")
        advanced = ttk.Frame(form); advanced.grid(row=4, column=0, columnspan=8, sticky="ew", pady=2)
        ttk.Label(advanced, text=tr("Size KB min:")).pack(side="left")
        ttk.Entry(advanced, textvariable=self.min_size_var, width=9).pack(side="left", padx=(3, 8))
        ttk.Label(advanced, text=tr("max:")).pack(side="left")
        ttk.Entry(advanced, textvariable=self.max_size_var, width=9).pack(side="left", padx=(3, 12))
        ttk.Label(advanced, text=tr("Modified within days:")).pack(side="left")
        ttk.Entry(advanced, textvariable=self.days_var, width=7).pack(side="left", padx=3)
        self.criteria_label = ttk.Label(form, anchor="w")
        self.criteria_label.grid(row=5, column=0, columnspan=8, sticky="ew", pady=(4, 0))
        actions = ttk.Frame(form); actions.grid(row=6, column=0, columnspan=8, sticky="ew", pady=(5, 0))
        self.find_button = ttk.Button(actions, text=tr("Find"), command=self.start); self.find_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text=tr("Cancel"), command=self.cancel, state="disabled"); self.cancel_button.pack(side="left", padx=3)
        ttk.Button(actions, text=tr("Clear Filters"), command=self.clear_filters).pack(side="left", padx=(3, 9))
        ttk.Button(actions, text=tr("Go to File"), command=self.go_selected).pack(side="left", padx=(12, 3))
        ttk.Button(actions, text=tr("Preview"), command=self.preview_selected).pack(side="left")
        ttk.Button(actions, text=tr("Copy Path"), command=self.copy_paths).pack(side="left", padx=3)
        self.status = ttk.Label(actions, anchor="e"); self.status.pack(side="right", fill="x", expand=True)
        form.columnconfigure(1, weight=1)

        body = ttk.Frame(self); body.pack(fill="both", expand=True)
        columns = ("folder", "size", "modified", "ext")
        self.tree = ttk.Treeview(body, columns=columns, show="tree headings", selectmode="extended",
                                 style="PFCSearch.Treeview")
        self.tree.heading("#0", text=tr("Name") + " ▲", command=lambda: self.change_sort("name")); self.tree.column("#0", width=260, stretch=False)
        for col, width in (("folder", 460), ("size", 90), ("modified", 140), ("ext", 60)):
            self.tree.heading(col, text=tr(col.title()), command=lambda c=col: self.change_sort(c))
            self.tree.column(col, width=width, anchor="e" if col == "size" else "w", stretch=False)
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview); self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True); scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _e: self.go_selected())
        self.tree.bind("<Return>", lambda _e: self.go_selected())
        self.tree.bind("<Configure>", self._schedule_column_resize)
        for variable in (self.mask_var, self.content_var, self.case_var, self.depth_var,
                         self.files_var, self.folders_var, self.min_size_var,
                         self.max_size_var, self.days_var):
            variable.trace_add("write", self._update_criteria_summary)
        self._update_criteria_summary()
        self.apply_color_scheme(getattr(master, "palette", color_scheme("light")))
        install_button_tooltips(self); self.after_idle(self.activate)

    def _reset_column_measurements(self) -> None:
        font = tkfont.nametofont("TkDefaultFont")
        heading = tkfont.nametofont("TkHeadingFont")
        self._column_desired = {
            "name": heading.measure(tr("Name") + " ▲") + 32,
            "folder": heading.measure(tr("Folder")) + 32,
            "size": heading.measure(tr("Size")) + 28,
            "modified": heading.measure(tr("Modified")) + 28,
            "ext": heading.measure(tr("Ext")) + 28,
        }
        for iid in self.tree.get_children():
            values = self.tree.item(iid, "values")
            if len(values) >= 4:
                self._measure_result(str(self.tree.item(iid, "text")), *map(str, values[:4]),
                                     schedule=False)
        self._schedule_column_resize()

    def _measure_result(self, name: str, folder: str, size: str, modified: str, ext: str,
                        schedule: bool = True) -> None:
        font = tkfont.nametofont("TkDefaultFont")
        for key, value in (("name", name), ("folder", folder), ("size", size),
                           ("modified", modified), ("ext", ext)):
            self._column_desired[key] = max(self._column_desired.get(key, 0),
                                            font.measure(value) + (38 if key == "name" else 24))
        if schedule:
            self._schedule_column_resize()

    def _schedule_column_resize(self, _event=None) -> None:
        if self._column_resize_job is not None:
            self.after_cancel(self._column_resize_job)
        self._column_resize_job = self.after(90, self._resize_columns)

    def _resize_columns(self) -> None:
        self._column_resize_job = None
        widths = search_column_widths(self.tree.winfo_width(), self._column_desired)
        self.tree.column("#0", width=widths["name"])
        for column in ("folder", "size", "modified", "ext"):
            self.tree.column(column, width=widths[column])

    def apply_color_scheme(self, palette) -> None:
        self.palette = palette
        self.configure(background=palette["window"])

    def apply_scale(self, scale: float) -> None:
        style = ttk.Style(self)
        default_font = tkfont.nametofont("TkDefaultFont")
        style.configure("PFCSearch.Treeview", font=default_font,
                        rowheight=search_row_height(default_font.metrics("linespace"), scale))
        style.configure("PFCSearch.Treeview.Heading", font=tkfont.nametofont("TkHeadingFont"))
        self._reset_column_measurements()

    def apply_language(self, old_language: str) -> None:
        depth = self.depth_values.get(self.depth_var.get(), self.depth_var.get())
        retranslate_widgets(self, old_language)
        self.depth_values = {tr("Current"): "Current", "1": "1", "2": "2", "3": "3",
                             "5": "5", tr("All"): "All"}
        self.depth_combo.configure(values=tuple(self.depth_values))
        self.depth_var.set(next(label for label, value in self.depth_values.items() if value == depth))
        self.title(tr("PFC Search"))
        self._apply_sort()
        self._reset_column_measurements()
        self._update_criteria_summary()
        if self.worker is not None and self.worker.is_alive():
            self.status.configure(text=tr("Searching…"))
        elif self.results:
            self.status.configure(text=tr("{count} found", count=len(self.results)))

    def activate(self):
        self.deiconify(); self.lift(); self.focus_force()
        self._update_criteria_summary()
        if self.mask_entry is not None:
            self.mask_entry.focus_set(); self.mask_entry.selection_range(0, "end"); self.mask_entry.icursor("end")

    def _update_criteria_summary(self, *_args) -> None:
        if not hasattr(self, "criteria_label"):
            return
        mask = self.mask_var.get().strip() or "*"
        scope = "/".join(label for label, enabled in (
            (tr("Files"), self.files_var.get()), (tr("Folders"), self.folders_var.get())) if enabled) or "—"
        parts = [f"{tr('Name/mask:')} {mask}", scope,
                 f"{tr('Depth:')} {self.depth_var.get()}"]
        if self.content_var.get().strip():
            parts.append(f"{tr('Containing text:')} {self.content_var.get().strip()}")
        if self.min_size_var.get().strip() or self.max_size_var.get().strip():
            parts.append(f"{tr('Size')}: {self.min_size_var.get().strip() or '0'}–{self.max_size_var.get().strip() or '∞'} KB")
        if self.days_var.get().strip():
            parts.append(f"{tr('Modified within days:')} {self.days_var.get().strip()}")
        if self.case_var.get():
            parts.append(tr("Case sensitive"))
        self.criteria_label.configure(text=f"{tr('Filters:')} " + " · ".join(parts))

    def clear_filters(self) -> None:
        self.mask_var.set("*")
        self.content_var.set("")
        self.case_var.set(False)
        self.depth_var.set(tr("All"))
        self.files_var.set(True)
        self.folders_var.set(True)
        self.min_size_var.set("")
        self.max_size_var.set("")
        self.days_var.set("")
        self.status.configure(text=tr("Filters cleared"))
        self.mask_entry.focus_set()
        self.mask_entry.selection_range(0, "end")

    def change_sort(self, column):
        self.sort_reverse = not self.sort_reverse if self.sort_column == column else False
        self.sort_column = column
        self._apply_sort()

    def _apply_sort(self):
        column = self.sort_column
        labels = {"name": tr("Name"), "folder": tr("Folder"), "size": tr("Size"),
                  "modified": tr("Modified"), "ext": tr("Ext")}
        for name, label in labels.items():
            marker = (" ▲" if not self.sort_reverse else " ▼") if name == column else ""
            self.tree.heading("#0" if name == "name" else name, text=label + marker)
        for index, iid in enumerate(sorted(self.tree.get_children(),
                                            key=lambda item: self.item_data[item][column],
                                            reverse=self.sort_reverse)):
            self.tree.move(iid, "", index)

    def criteria(self):
        def number(value, factor=1):
            try: return float(value) * factor if value.strip() else None
            except ValueError: return None
        depth = self.depth_values.get(self.depth_var.get(), self.depth_var.get())
        max_depth = None if depth == "All" else (0 if depth == "Current" else int(depth))
        days = number(self.days_var.get())
        return dict(root=Path(self.path_var.get().strip().strip('"')), masks=self.mask_var.get(), content=self.content_var.get(),
                    case=self.case_var.get(), max_depth=max_depth, files=self.files_var.get(), folders=self.folders_var.get(),
                    min_size=number(self.min_size_var.get(), 1024), max_size=number(self.max_size_var.get(), 1024),
                    since=datetime.now() - timedelta(days=days) if days is not None else None)

    def start(self):
        if self.worker and self.worker.is_alive(): return
        criteria = self.criteria()
        if not criteria["root"].is_dir(): messagebox.showerror(tr("Search"), tr("Start path is not a folder."), parent=self); return
        self.tree.delete(*self.tree.get_children()); self.results=[]; self.item_data.clear(); self.cancel_event.clear()
        self._reset_column_measurements()
        self.find_button.configure(state="disabled"); self.cancel_button.configure(state="normal"); self.status.configure(text=tr("Searching…"))
        self.worker = threading.Thread(target=self._search, args=(criteria,), daemon=True); self.worker.start(); self._poll()

    def _search(self, c):
        count = 0
        try:
            for current, dirs, files in os.walk(c["root"]):
                if self.cancel_event.is_set(): break
                depth = len(Path(current).relative_to(c["root"]).parts)
                folder_names = list(dirs)
                if c["max_depth"] is not None and depth >= c["max_depth"]: dirs[:] = []
                candidates = ([Path(current) / name for name in folder_names] if c["folders"] else []) + ([Path(current) / name for name in files] if c["files"] else [])
                for path in candidates:
                    if self.cancel_event.is_set() or count >= RESULT_LIMIT: break
                    try:
                        stat = path.stat()
                        if not name_matches(path.name, c["masks"], c["case"]): continue
                        if path.is_file() and c["min_size"] is not None and stat.st_size < c["min_size"]: continue
                        if path.is_file() and c["max_size"] is not None and stat.st_size > c["max_size"]: continue
                        if c["since"] is not None and datetime.fromtimestamp(stat.st_mtime) < c["since"]: continue
                        if path.is_file() and not content_matches(path, c["content"], c["case"]): continue
                        if path.is_dir() and c["content"]: continue
                        self.messages.put(("item", path, stat)); count += 1
                    except OSError: continue
            self.messages.put(("done", count, self.cancel_event.is_set(), count >= RESULT_LIMIT))
        except OSError as exc: self.messages.put(("error", str(exc)))

    def _poll(self):
        processed = 0
        while processed < 250:
            try: message = self.messages.get_nowait()
            except queue.Empty: break
            processed += 1
            if message[0] == "item":
                _, path, stat = message; self.results.append(path)
                folder = str(path.parent)
                size_text = "<DIR>" if path.is_dir() else f"{stat.st_size:,}"
                modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                extension = "" if path.is_dir() else path.suffix[1:]
                iid = self.tree.insert("", "end", text=path.name, tags=(str(path),),
                                       values=(folder, size_text, modified, extension))
                self._measure_result(path.name, folder, size_text, modified, extension)
                self.item_data[iid] = {"name": path.name.casefold(), "folder": str(path.parent).casefold(),
                                       "size": stat.st_size, "modified": stat.st_mtime,
                                       "ext": ("" if path.is_dir() else path.suffix[1:]).casefold()}
                self.status.configure(text=tr("{count} found", count=len(self.results)))
            elif message[0] == "done":
                _, count, cancelled, limited = message
                suffix = tr(" — cancelled") if cancelled else (tr(" — limit reached") if limited else "")
                self.status.configure(text=tr("{count} found", count=count) + suffix); self.find_button.configure(state="normal"); self.cancel_button.configure(state="disabled")
                self._apply_sort()
            elif message[0] == "error":
                self.find_button.configure(state="normal"); self.cancel_button.configure(state="disabled")
                messagebox.showerror(tr("Search failed"), message[1], parent=self)
        if not self.messages.empty() or (self.worker and self.worker.is_alive()):
            self.poll_job = self.after(40, self._poll)

    def selected_paths(self):
        return [Path(self.tree.item(iid, "tags")[0]) for iid in self.tree.selection()
                if self.tree.item(iid, "tags")]
    def go_selected(self):
        paths=self.selected_paths()
        if paths:
            self.on_go(paths[0])
            try: self.lower(self.master)
            except tk.TclError: pass
    def preview_selected(self):
        paths=self.selected_paths()
        if paths:
            ordered = [Path(self.tree.item(iid, "tags")[0]) for iid in self.tree.get_children()
                       if self.tree.item(iid, "tags")]
            self.on_preview(ordered, paths[0])
    def copy_paths(self):
        paths=self.selected_paths()
        if paths: self.clipboard_clear(); self.clipboard_append("\n".join(map(str, paths))); self.update_idletasks()
    def cancel(self): self.cancel_event.set(); self.status.configure(text=tr("Cancelling…"))
    def escape(self): self.cancel() if self.worker and self.worker.is_alive() else self.close()
    def close(self):
        self.cancel_event.set()
        if self.poll_job is not None:
            try: self.after_cancel(self.poll_job)
            except tk.TclError: pass
        if self._column_resize_job is not None:
            try: self.after_cancel(self._column_resize_job)
            except tk.TclError: pass
        if not self.config_data.has_section("search"): self.config_data.add_section("search")
        for key, value in (("geometry", self.geometry()), ("mask", self.mask_var.get()), ("content", self.content_var.get()),
                           ("case_sensitive", str(self.case_var.get()).lower()),
                           ("depth", self.depth_values.get(self.depth_var.get(), self.depth_var.get())),
                           ("files", str(self.files_var.get()).lower()), ("folders", str(self.folders_var.get()).lower()),
                           ("min_size_kb", self.min_size_var.get()), ("max_size_kb", self.max_size_var.get()),
                           ("modified_days", self.days_var.get())):
            self.config_data.set("search", key, value)
        self.save_config(); self.destroy()
