from __future__ import annotations

import tkinter as tk
from tkinter import ttk


BUTTON_HELP = {
    "↑": "Go to the parent folder.", "⌂": "Go to your home folder.",
    "F2 Rename": "Rename the selected item.", "F3 Preview": "Open the selected item in PFC Preview.",
    "F4 Search": "Search for files and folders below the current path.",
    "F5 Copy": "Copy selected items to the opposite panel.",
    "F6 Move": "Move selected items to the opposite panel.", "F7 New folder": "Create a folder here.",
    "F8": "Reserved for a future action.", "F9 Compare": "Compare selected files or folders.",
    "F11 Copy Path": "Copy all selected full paths as text.",
    "F12 Change Dir": "Focus and select the path bar for direct paste.",
    "File <<": "Preview the previous item.", "File >>": "Preview the next item.",
    "Find Prev": "Go to the previous search match.", "Find Next": "Go to the next search match.",
    "F7 Diff <<": "Go to the previous difference.", "F8 Diff >>": "Go to the next difference.",
    "Previous": "Go to the previous item.", "Next": "Go to the next item.",
    "Files": "Open file operations.", "View": "Open display settings.", "OK": "Close this window.",
}


class ToolTip:
    def __init__(self, widget, text, delay=5000):
        self.widget, self.text, self.delay = widget, text, delay
        self.job = self.popup = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<Button>", self.hide, add="+")

    def _enter(self, _event=None):
        self.hide(); self.job = self.widget.after(self.delay, self.show)

    def show(self):
        self.job = None
        if not self.widget.winfo_exists(): return
        self.popup = tk.Toplevel(self.widget.winfo_toplevel())
        self.popup.overrideredirect(True); self.popup.attributes("-topmost", True)
        x, y = self.widget.winfo_pointerxy()
        self.popup.geometry(f"+{x + 14}+{y + 18}")
        owner = self.widget.winfo_toplevel()
        palette = getattr(owner, "palette", {})
        tk.Label(self.popup, text=self.text, justify="left",
                 background=palette.get("tooltip", "#fffbd6"),
                 foreground=palette.get("tooltip_text", "#18232c"),
                 relief="solid", borderwidth=1, padx=7, pady=4).pack()

    def hide(self, _event=None):
        if self.job is not None:
            try: self.widget.after_cancel(self.job)
            except tk.TclError: pass
            self.job = None
        if self.popup is not None:
            try: self.popup.destroy()
            except tk.TclError: pass
            self.popup = None


class MenuToolTip:
    def __init__(self, menu, descriptions, delay=5000):
        self.menu, self.descriptions, self.delay = menu, descriptions, delay
        self.job = self.popup = self.last_index = None
        menu.bind("<<MenuSelect>>", self._selected, add="+")
        menu.bind("<Unmap>", self.hide, add="+")

    def _selected(self, _event=None):
        try: index = self.menu.index("active")
        except tk.TclError: index = None
        if index == self.last_index: return
        self.hide(); self.last_index = index
        if index is not None and self.menu.type(index) != "separator":
            self.job = self.menu.after(self.delay, lambda: self.show(index))

    def show(self, index):
        self.job = None
        try: label = self.menu.entrycget(index, "label")
        except tk.TclError: return
        text = self.descriptions.get(label, label.replace("\t", " — "))
        self.popup = tk.Toplevel(self.menu.winfo_toplevel())
        self.popup.overrideredirect(True); self.popup.attributes("-topmost", True)
        x, y = self.menu.winfo_pointerxy(); self.popup.geometry(f"+{x + 14}+{y + 18}")
        owner = self.menu.winfo_toplevel()
        palette = getattr(owner, "palette", {})
        tk.Label(self.popup, text=text, justify="left",
                 background=palette.get("tooltip", "#fffbd6"),
                 foreground=palette.get("tooltip_text", "#18232c"),
                 relief="solid", borderwidth=1, padx=7, pady=4).pack()

    def hide(self, _event=None):
        if self.job is not None:
            try: self.menu.after_cancel(self.job)
            except tk.TclError: pass
            self.job = None
        if self.popup is not None:
            try: self.popup.destroy()
            except tk.TclError: pass
            self.popup = None


def install_button_tooltips(root) -> None:
    for widget in root.winfo_children():
        if isinstance(widget, (ttk.Button, tk.Button, tk.Menubutton)) and not hasattr(widget, "_pfc_tooltip"):
            text = str(widget.cget("text"))
            widget._pfc_tooltip = ToolTip(widget, BUTTON_HELP.get(text, f"Activate {text}."))
        install_button_tooltips(widget)
