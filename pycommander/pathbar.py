"""Single-line logical breadcrumbs with an explicit full-path editor."""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from .i18n import tr
from .tooltip import ToolTip


def path_ancestors(path):
    """Keep real targets, including drive/UNC roots, separate from labels."""
    return [(p.name or str(p), p) for p in [*reversed(path.parents), path]]


def fit_crumbs(parts, width, measure):
    """Return (label, original index, pixel width); None denotes overflow."""
    if not parts or width <= 0:
        return []
    widths = [measure(label) + 20 for label, _ in parts]
    start = 0
    overflow = measure("…") + 20
    while start < len(parts) - 1 and sum(widths[start:]) + (overflow if start else 0) > width:
        start += 1
    # In very narrow panes the current directory takes precedence over overflow.
    show_overflow = start > 0 and width >= overflow + measure("MMMM") + 20
    remaining = max(1, width - (overflow if show_overflow else 0))
    result = [("…", None, overflow)] if show_overflow else []
    for index in range(start, len(parts)):
        label = parts[index][0]
        space = min(widths[index], remaining)
        if measure(label) > max(0, space - 20):
            length = len(label)
            while length > 0:
                candidate = label[:(length + 1) // 2] + "…" + (label[-(length // 2):] if length > 1 else "")
                if measure(candidate) <= max(0, space - 20):
                    break
                length -= 1
            label = candidate if length else "…"
        result.append((label, index, space))
        remaining -= space
    return result


class PathBar(ttk.Frame):
    def __init__(self, master, variable, parts, activate, submit, focus_files):
        super().__init__(master)
        self.variable, self.parts = variable, parts
        self.activate, self.submit, self.focus_files = activate, submit, focus_files
        self.editing = self.submitting = False
        self._closed = False
        self._redraw_job = None
        self._owner = self.winfo_toplevel()
        # Never mix a live system named font with a copied bold font. Windows
        # can refresh named fonts after unlock without resizing this Canvas.
        self.normal = tkfont.Font(root=self, font="TkDefaultFont")
        self.link = tkfont.Font(root=self, font="TkDefaultFont")
        self.bold = tkfont.Font(root=self, font="TkDefaultFont")
        self.committed = variable.get()
        self.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, width=1, highlightthickness=0, takefocus=1)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.entry = ttk.Entry(self, textvariable=variable, width=1)
        self.edit_button = ttk.Button(self, text="✎", width=2, command=self.begin_edit)
        self.edit_button.grid(row=0, column=1, sticky="ns")
        self.tooltip = ToolTip(self.canvas, lambda: self.committed, delay=700)
        ToolTip(self.edit_button, lambda: tr("Edit path (Ctrl+L / F12)"), delay=700)
        for sequence in ("<Configure>", "<Expose>", "<Map>", "<Visibility>", "<<ThemeChanged>>"):
            self.canvas.bind(sequence, self.request_redraw)
        self._focus_binding = self._owner.bind("<FocusIn>", self.request_redraw, add="+")
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Return>", self.begin_edit)
        self.canvas.bind("<space>", self.begin_edit)
        self.entry.bind("<Return>", self._submit)
        self.entry.bind("<Escape>", self.cancel)
        self.entry.bind("<FocusOut>", self._focus_out)
        self._trace = variable.trace_add("write", self._changed)
        self.bind("<Destroy>", self._destroy, add="+")
        self._regions = []
        self._overflow_menu = None
        self.redraw()

    def _destroy(self, event):
        if event.widget is self:
            self._closed = True
            if self._redraw_job is not None:
                self.after_cancel(self._redraw_job)
                self._redraw_job = None
            self._owner.unbind("<FocusIn>", self._focus_binding)
            self.variable.trace_remove("write", self._trace)
            self.tooltip.hide()

    def _changed(self, *_):
        if not self.editing:
            self.committed = self.variable.get()
            self.redraw()

    def set_location(self, text):
        """A real navigation supersedes an unsubmitted edit, even without blur."""
        self.editing = False
        self.committed = text
        self.entry.grid_remove()
        self.canvas.grid()
        self.variable.set(text)

    def begin_edit(self, _event=None):
        if not self.editing:
            self.variable.set(self.committed)
            self.editing = True
            self.canvas.grid_remove()
            self.entry.grid(row=0, column=0, sticky="nsew")
        self.entry.focus_set()
        self.entry.selection_range(0, "end")
        return "break"

    def cancel(self, _event=None, focus=True):
        if self.editing:
            self.editing = False
            self.variable.set(self.committed)
            self.entry.grid_remove()
            self.canvas.grid()
            if focus:
                self.focus_files()
        return "break"

    def _focus_out(self, _event=None):
        if not self.submitting:
            self.cancel(focus=False)

    def _submit(self, _event=None):
        raw = self.variable.get()
        self.submitting = True
        try:
            success = self.submit()
        finally:
            self.submitting = False
        if success:
            self.committed = self.variable.get()
            self.cancel(focus=False)
        else:
            self.begin_edit()
            self.variable.set(raw)
            self.entry.focus_set()
        return "break"

    def request_redraw(self, _event=None):
        if not self._closed and self._redraw_job is None:
            self._redraw_job = self.after_idle(self.redraw)

    def redraw(self, _event=None):
        if self._closed:
            return
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
            self._redraw_job = None
        palette = getattr(self.winfo_toplevel(), "palette", {})
        font = tkfont.nametofont("TkDefaultFont")
        attributes = font.actual()
        self.normal.configure(**dict(attributes, underline=0))
        self.link.configure(**dict(attributes, underline=1))
        self.bold.configure(**dict(attributes, weight="bold", underline=1))
        bg, fg = palette.get("entry", "#ffffff"), palette.get("text", "#18232c")
        self.canvas.configure(background=bg, height=font.metrics("linespace") + 10)
        self.canvas.delete("all")
        parts = self.parts()
        if self.committed.startswith("["):
            parts = [(self.committed, None)]
        self._parts = parts
        self._regions = []
        x, height = 0, max(self.canvas.winfo_height(), font.metrics("linespace") + 10)
        for label, index, width in fit_crumbs(parts, self.canvas.winfo_width(), self.bold.measure):
            target = parts[index][1] if index is not None else None
            is_folder = target is not None and target.parent != target
            label_font = self.bold if index == len(parts) - 1 else self.link
            if not is_folder:
                label_font = self.normal
            self.canvas.create_text(x + 4, height / 2, text=label, anchor="w",
                                    fill=fg, font=label_font, tags=("folder" if is_folder else "root",))
            if index is not None and index < len(parts) - 1:
                self.canvas.create_text(x + width - 8, height / 2, text="›", fill=fg, font=self.normal)
            self._regions.append((x, x + width, index))
            x += width

    def _click(self, event):
        for left, right, index in self._regions:
            if left <= event.x < right:
                if index is None:
                    if self._overflow_menu is not None:
                        self._overflow_menu.destroy()
                    menu = tk.Menu(self, tearoff=False, font="TkMenuFont")
                    self._overflow_menu = menu
                    palette = getattr(self.winfo_toplevel(), "palette", {})
                    if palette:
                        menu.configure(background=palette["menu"], foreground=palette["menu_text"],
                                       activebackground=palette["menu_active"], activeforeground=palette["menu_active_text"])
                    visible = [i for _, _, i in self._regions if i is not None]
                    for label, target in self._parts[:min(visible)]:
                        menu.add_command(label=label, command=lambda p=target: self.activate(p))
                    try:
                        menu.tk_popup(event.x_root, event.y_root)
                    finally:
                        menu.grab_release()
                elif self._parts[index][1] is not None:
                    self.activate(self._parts[index][1])
                return "break"
