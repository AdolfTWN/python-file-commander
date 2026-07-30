from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import messagebox, ttk

from .fileops import format_size
from .i18n import retranslate_widgets, tr


@dataclass
class SpaceNode:
    path: Path
    size: int
    is_dir: bool
    children: list["SpaceNode"] = field(default_factory=list)


def scan_space(path: Path, cancel_event: threading.Event | None = None) -> SpaceNode:
    """Return a best-effort, symlink-safe disk usage tree."""
    cancel_event = cancel_event or threading.Event()
    path = path.expanduser().resolve()
    if cancel_event.is_set():
        raise InterruptedError
    try:
        is_dir = path.is_dir()
    except OSError:
        return SpaceNode(path, 0, False)
    if not is_dir:
        try:
            return SpaceNode(path, path.stat().st_size, False)
        except OSError:
            return SpaceNode(path, 0, False)
    children = []
    try:
        entries = list(os.scandir(path))
    except OSError:
        return SpaceNode(path, 0, True)
    for entry in entries:
        if cancel_event.is_set():
            raise InterruptedError
        child = Path(entry.path)
        try:
            if entry.is_symlink():
                size = entry.stat(follow_symlinks=False).st_size
                children.append(SpaceNode(child, size, False))
            elif entry.is_dir(follow_symlinks=False):
                children.append(scan_space(child, cancel_event))
            else:
                children.append(SpaceNode(
                    child, entry.stat(follow_symlinks=False).st_size, False))
        except OSError:
            children.append(SpaceNode(child, 0, False))
    children.sort(key=lambda node: node.size, reverse=True)
    return SpaceNode(path, sum(child.size for child in children), True, children)


def partition_rectangles(nodes: list[SpaceNode], x: float, y: float,
                         width: float, height: float) -> list[tuple[SpaceNode, tuple[float, float, float, float]]]:
    """Balanced slice-and-dice layout with area proportional to byte size."""
    nodes = [node for node in nodes if node.size > 0]
    if not nodes or width <= 0 or height <= 0:
        return []
    if len(nodes) == 1:
        return [(nodes[0], (x, y, x + width, y + height))]
    total = sum(node.size for node in nodes)
    halfway, running, split = total / 2, 0, 1
    for index, node in enumerate(nodes[:-1], 1):
        running += node.size
        split = index
        if running >= halfway:
            break
    first, second = nodes[:split], nodes[split:]
    first_total = sum(node.size for node in first)
    ratio = first_total / total
    if width >= height:
        first_box = (x, y, width * ratio, height)
        second_box = (x + width * ratio, y, width * (1 - ratio), height)
    else:
        first_box = (x, y, width, height * ratio)
        second_box = (x, y + height * ratio, width, height * (1 - ratio))
    return (partition_rectangles(first, *first_box) +
            partition_rectangles(second, *second_box))


class SpaceAnalyzerWindow(tk.Toplevel):
    COLORS = ("#4f8fc9", "#66a65c", "#e29b45", "#9b72cf", "#d85d67",
              "#4fb5ad", "#c8885d", "#7d92a8", "#d3b94f")

    def __init__(self, parent, start_path: Path, on_locate, palette: dict) -> None:
        super().__init__(parent)
        self.withdraw()
        self.title(tr("Folder Space Analyzer"))
        self.transient(parent)
        self.on_locate = on_locate
        self.palette = palette
        self.path_var = tk.StringVar(value=str(start_path))
        self.status_var = tk.StringVar(value=tr("Ready"))
        self.history: list[Path] = []
        self.root_node: SpaceNode | None = None
        self.selected_node: SpaceNode | None = None
        self._rectangles: list[tuple[int, SpaceNode]] = []
        self._messages: queue.Queue = queue.Queue()
        self._cancel_event = threading.Event()
        self._worker = None
        self._poll_job = None
        self._resize_job = None
        self._build()
        parent.update_idletasks()
        width = max(840, int(parent.winfo_width() * 0.78))
        height = max(560, int(parent.winfo_height() * 0.80))
        screen_width, screen_height = self.winfo_screenwidth(), self.winfo_screenheight()
        width, height = min(width, screen_width - 50), min(height, screen_height - 80)
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(840, width), min(560, height))
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _event: self.close())
        self.bind("<F5>", lambda _event: self.scan())
        self.deiconify()
        self.lift()
        self.focus_force()
        self.scan(start_path, remember=False)

    def _build(self) -> None:
        toolbar = ttk.Frame(self, padding=(8, 7, 8, 3))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text=tr("Back"), command=self.back).pack(side="left")
        ttk.Button(toolbar, text=tr("Parent Folder"), command=self.parent_folder).pack(side="left", padx=4)
        self.scan_button = ttk.Button(toolbar, text=tr("Analyze"), command=self.scan)
        self.scan_button.pack(side="left", padx=(6, 3))
        self.stop_button = ttk.Button(toolbar, text=tr("Stop"), command=self.stop)
        self.stop_button.pack(side="left")
        ttk.Button(toolbar, text=tr("Locate in PFC"),
                   command=self.locate_selected).pack(side="right")

        path_row = ttk.Frame(self, padding=(8, 3, 8, 5))
        path_row.pack(fill="x")
        ttk.Label(path_row, text=tr("Folder:")).pack(side="left", padx=(0, 5))
        self.path_entry = ttk.Entry(path_row, textvariable=self.path_var)
        self.path_entry.pack(side="left", fill="x", expand=True)
        self.path_entry.bind("<Return>", lambda _event: self.scan())

        info = ttk.Frame(self, padding=(8, 0, 8, 6))
        info.pack(fill="x")
        ttk.Label(
            info,
            text=tr("Block area is proportional to file or folder size. Click to locate; double-click a folder to analyze it."),
            anchor="w").pack(fill="x")

        self.canvas = tk.Canvas(self, highlightthickness=1, relief="sunken",
                                background=palette_color(self.palette, "background", "#f2f2f2"))
        self.canvas.pack(fill="both", expand=True, padx=8)
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Double-Button-1>", self._double_click)
        self.canvas.bind("<Configure>", self._schedule_redraw)

        legend = ttk.Frame(self, padding=(8, 5, 8, 2))
        legend.pack(fill="x")
        for label, color in ((tr("Folders"), self.COLORS[0]),
                             (tr("Files"), self.COLORS[2]),
                             (tr("Selected"), "#ffcf45")):
            swatch = tk.Label(legend, width=2, background=color, relief="solid", borderwidth=1)
            swatch.pack(side="left", padx=(0, 3))
            ttk.Label(legend, text=label).pack(side="left", padx=(0, 12))
        ttk.Label(self, textvariable=self.status_var, anchor="w",
                  padding=(8, 4)).pack(fill="x")

    def apply_scale(self, _scale: float) -> None:
        self.after_idle(self._redraw)

    def apply_color_scheme(self, palette: dict) -> None:
        self.palette = palette
        self.canvas.configure(
            background=palette_color(palette, "content", "#f2f2f2"),
            highlightbackground=palette_color(palette, "border", "#808080"))
        self._redraw()

    def apply_language(self, old_language: str) -> None:
        self.title(tr("Folder Space Analyzer"))
        retranslate_widgets(self, old_language)

    def show(self, path: Path) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()
        target = path if path.is_dir() else path.parent
        if str(target) != self.path_var.get():
            self.scan(target)

    def scan(self, path: Path | None = None, remember: bool = True) -> None:
        target = Path(path or self.path_var.get().strip().strip('"')).expanduser()
        if not target.is_dir():
            messagebox.showerror(tr("Folder Space Analyzer"),
                                 tr("Select a folder to analyze."), parent=self)
            self.path_var.set(str(self.root_node.path if self.root_node else target.parent))
            return
        target = target.resolve()
        if self._worker is not None and self._worker.is_alive():
            self.stop()
        if remember and self.root_node is not None and self.root_node.path != target:
            self.history.append(self.root_node.path)
        self.path_var.set(str(target))
        self.root_node = None
        self.selected_node = None
        self.canvas.delete("all")
        self._cancel_event = threading.Event()
        self.status_var.set(tr("Scanning…  Esc closes"))
        self.stop_button.state(["!disabled"])
        self.scan_button.state(["disabled"])

        def worker():
            try:
                self._messages.put(("done", scan_space(target, self._cancel_event)))
            except InterruptedError:
                self._messages.put(("cancelled", None))
            except Exception as exc:
                self._messages.put(("error", exc))

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()
        if self._poll_job is None:
            self._poll()

    def _poll(self) -> None:
        self._poll_job = None
        try:
            kind, value = self._messages.get_nowait()
        except queue.Empty:
            if self.winfo_exists():
                self._poll_job = self.after(80, self._poll)
            return
        self.scan_button.state(["!disabled"])
        self.stop_button.state(["disabled"])
        if kind == "done":
            self.root_node = value
            self.status_var.set(tr("{count} top-level items   {size}",
                                   count=len(value.children), size=format_size(value.size)))
            self._redraw()
        elif kind == "cancelled":
            self.status_var.set(tr("Scan cancelled"))
        else:
            self.status_var.set(tr("Scan failed"))
            messagebox.showerror(tr("Folder Space Analyzer"), str(value), parent=self)

    def stop(self) -> None:
        self._cancel_event.set()
        self.status_var.set(tr("Cancelling…"))

    def back(self) -> None:
        if self.history:
            self.scan(self.history.pop(), remember=False)

    def parent_folder(self) -> None:
        current = Path(self.path_var.get())
        if current.parent != current:
            self.scan(current.parent)

    def _schedule_redraw(self, _event=None) -> None:
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(100, self._redraw)

    def _redraw(self) -> None:
        self._resize_job = None
        self.canvas.delete("all")
        self._rectangles.clear()
        if self.root_node is None:
            return
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        boxes = partition_rectangles(self.root_node.children, 2, 2, width - 4, height - 4)
        font = tkfont.nametofont("TkDefaultFont")
        for index, (node, box) in enumerate(boxes):
            self._draw_node(node, box, font, depth=0, color_index=index)

    def _draw_node(self, node: SpaceNode, box, font, depth: int,
                   color_index: int) -> None:
        x1, y1, x2, y2 = box
        width, height = x2 - x1, y2 - y1
        if width < 2 or height < 2:
            return
        if node.is_dir:
            color = self.COLORS[depth % 2]
        else:
            suffix_value = sum(ord(char) for char in node.path.suffix.casefold())
            color = self.COLORS[2 + suffix_value % (len(self.COLORS) - 2)]
        if node is self.selected_node:
            color = "#ffcf45"
        item = self.canvas.create_rectangle(
            x1, y1, x2, y2, fill=color, outline="#ffffff",
            width=max(1, 2 - min(depth, 1)))
        self._rectangles.append((item, node))
        line = font.metrics("linespace")
        label_height = line + 5 if node.is_dir and node.children else 0
        if width > font.measure("MMMM") and height > line * 1.25:
            max_width = max(1, int(width - 8))
            label = node.path.name
            while label and font.measure(label) > max_width:
                label = label[:-1]
            if label != node.path.name:
                label = label[:-1] + "…" if label else ""
            detail = label if label_height else f"{label}\n{format_size(node.size)}"
            self.canvas.create_text(
                x1 + 5, y1 + 3, text=detail, anchor="nw",
                width=max_width, fill="#101820", font=font)
        inner_height = height - label_height - 3
        if (node.is_dir and node.children and depth < 7 and
                width >= 34 and inner_height >= 24):
            inner = partition_rectangles(
                node.children, x1 + 2, y1 + label_height,
                width - 4, inner_height)
            for index, (child, child_box) in enumerate(inner):
                self._draw_node(child, child_box, font, depth + 1,
                                color_index + index)

    def _node_at(self, x: int, y: int) -> SpaceNode | None:
        overlapping = set(self.canvas.find_overlapping(x, y, x, y))
        for item, node in reversed(self._rectangles):
            if item in overlapping:
                return node
        return None

    def _click(self, event) -> None:
        node = self._node_at(event.x, event.y)
        if node is None:
            return
        self.selected_node = node
        self.status_var.set(f"{node.path}   {format_size(node.size)}")
        self._redraw()
        self.on_locate(node.path)

    def _double_click(self, event) -> None:
        node = self._node_at(event.x, event.y)
        if node is not None and node.is_dir:
            self.scan(node.path)

    def locate_selected(self) -> None:
        if self.selected_node is not None:
            self.on_locate(self.selected_node.path)

    def close(self) -> None:
        self._cancel_event.set()
        if self._poll_job is not None:
            self.after_cancel(self._poll_job)
            self._poll_job = None
        self.destroy()


def palette_color(palette: dict, key: str, fallback: str) -> str:
    return palette.get(key, fallback)
