from __future__ import annotations

import io
import keyword
import re
import tokenize
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk
from .tooltip import install_button_tooltips
from .i18n import retranslate_widgets, tr
from .tabs import color_scheme


TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".tsv", ".log", ".py", ".ini", ".json", ".xml",
    ".yaml", ".yml", ".html", ".htm", ".css", ".js", ".ps1", ".bat", ".cmd",
    ".sql", ".srt", ".cfg", ".conf",
}
TEXT_LIMIT = 8 * 1024 * 1024
HEX_LIMIT = 1024 * 1024
SYNTAX_BATCH_SIZE = 600

CODE_EXTENSIONS = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++",
    ".cs": "C#", ".go": "Go", ".rs": "Rust", ".php": "PHP",
    ".sql": "SQL", ".ps1": "PowerShell", ".sh": "Shell",
    ".bat": "Batch", ".cmd": "Batch", ".json": "JSON",
    ".xml": "XML", ".html": "HTML", ".htm": "HTML", ".xhtml": "HTML",
    ".svg": "SVG", ".css": "CSS", ".scss": "SCSS",
    ".yaml": "YAML", ".yml": "YAML", ".ini": "INI",
    ".cfg": "Config", ".conf": "Config", ".md": "Markdown",
}

COMMON_KEYWORDS = set("""
abstract as async await break case catch class const continue def default delete do
else enum except export extends false finally for from function if import in
interface lambda let match namespace new nil none null package pass private
protected public raise return self static struct super switch this throw true try
type typeof using var void while with yield select range where
""".split())


def _line_offsets(text: str) -> list[int]:
    offsets, total = [0], 0
    for line in text.splitlines(keepends=True):
        total += len(line); offsets.append(total)
    return offsets


def syntax_spans(text: str, suffix: str) -> list[tuple[int, int, str]]:
    """Return lightweight syntax spans without requiring third-party packages."""
    suffix = suffix.casefold()
    if suffix == ".py":
        offsets = _line_offsets(text)
        spans = []
        try:
            for token in tokenize.generate_tokens(io.StringIO(text).readline):
                if token.type not in (tokenize.COMMENT, tokenize.STRING, tokenize.NUMBER,
                                      tokenize.NAME, tokenize.OP):
                    continue
                tag = {
                    tokenize.COMMENT: "syntax_comment", tokenize.STRING: "syntax_string",
                    tokenize.NUMBER: "syntax_number", tokenize.OP: "syntax_operator",
                }.get(token.type)
                if token.type == tokenize.NAME and keyword.iskeyword(token.string):
                    tag = "syntax_keyword"
                if tag and token.start[0] <= len(offsets) and token.end[0] <= len(offsets):
                    start = offsets[token.start[0] - 1] + token.start[1]
                    end = offsets[token.end[0] - 1] + token.end[1]
                    spans.append((start, end, tag))
        except (tokenize.TokenError, IndentationError):
            pass
        return spans

    spans = []
    comment_pattern = (r"(?m)(?://|;|--).*?$|/\*[\s\S]*?\*/|<!--[\s\S]*?-->"
                       if suffix == ".md" else
                       r"(?m)(?://|#|;|--).*?$|/\*[\s\S]*?\*/|<!--[\s\S]*?-->")
    patterns = [
        ("syntax_comment", comment_pattern),
        ("syntax_string", r"""(?s:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')"""),
        ("syntax_number", r"\b(?:0x[0-9a-fA-F]+|\d+(?:\.\d+)?)\b"),
    ]
    if suffix in {".xml", ".html", ".htm", ".xhtml", ".svg"}:
        patterns.append(("syntax_keyword", r"</?[\w:-]+|/?>"))
    elif suffix == ".md":
        patterns.extend([
            ("syntax_heading", r"(?m)^#{1,6}\s+.*$"),
            ("syntax_keyword", r"(?m)^(?:\s*[-*+]\s+|\s*\d+\.\s+|>\s+)|`{1,3}"),
            ("syntax_link", r"\[[^\]]+\]\([^)]+\)"),
        ])
    else:
        words = COMMON_KEYWORDS
        patterns.append(("syntax_keyword", r"\b(?:" + "|".join(sorted(map(re.escape, words))) + r")\b"))
    occupied = [False] * len(text)
    for tag, pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start, end = match.span()
            if start < end and not any(occupied[start:end]):
                spans.append((start, end, tag))
                occupied[start:end] = [True] * (end - start)
    return spans


def render_markdown(text: str) -> tuple[str, list[tuple[int, int, str]]]:
    """Render common Markdown structure into readable Tk text and style spans."""
    output, spans, in_code, length = [], [], False, 0

    def append(value: str, tag: str | None = None) -> None:
        nonlocal length
        start = length; output.append(value); length += len(value)
        if tag and value: spans.append((start, start + len(value), tag))

    def inline(value: str) -> None:
        pattern = re.compile(r"(\*\*.+?\*\*|__.+?__|`[^`]+`|\[[^\]]+\]\([^)]+\)|(?<!\*)\*[^*]+\*)")
        cursor = 0
        for match in pattern.finditer(value):
            append(value[cursor:match.start()])
            token = match.group()
            if token.startswith(("**", "__")):
                append(token[2:-2], "markdown_bold")
            elif token.startswith("`"):
                append(token[1:-1], "markdown_code")
            elif token.startswith("["):
                label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", token).groups()
                append(label, "markdown_link"); append(f" ({url})", "markdown_url")
            else:
                append(token[1:-1], "markdown_italic")
            cursor = match.end()
        append(value[cursor:])

    for raw in text.splitlines():
        if raw.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            append(raw + "\n", "markdown_code")
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", raw)
        if heading:
            start = length; inline(heading.group(2)); append("\n")
            spans.append((start, length - 1,
                          f"markdown_h{min(3, len(heading.group(1)))}"))
        elif re.match(r"^\s*[-*+]\s+", raw):
            append("• ", "markdown_bullet"); inline(re.sub(r"^\s*[-*+]\s+", "", raw)); append("\n")
        elif raw.startswith(">"):
            append("│ ", "markdown_quote"); inline(raw[1:].lstrip()); append("\n")
        elif re.match(r"^\s*(?:---+|\*\*\*+)\s*$", raw):
            append("────────────────────────\n", "markdown_rule")
        else:
            inline(raw); append("\n")
    return "".join(output), spans


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
    def __init__(self, master, config, save_config, files, selected,
                 extension_effect: bool = True) -> None:
        super().__init__(master)
        self.config_data, self.save_config = config, save_config
        self.files = list(files)
        self.index = self.files.index(selected) if selected in self.files else 0
        self.mode_values = {tr("Auto"): "Auto", tr("Text"): "Text", tr("Hex"): "Hex"}
        self.mode_var = tk.StringVar(value=tr("Auto"))
        self.wrap_var = tk.BooleanVar(value=config.getboolean("preview", "wrap", fallback=False))
        self.case_var = tk.BooleanVar(value=False)
        self.search_var = tk.StringVar()
        self.extension_effect = bool(extension_effect)
        self.markdown_values = {tr("Markdown Source"): "source", tr("Rendered"): "rendered"}
        self.markdown_var = tk.StringVar(value=tr("Rendered"))
        self.matches = []
        self.match_index = -1
        self._signature = None
        self._refresh_job = None
        self._span_job = None
        self._pending_spans = []
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
        self.mode_combo = ttk.Combobox(file_row, width=7, state="readonly", textvariable=self.mode_var,
                                       values=tuple(self.mode_values))
        self.mode_combo.pack(side="left")
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _event: self.load())
        ttk.Checkbutton(file_row, text=tr("Wrap"), variable=self.wrap_var,
                        command=self.set_wrap).pack(side="left", padx=10)
        self.markdown_frame = ttk.Frame(file_row)
        ttk.Label(self.markdown_frame, text="Markdown:").pack(side="left", padx=(2, 3))
        self.markdown_combo = ttk.Combobox(self.markdown_frame, width=10, state="readonly",
                                           textvariable=self.markdown_var,
                                           values=tuple(self.markdown_values))
        self.markdown_combo.pack(side="left")
        self.markdown_combo.bind("<<ComboboxSelected>>", lambda _event: self.load())
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
        self._configure_effect_fonts()
        self.status = ttk.Label(self, anchor="w", padding=(7, 4)); self.status.pack(fill="x")
        self.apply_color_scheme(getattr(master, "palette", color_scheme("light")))
        install_button_tooltips(self)
        self.load()
        self._schedule_refresh()
        self.after_idle(self.activate)

    def apply_language(self, old_language: str) -> None:
        mode = self.mode_values.get(self.mode_var.get(), self.mode_var.get())
        retranslate_widgets(self, old_language)
        self.mode_values = {tr("Auto"): "Auto", tr("Text"): "Text", tr("Hex"): "Hex"}
        self.mode_combo.configure(values=tuple(self.mode_values))
        self.mode_var.set(next(label for label, value in self.mode_values.items() if value == mode))
        markdown_mode = self.markdown_values.get(self.markdown_var.get(), "rendered")
        self.markdown_values = {tr("Markdown Source"): "source", tr("Rendered"): "rendered"}
        self.markdown_combo.configure(values=tuple(self.markdown_values))
        self.markdown_var.set(next(label for label, value in self.markdown_values.items()
                                   if value == markdown_mode))
        self.load()

    def _configure_effect_fonts(self) -> None:
        base = tkfont.nametofont("TkFixedFont")
        family, size = base.cget("family"), base.cget("size")
        self.effect_fonts = {
            "bold": tkfont.Font(self, family=family, size=size, weight="bold"),
            "italic": tkfont.Font(self, family=family, size=size, slant="italic"),
            "h1": tkfont.Font(self, family=family, size=max(size + 6, round(size * 1.55)), weight="bold"),
            "h2": tkfont.Font(self, family=family, size=max(size + 4, round(size * 1.35)), weight="bold"),
            "h3": tkfont.Font(self, family=family, size=max(size + 2, round(size * 1.18)), weight="bold"),
        }

    def apply_scale(self, _scale: float) -> None:
        self._configure_effect_fonts()
        self.apply_color_scheme(self.palette)

    def apply_color_scheme(self, palette) -> None:
        self.palette = palette
        self.configure(background=palette["window"])
        self.text.configure(background=palette["content"], foreground=palette["text"],
                            insertbackground=palette["text"], selectbackground=palette["selection"],
                            selectforeground="#ffffff")
        self.text.tag_configure("match", background=palette["match"], foreground=palette["text"])
        self.text.tag_configure("current_match", background=palette["current_diff"], foreground="#ffffff")
        dark = sum(int(palette["content"][i:i + 2], 16) for i in (1, 3, 5)) < 330
        colors = {
            "syntax_keyword": "#6cb6ff" if dark else "#005cc5",
            "syntax_string": "#a5d6a7" if dark else "#116329",
            "syntax_comment": "#9aa7b0" if dark else "#66737d",
            "syntax_number": "#f2a65a" if dark else "#b35900",
            "syntax_operator": "#d2a8ff" if dark else "#7a3e9d",
            "syntax_heading": "#79c0ff" if dark else "#174f86",
            "syntax_link": "#58a6ff" if dark else "#0969da",
        }
        for tag, foreground in colors.items():
            self.text.tag_configure(tag, foreground=foreground)
        self.text.tag_configure("markdown_bold", font=self.effect_fonts["bold"])
        self.text.tag_configure("markdown_italic", font=self.effect_fonts["italic"])
        self.text.tag_configure("markdown_code", background=palette["surface_alt"],
                                foreground=colors["syntax_string"])
        self.text.tag_configure("markdown_link", foreground=colors["syntax_link"], underline=True)
        self.text.tag_configure("markdown_url", foreground=palette["muted"])
        self.text.tag_configure("markdown_quote", foreground=palette["muted"])
        self.text.tag_configure("markdown_bullet", foreground=colors["syntax_keyword"])
        self.text.tag_configure("markdown_rule", foreground=palette["border"])
        for level in (1, 2, 3):
            self.text.tag_configure(f"markdown_h{level}", font=self.effect_fonts[f"h{level}"],
                                    foreground=colors["syntax_heading"], spacing1=8, spacing3=4)

    @property
    def path(self) -> Path:
        return self.files[self.index]

    def show(self, files, selected) -> None:
        self.files = list(files)
        self.index = self.files.index(selected) if selected in self.files else 0
        self.load(); self.activate()

    def set_extension_effect(self, enabled: bool) -> None:
        self.extension_effect = bool(enabled)
        self.load()

    def _apply_spans(self, spans: list[tuple[int, int, str]]) -> None:
        self._pending_spans = list(spans)
        self._apply_span_batch()

    def _apply_span_batch(self) -> None:
        self._span_job = None
        batch, self._pending_spans = (
            self._pending_spans[:SYNTAX_BATCH_SIZE],
            self._pending_spans[SYNTAX_BATCH_SIZE:])
        grouped: dict[str, list[str]] = {}
        for start, end, tag in batch:
            grouped.setdefault(tag, []).extend((f"1.0+{start}c", f"1.0+{end}c"))
        for tag, ranges in grouped.items():
            self.text.tag_add(tag, *ranges)
        if self._pending_spans and self.winfo_exists():
            self._span_job = self.after(8, self._apply_span_batch)

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
        if self._span_job is not None:
            self.after_cancel(self._span_job); self._span_job = None
        self._pending_spans = []
        self.title(f"{tr('PFC Preview')} — {path.name}")
        self.text.configure(state="normal"); self.text.delete("1.0", "end")
        mode = self.mode_values.get(self.mode_var.get(), self.mode_var.get())
        encoding, truncated, spans = "", False, []
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
                    suffix = path.suffix.casefold()
                    markdown_mode = self.markdown_values.get(self.markdown_var.get(), "rendered")
                    if self.extension_effect and suffix == ".md" and markdown_mode == "rendered":
                        content, spans = render_markdown(content)
                        shown_mode = tr("Markdown rendered")
                    elif self.extension_effect and suffix in CODE_EXTENSIONS:
                        spans = syntax_spans(content, suffix)
                        shown_mode = tr("{language} syntax", language=CODE_EXTENSIONS[suffix])
                else:
                    content = render_hex(data); shown_mode = tr("Hex")
                size = path.stat().st_size
            self.text.insert("1.0", content)
            self._apply_spans(spans)
            show_markdown = (path.is_file() and path.suffix.casefold() == ".md"
                             and chosen == "Text" and self.extension_effect)
            if show_markdown:
                self.markdown_frame.pack(side="left", padx=(4, 0))
            else:
                self.markdown_frame.pack_forget()
            size = path.stat().st_size if path.is_file() else 0
            detail = f"{shown_mode}   {size:,} bytes"
            if encoding: detail += f"   {encoding}"
            if truncated: detail += "   Preview truncated"
            self.status.configure(text=f"{detail}   {path}")
        except OSError as exc:
            self.text.insert("1.0", f"{tr('Cannot preview file')}:\n{exc}")
            self.status.configure(text=str(path))
        self.text.configure(state="disabled")
        self.text.tag_raise("match"); self.text.tag_raise("current_match")
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
        if self._span_job is not None:
            self.after_cancel(self._span_job); self._span_job = None
        if not self.config_data.has_section("preview"): self.config_data.add_section("preview")
        self.config_data.set("preview", "geometry", self.geometry())
        self.config_data.set("preview", "wrap", str(self.wrap_var.get()).lower())
        self.save_config(); self.destroy()
