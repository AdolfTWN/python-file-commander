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

TAB_STYLES = {
    "rounded": "Soft Rounded",
    "slanted": "Slanted",
    "chamfered": "Chamfered",
    "compact": "Compact",
}


class ChamferNotebook(ttk.Frame):
    """A small Notebook-compatible container with canvas-drawn colored tabs."""

    def __init__(self, master, on_color_changed=None, on_lock_changed=None,
                 tab_style="rounded", **kwargs):
        super().__init__(master, **kwargs)
        self.on_color_changed = on_color_changed or (lambda _child, _color: None)
        self.on_lock_changed = on_lock_changed or (lambda _child, _mode: None)
        self._tabs = []
        self._texts = {}
        self._colors = {}
        self._locks = {}
        self._selected = None
        self._tab_style = tab_style if tab_style in TAB_STYLES else "rounded"
        self._hitboxes = []
        self.bar = tk.Canvas(self, height=34, highlightthickness=0, background="#9eafbd")
        self.bar.pack(fill="x", side="top")
        self.bar.bind("<Button-1>", self._click)
        self.bar.bind("<Button-3>", self._popup)
        self.bar.bind("<Configure>", lambda _e: self._draw())

    def add(self, child, text="", color="default", lock="unlocked", position=None, **_kwargs):
        if child not in self._tabs:
            if position is None:
                self._tabs.append(child)
            else:
                self._tabs.insert(max(0, min(position, len(self._tabs))), child)
        self._texts[child] = text
        self._colors[child] = color if color in TAB_COLORS else "default"
        self._locks[child] = lock if lock in {"unlocked", "locked", "reset"} else "unlocked"
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
        self._texts.pop(child, None); self._colors.pop(child, None); self._locks.pop(child, None)
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

    def set_lock(self, tab, mode, notify=True):
        child = self._resolve(tab)
        self._locks[child] = mode if mode in {"unlocked", "locked", "reset"} else "unlocked"
        self._draw()
        if notify:
            self.on_lock_changed(child, self._locks[child])

    def redraw(self):
        self._draw()

    def set_style(self, style):
        self._tab_style = style if style in TAB_STYLES else "rounded"
        self._draw()

    def _resolve(self, tab):
        if tab in self._tabs:
            return tab
        return self.nametowidget(tab)

    def _draw(self):
        self.bar.delete("all"); self._hitboxes.clear()
        font = tkfont.nametofont("TkDefaultFont")
        compact = self._tab_style == "compact"
        height = max(27 if compact else 30, font.metrics("linespace") + (9 if compact else 13))
        self.bar.configure(height=height)
        overlap = {"rounded": 2, "slanted": 11, "chamfered": 9, "compact": -2}[self._tab_style]
        x = 3
        drawings = []
        for child in self._tabs:
            text = self._texts.get(child, "")
            lock = self._locks.get(child, "unlocked")
            selected = child is self._selected
            padding = 20 if compact else 28
            width = max(52 if compact else 58, font.measure(text) + padding + (10 if selected else 0))
            color = TAB_COLORS[self._colors.get(child, "default")][1]
            top = 0 if selected else max(4, round(height * (0.18 if compact else 0.22)))
            bottom = height if selected else height - 3
            corner = max(6, round(height * 0.28))
            if self._tab_style == "rounded":
                points = (x, bottom, x, top + corner, x, top + corner,
                          x + corner, top, x + corner, top,
                          x + width - corner, top, x + width - corner, top,
                          x + width, top + corner, x + width, top + corner, x + width, bottom)
                smooth, inset = True, corner
            elif self._tab_style == "slanted":
                slant = max(10, round(height * 0.42))
                points = (x, bottom, x + slant, top, x + width - slant, top, x + width, bottom)
                smooth, inset = False, slant
            elif self._tab_style == "compact":
                tail = max(12, round(height * 0.45))
                points = (x, bottom, x, top,
                          x + width - 5, top, x + width, top + 5,
                          x + width, bottom - 7, x + width + tail, bottom)
                smooth, inset = False, 5
            else:
                chamfer = max(8, round(height * 0.30))
                points = (x, bottom, x, top + chamfer, x + chamfer, top,
                          x + width - chamfer, top, x + width, top + chamfer, x + width, bottom)
                smooth, inset = False, chamfer
            drawings.append((selected, points, color, text, x, width, top, child, lock, inset, smooth))
            self._hitboxes.append((x, x + width, child))
            x += width - overlap
        # Paint the selected polygon last so its chamfered edges sit in front of
        # both neighbours instead of being covered by the tab to its right.
        for selected, points, color, text, left, width, top, child, lock, tab_inset, smooth in sorted(
                drawings, key=lambda item: item[0]):
            self.bar.create_polygon(points, fill=color, outline="#3b5265" if selected else "#718596",
                                    width=3 if selected else 1, smooth=smooth, splinesteps=18)
            if lock != "unlocked":
                self.bar.create_line(left + tab_inset + 2, top + 2,
                                     left + width - tab_inset - 2, top + 2,
                                     fill="#3b5265", width=3,
                                     dash=() if lock == "locked" else (5, 3))
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
        menu.add_separator()
        lock_mode = tk.StringVar(value=self._locks.get(child, "unlocked"))
        for label, value in (("Unlocked", "unlocked"),
                             ("Lock (open folder in new tab)", "locked"),
                             ("Lock (open folder is allowed)", "reset")):
            menu.add_radiobutton(label=label, value=value, variable=lock_mode,
                                 command=lambda mode=value: self.set_lock(child, mode))
        menu.tk_popup(event.x_root, event.y_root)
