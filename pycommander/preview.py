from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk
from .tooltip import install_button_tooltips
from .i18n import tr


TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".tsv", ".log", ".py", ".ini", ".json", ".xml",
    ".yaml", ".yml", ".html", ".htm", ".css", ".js", ".ps1", ".bat", ".cmd",
    ".sql", ".srt", ".cfg", ".conf",
}
TEXT_LIMIT = 8 * 1024 * 1024
HEX_LIMIT = 1024 * 1024


def looks_text(path: Path, sample: bytes) -> bool:
    if path.suffix.casefold() in TEXT_EXTENSIONS:
        return True
    if not sample:
        return True
    if sample.startswith((b"\xff\xfe", b"\xfe\xff", b"\xef\xbb\xbf")):
        return True
    return b"\x00" not in sample and sum(byte < 9 or 13 < byte < 32 for byte in sample) / len(sample) < 0.05


def decode_text(data: bytes) -> tuple[str, str]:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace"), "UTF-16"
    try:
        return data.decode("utf-8-sig"), "UTF-8"
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace"), "Windows-1252"


def render_hex(data: bytes) -> str:
    lines = []
    for offset in range(0, len(data), 16):
        chunk = data[offset:offset + 16]
        hexadecimal = " ".join(f"{byte:02X}" for byte in chunk)
        printable = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        lines.append(f"{offset:08X}  {hexadecimal:<47}  |{printable}|\n")
    return "".join(lines)


class PreviewWindow(tk.Toplevel):
    def __init__(self, master, config, save_config, files, selected) -> None:
        super().__init__(master)
        self.config_data, self.save_config = config, save_config
        self.files = list(files)
        self.index = self.files.index(selected) if selected in self.files else 0
        self.mode_values = {tr("Auto"): "Auto", tr("Text"): "Text", tr("Hex"): "Hex"}
        self.mode_var = tk.StringVar(value=tr("Auto"))
        self.wrap_var = tk.BooleanVar(value=config.getboolean("preview", "wrap", fallback=False))
        self.case_var = tk.BooleanVar(value=False)
        self.search_var = tk.StringVar()
        self.matches = []
        self.match_index = -1
        self._signature = None
        self._refresh_job = None
        self.title(tr("PFC Preview"))
        self.geometry(config.get("preview", "geometry", fallback="1100x720"))
        self.minsize(640, 400)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _event: self.close())
        self.bind("<Control-f>", lambda _event: self.focus_search())
        self.bind("<Alt-Left>", lambda _event: self.previous_file())
        self.bind("<Alt-Right>", lambda _event: self.next_file())

        toolbar = ttk.Frame(self, padding=(6, 5)); toolbar.pack(fill="x")
        file_row = ttk.Frame(toolbar); file_row.pack(fill="x")
        ttk.Button(file_row, text=tr("File <<"), command=self.previous_file).pack(side="left")
        ttk.Button(file_row, text=tr("File >>"), command=self.next_file).pack(side="left", padx=(3, 10))
        ttk.Label(file_row, text=tr("View:")).pack(side="left", padx=(4, 3))
        mode = ttk.Combobox(file_row, width=7, state="readonly", textvariable=self.mode_var,
                            values=tuple(self.mode_values))
        mode.pack(side="left"); mode.bind("<<ComboboxSelected>>", lambda _event: self.load())
        ttk.Checkbutton(file_row, text=tr("Wrap"), variable=self.wrap_var,
                        command=self.set_wrap).pack(side="left", padx=10)
        find_row = ttk.Frame(toolbar); find_row.pack(fill="x", pady=(4, 0))
        ttk.Label(find_row, text=tr("Find:")).pack(side="left", padx=(0, 3))
        self.search = ttk.Entry(find_row, textvariable=self.search_var, width=24)
        self.search.pack(side="left", fill="x", expand=True)
        self.search.bind("<Return>", lambda _event: self.find_next())
        self.search.bind("<Shift-Return>", lambda _event: self.find_previous())
        find_actions = ttk.Frame(toolbar); find_actions.pack(fill="x", pady=(3, 0))
        ttk.Button(find_actions, text=tr("Find Prev"), command=self.find_previous).pack(side="left")
        ttk.Button(find_actions, text=tr("Find Next"), command=self.find_next).pack(side="left", padx=(3, 0))
        ttk.Checkbutton(find_actions, text=tr("Case sensitive"), variable=self.case_var,
                        command=self.find_all).pack(side="left", padx=(8, 0))

        frame = ttk.Frame(self); frame.pack(fill="both", expand=True)
        self.text = tk.Text(frame, wrap="word" if self.wrap_var.get() else "none", undo=False,
                            font=tkfont.nametofont("TkFixedFont"), padx=8, pady=6)
        vertical = ttk.Scrollbar(frame, orient="vertical", command=self.text.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        horizontal.pack(side="bottom", fill="x")
        self.text.pack(side="left", fill="both", expand=True); vertical.pack(side="right", fill="y")
        self.text.tag_configure("match", background="#fff0a6")
        self.text.tag_configure("current_match", background="#ffb347")
        self.status = ttk.Label(self, anchor="w", padding=(7, 4)); self.status.pack(fill="x")
        install_button_tooltips(self)
        self.load()
        self._schedule_refresh()
        self.after_idle(self.activate)

    @property
    def path(self) -> Path:
        return self.files[self.index]

    def show(self, files, selected) -> None:
        self.files = list(files)
        self.index = self.files.index(selected) if selected in self.files else 0
        self.load(); self.activate()

    def activate(self) -> None:
        self.deiconify(); self.lift(); self.focus_force(); self.text.focus_set()

    def _path_signature(self):
        try:
            path = self.path
            if path.is_dir():
                return tuple(sorted((item.name, item.stat().st_mtime_ns, item.stat().st_size)
                                    for item in path.iterdir()))
            stat = path.stat(); return stat.st_mtime_ns, stat.st_size
        except OSError:
            return None

    def _schedule_refresh(self) -> None:
        self._refresh_job = self.after(2000, self._auto_refresh)

    def _auto_refresh(self) -> None:
        self._refresh_job = None
        signature = self._path_signature()
        if signature != self._signature:
            self.load()
        if self.winfo_exists(): self._schedule_refresh()

    def load(self) -> None:
        path = self.path
        self.title(f"{tr('PFC Preview')} — {path.name}")
        self.text.configure(state="normal"); self.text.delete("1.0", "end")
        mode = self.mode_values.get(self.mode_var.get(), self.mode_var.get())
        encoding, truncated = "", False
        try:
            if path.is_dir():
                entries = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
                content = f"{tr('Folder')}: {path}\n\n" + "\n".join(
                    ("[DIR]  " if item.is_dir() else "       ") + item.name for item in entries)
                shown_mode = tr("Folder view")
            else:
                size = path.stat().st_size
                with path.open("rb") as stream:
                    sample = stream.read(4096); stream.seek(0)
                    chosen = "Text" if mode == "Text" or (mode == "Auto" and looks_text(path, sample)) else "Hex"
                    limit = TEXT_LIMIT if chosen == "Text" else HEX_LIMIT
                    data = stream.read(limit + 1)
                truncated = len(data) > limit; data = data[:limit]
                if chosen == "Text":
                    content, encoding = decode_text(data); shown_mode = tr("Text")
                else:
                    content = render_hex(data); shown_mode = tr("Hex")
                size = path.stat().st_size
            self.text.insert("1.0", content)
            size = path.stat().st_size if path.is_file() else 0
            detail = f"{shown_mode}   {size:,} bytes"
            if encoding: detail += f"   {encoding}"
            if truncated: detail += "   Preview truncated"
            self.status.configure(text=f"{detail}   {path}")
        except OSError as exc:
            self.text.insert("1.0", f"{tr('Cannot preview file')}:\n{exc}")
            self.status.configure(text=str(path))
        self.text.configure(state="disabled")
        self._signature = self._path_signature()
        self.find_all()

    def set_wrap(self) -> None:
        self.text.configure(wrap="word" if self.wrap_var.get() else "none")

    def focus_search(self) -> str:
        self.search.focus_set(); self.search.selection_range(0, "end"); return "break"

    def find_all(self) -> None:
        self.text.tag_remove("match", "1.0", "end"); self.text.tag_remove("current_match", "1.0", "end")
        self.matches, self.match_index = [], -1
        needle = self.search_var.get()
        if not needle: return
        start = "1.0"
        while True:
            found = self.text.search(needle, start, stopindex="end", nocase=not self.case_var.get())
            if not found: break
            end = f"{found}+{len(needle)}c"; self.matches.append((found, end))
            self.text.tag_add("match", found, end); start = end

    def _find(self, direction: int) -> str:
        previous_index = self.match_index
        self.find_all()
        if not self.matches:
            self.status.configure(text=f"{tr('No matches')}   {self.path}"); return "break"
        self.match_index = (previous_index + direction) % len(self.matches)
        start, end = self.matches[self.match_index]
        self.text.tag_remove("current_match", "1.0", "end")
        self.text.tag_add("current_match", start, end); self.text.see(start)
        self.status.configure(text=f"{tr('Match {current} of {total}', current=self.match_index + 1, total=len(self.matches))}   {self.path}")
        return "break"

    def find_next(self) -> str: return self._find(1)
    def find_previous(self) -> str: return self._find(-1)

    def previous_file(self) -> None:
        if self.files: self.index = (self.index - 1) % len(self.files); self.load()

    def next_file(self) -> None:
        if self.files: self.index = (self.index + 1) % len(self.files); self.load()

    def close(self) -> None:
        if self._refresh_job is not None:
            self.after_cancel(self._refresh_job); self._refresh_job = None
        if not self.config_data.has_section("preview"): self.config_data.add_section("preview")
        self.config_data.set("preview", "geometry", self.geometry())
        self.config_data.set("preview", "wrap", str(self.wrap_var.get()).lower())
        self.save_config(); self.destroy()
