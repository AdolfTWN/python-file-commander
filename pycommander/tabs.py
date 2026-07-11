from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk


TAB_COLORS = {
    "default": ("Default", "#c7d3dd"),
    "amber": ("Amber", "#f2c14e"),
    "coral": ("Coral", "#f58b68"),
    "pink": ("Pink", "#e96ba8"),
    "violet": ("Violet", "#8d7be5"),
    "teal": ("Teal", "#55b9ae"),
}


class ChamferNotebook(ttk.Frame):
    """A small Notebook-compatible container with canvas-drawn colored tabs."""

    def __init__(self, master, on_color_changed=None, **kwargs):
        super().__init__(master, **kwargs)
        self.on_color_changed = on_color_changed or (lambda _child, _color: None)
        self._tabs = []
        self._texts = {}
        self._colors = {}
        self._selected = None
        self._hitboxes = []
        self.bar = tk.Canvas(self, height=34, highlightthickness=0, background="#9eafbd")
        self.bar.pack(fill="x", side="top")
        self.bar.bind("<Button-1>", self._click)
        self.bar.bind("<Button-3>", self._popup)
        self.bar.bind("<Configure>", lambda _e: self._draw())

    def add(self, child, text="", color="default", **_kwargs):
        if child not in self._tabs:
            self._tabs.append(child)
        self._texts[child] = text
        self._colors[child] = color if color in TAB_COLORS else "default"
        self.select(child)

    def tabs(self):
        return tuple(str(child) for child in self._tabs)

    def select(self, tab=None):
        if tab is None:
            return str(self._selected) if self._selected is not None else ""
        child = self._resolve(tab)
        if child is self._selected:
            return str(child)
        if self._selected is not None:
            self._selected.pack_forget()
        self._selected = child
        child.pack(fill="both", expand=True, side="top")
        self._draw()
        self.event_generate("<<NotebookTabChanged>>")
        return str(child)

    def forget(self, tab):
        child = self._resolve(tab)
        was_selected = child is self._selected
        child.pack_forget()
        self._tabs.remove(child)
        self._texts.pop(child, None); self._colors.pop(child, None)
        if was_selected:
            self._selected = None
            if self._tabs:
                self.select(self._tabs[min(len(self._tabs) - 1, 0)])
        self._draw()

    def tab(self, tab, **options):
        child = self._resolve(tab)
        if "text" in options:
            self._texts[child] = options["text"]; self._draw()
        return {"text": self._texts.get(child, "")}

    def index(self, tab):
        return self._tabs.index(self._resolve(tab))

    def set_color(self, tab, color, notify=True):
        child = self._resolve(tab)
        self._colors[child] = color if color in TAB_COLORS else "default"
        self._draw()
        if notify:
            self.on_color_changed(child, self._colors[child])

    def redraw(self):
        self._draw()

    def _resolve(self, tab):
        if tab in self._tabs:
            return tab
        return self.nametowidget(tab)

    def _draw(self):
        self.bar.delete("all"); self._hitboxes.clear()
        font = tkfont.nametofont("TkDefaultFont")
        height = max(30, font.metrics("linespace") + 13)
        self.bar.configure(height=height)
        x, overlap, chamfer = 3, 9, max(8, round(height * 0.30))
        drawings = []
        for child in self._tabs:
            text = self._texts.get(child, "")
            selected = child is self._selected
            width = max(58, font.measure(text) + 28 + (14 if selected else 0))
            color = TAB_COLORS[self._colors.get(child, "default")][1]
            top = 0 if selected else max(5, round(height * 0.22))
            bottom = height if selected else height - 3
            points = (x, bottom, x, top + chamfer, x + chamfer, top,
                      x + width - chamfer, top, x + width, top + chamfer, x + width, bottom)
            drawings.append((selected, points, color, text, x, width, top, child))
            self._hitboxes.append((x, x + width, child))
            x += width - overlap
        # Paint the selected polygon last so its chamfered edges sit in front of
        # both neighbours instead of being covered by the tab to its right.
        for selected, points, color, text, left, width, top, child in sorted(drawings, key=lambda item: item[0]):
            self.bar.create_polygon(points, fill=color, outline="#3b5265" if selected else "#718596",
                                    width=3 if selected else 1)
            if selected:
                self.bar.create_line(left + 2, height - 2, left + width - 2, height - 2,
                                     fill=color, width=4)
            draw_font = (font.actual("family"), font.actual("size"), "bold") if selected else font
            self.bar.create_text(left + width / 2, (top + height) / 2 + 1, text=text, font=draw_font,
                                 fill="#10202c")
        self.bar.configure(scrollregion=(0, 0, max(x + overlap, self.bar.winfo_width()), height))

    def _at(self, x):
        if self._selected is not None:
            for left, right, child in self._hitboxes:
                if child is self._selected and left <= x <= right:
                    return child
        for left, right, child in reversed(self._hitboxes):
            if left <= x <= right:
                return child
        return None

    def _click(self, event):
        child = self._at(event.x)
        if child is not None:
            self.select(child)

    def _popup(self, event):
        child = self._at(event.x)
        if child is None:
            return
        self.select(child)
        menu = tk.Menu(self, tearoff=False, font=tkfont.nametofont("TkMenuFont"))
        for key, (label, _color) in TAB_COLORS.items():
            menu.add_command(label=label, command=lambda value=key: self.set_color(child, value))
        menu.tk_popup(event.x_root, event.y_root)
