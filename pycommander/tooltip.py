from __future__ import annotations

import tkinter as tk
from tkinter import ttk


BUTTON_HELP = {
    "↑": "Go to the parent folder.", "⌂": "Go to your home folder.",
    "F2 Rename": "Rename the selected item.", "F3 Preview": "Open the selected item in PFC Preview.",
    "F4 Search": "Search for files and folders below the current path.",
    "F5 Copy": "Copy selected items to the destination panel shown on F5.",
    "F6 Move": "Move selected items to the opposite panel.", "F7 New folder": "Create a folder here.",
    "F8": "Git / SVN status, commit, history and graph.", "F9 Compare": "Compare selected files or folders.",
    "F11 Copy Path": "Copy all selected full paths as text.",
    "F12 Change Path": "Focus and select the path bar for direct paste.",
    "File <<": "Preview the previous item.", "File >>": "Preview the next item.",
    "Find Prev": "Go to the previous search match.", "Find Next": "Go to the next search match.",
    "F7 Diff <<": "Go to the previous difference.", "F8 Diff >>": "Go to the next difference.",
    "Previous": "Go to the previous item.", "Next": "Go to the next item.",
    "Files": "Open file operations.", "View": "Open display settings.", "OK": "Close this window.",
}


class ToolTip:
    """Owner-scoped, bounded hover help; never survives a stale hover/focus."""

    poll_ms = 100
    lifetime_ms = 8000

    def __init__(self, widget, text, delay=5000, *, bind_hover=True):
        self.widget, self.text, self.delay = widget, text, delay
        self.job = self.popup = None
        self.watch_job = self.expire_job = None
        self.owner = widget.winfo_toplevel()
        while isinstance(self.owner, tk.Menu):
            self.owner = self.owner.master.winfo_toplevel()
        self.owner_bindings = []
        if bind_hover:
            widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<Button>", self.hide, add="+")
        widget.bind("<MouseWheel>", self.hide, add="+")
        widget.bind("<Unmap>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")

    def _enter(self, _event=None):
        self.hide()
        self._schedule()

    def _schedule(self):
        if not self._eligible():
            return
        # Bind only for the lifetime of a pending/visible tooltip. No root-wide
        # permanent callbacks accumulating as preview tabs/menus are destroyed.
        for sequence in ("<FocusOut>", "<KeyPress>", "<ButtonPress>", "<Unmap>"):
            token = self.owner.bind(sequence, self.hide, add="+")
            self.owner_bindings.append((sequence, token))
        self.job = self.widget.after(self.delay, self.show)
        self.watch_job = self.widget.after(self.poll_ms, self._watch)

    def _eligible(self):
        try:
            if not self.widget.winfo_viewable() or not self.owner.winfo_viewable():
                return False
            focus = self.owner.focus_displayof()
            if focus is None or focus.winfo_toplevel() != self.owner:
                return False
            x, y = self.widget.winfo_pointerxy()
            return self._target_at(x, y)
        except (tk.TclError, KeyError):
            return False

    def _target_at(self, x, y):
        target = self.widget.winfo_containing(x, y)
        return target == self.widget

    def _watch(self):
        self.watch_job = None
        if not self._eligible():
            self.hide()
        else:
            self.watch_job = self.widget.after(self.poll_ms, self._watch)

    def show(self):
        self.job = None
        if not self._eligible():
            self.hide()
            return
        text = self.text() if callable(self.text) else self.text
        if not text:
            self.hide()
            return
        if self.popup is not None:
            return
        self.popup = tk.Toplevel(self.owner, takefocus=False)
        self.popup.withdraw()
        self.popup.overrideredirect(True)
        # Owned help must not float globally above unrelated applications.
        self.popup.transient(self.owner)
        x, y = self.widget.winfo_pointerxy()
        self.popup.geometry(f"+{x + 14}+{y + 18}")
        palette = getattr(self.owner, "palette", {})
        tk.Label(self.popup, text=text, justify="left", wraplength=900,
                 background=palette.get("tooltip", "#fffbd6"),
                 foreground=palette.get("tooltip_text", "#18232c"),
                 relief="solid", borderwidth=1, padx=7, pady=4).pack()
        # If the pointer approaches the help window, dismiss it before a click
        # can be intercepted. Escape and owner input also dismiss immediately.
        self.popup.bind("<Enter>", self.hide, add="+")
        self.popup.bind("<ButtonPress>", self.hide, add="+")
        self.popup.deiconify()
        self.expire_job = self.widget.after(self.lifetime_ms, self.hide)

    def hide(self, _event=None):
        for name in ("job", "watch_job", "expire_job"):
            token = getattr(self, name)
            if token is not None:
                try: self.widget.after_cancel(token)
                except tk.TclError: pass
                setattr(self, name, None)
        for sequence, token in self.owner_bindings:
            try: self.owner.unbind(sequence, token)
            except tk.TclError: pass
        self.owner_bindings.clear()
        if self.popup is not None:
            try: self.popup.destroy()
            except tk.TclError: pass
            self.popup = None


class TreeItemToolTip(ToolTip):
    """Shows delayed text for the Treeview row currently under the pointer."""

    def __init__(self, tree, text_for_item, delay=3000):
        self.tree, self.text_for_item, self.delay = tree, text_for_item, delay
        self.item = ""
        super().__init__(tree, self._text, delay, bind_hover=False)
        tree.bind("<Motion>", self._motion, add="+")

    def _text(self):
        return self.text_for_item(self.item) if self.item else ""

    def _target_at(self, x, y):
        return (super()._target_at(x, y) and bool(self.item)
                and self.tree.identify_row(y - self.tree.winfo_rooty()) == self.item)

    def _motion(self, event):
        item = self.tree.identify_row(event.y)
        if item == self.item:
            return
        self.hide(); self.item = item
        if item and self.text_for_item(item):
            self._schedule()

    def hide(self, _event=None):
        super().hide(_event)
        self.item = ""


class MenuToolTip(ToolTip):
    def __init__(self, menu, descriptions, delay=5000):
        self.menu, self.descriptions, self.delay = menu, descriptions, delay
        self.last_index = None
        super().__init__(menu, self._text, delay, bind_hover=False)
        menu.bind("<<MenuSelect>>", self._selected, add="+")

    def _selected(self, _event=None):
        try: index = self.menu.index("active")
        except tk.TclError: index = None
        if index == self.last_index: return
        self.hide(); self.last_index = index
        if index is not None and self.menu.type(index) != "separator":
            self._schedule()

    def _text(self):
        try: label = self.menu.entrycget(self.last_index, "label")
        except tk.TclError: return ""
        return self.descriptions.get(label, label.replace("\t", " — "))

    def _target_at(self, x, y):
        return (super()._target_at(x, y) and self.last_index is not None
                and self.menu.index("active") == self.last_index)

    def hide(self, _event=None):
        super().hide(_event)
        self.last_index = None


def install_button_tooltips(root) -> None:
    for widget in root.winfo_children():
        if isinstance(widget, (ttk.Button, tk.Button, tk.Menubutton)) and not hasattr(widget, "_pfc_tooltip"):
            text = str(widget.cget("text"))
            widget._pfc_tooltip = ToolTip(widget, BUTTON_HELP.get(text, f"Activate {text}."))
        install_button_tooltips(widget)
