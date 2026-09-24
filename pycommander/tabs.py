from __future__ import annotations

import ctypes
import os
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from .i18n import tr
from .tabicons import tab_lock_icon_png
from .tooltip import ToolTip


def virtual_screen_bounds(widget) -> tuple[int, int, int, int]:
    """Return the complete desktop bounds, including negative monitor origins."""
    if os.name == "nt":
        user32 = ctypes.windll.user32
        return tuple(user32.GetSystemMetrics(index) for index in (76, 77, 78, 79))
    return (widget.winfo_vrootx(), widget.winfo_vrooty(),
            widget.winfo_vrootwidth(), widget.winfo_vrootheight())


def clamp_popup_position(x: int, y: int, width: int, height: int,
                         bounds: tuple[int, int, int, int]) -> tuple[int, int]:
    left, top, screen_width, screen_height = bounds
    right, bottom = left + screen_width, top + screen_height
    return (max(left, min(int(x), right - int(width))),
            max(top, min(int(y), bottom - int(height))))


TAB_COLORS = {
    "default": ("Default", "#e4edf3"),
    "red": ("Red", "#f59b9b"),
    "light_blue": ("Light Blue", "#a3d6ed"),
    "orange": ("Orange", "#f6c18a"),
    "green": ("Green", "#9ed8af"),
    "purple": ("Purple", "#c0a6e9"),
}

# Preserve tabs saved by releases before v0.12.7 while presenting only the
# clearer, commonly named palette in the context menu.
TAB_COLOR_ALIASES = {
    "amber": "orange", "coral": "red", "pink": "red",
    "violet": "purple", "teal": "light_blue",
}


def normalize_tab_color(color: str) -> str:
    normalized = TAB_COLOR_ALIASES.get(color, color)
    return normalized if normalized in TAB_COLORS else "default"

TAB_STYLES = {
    "right_skirt": "Right Skirt",
    "rounded": "Rounded",
    "squarish": "Squarish",
}


COLOR_SCHEMES = {
    "light": {
        "window": "#f0f2f4", "surface": "#ffffff", "surface_alt": "#e8edf1",
        "text": "#17232c", "muted": "#526575", "border": "#8fa0ad",
        "header": "#243b53", "header_text": "#f4f8fb", "header_muted": "#c9e5f5",
        "header_button": "#31536e", "header_active": "#3d6888",
        "button": "#e7ecef", "button_active": "#d4e2eb", "entry": "#ffffff",
        "selection": "#1683e2", "inactive_selection": "#91a9bd",
        "tab_bar": "#9eafbd", "tab_default": "#e4edf3", "tab_text": "#10202c",
        "tab_lock_bg": "#414141", "tab_lock_fg": "#fafafa",
        "menu": "#f0f0f0", "menu_text": "#101010", "menu_disabled": "#777777",
        "menu_active": "#087bdc", "menu_active_text": "#ffffff", "separator": "#b8b8b8",
        "gutter": "#e5ebef", "gutter_text": "#526575", "content": "#ffffff",
        "diff": "#ffe1a8", "current_diff": "#ffb347", "match": "#fff0a6",
        "left_header": "#2d668f", "right_header": "#9b5d2e", "map_header": "#263d4c",
        "tooltip": "#fffbd6", "tooltip_text": "#18232c",
    },
    "light_grey": {
        "window": "#d8dde1", "surface": "#eef1f3", "surface_alt": "#dfe5e9",
        "text": "#1b2831", "muted": "#52616c", "border": "#83939f",
        "header": "#30495e", "header_text": "#f6f8fa", "header_muted": "#d5e5ef",
        "header_button": "#3b5c74", "header_active": "#4a708b",
        "button": "#d4dbe0", "button_active": "#c4d2dc", "entry": "#f8f9fa",
        "selection": "#187ecb", "inactive_selection": "#829bab",
        "tab_bar": "#899ca9", "tab_default": "#dce5eb", "tab_text": "#14232d",
        "tab_lock_bg": "#414141", "tab_lock_fg": "#fafafa",
        "menu": "#e1e5e8", "menu_text": "#15212a", "menu_disabled": "#727b82",
        "menu_active": "#147fc7", "menu_active_text": "#ffffff", "separator": "#a1abb2",
        "gutter": "#d5dde2", "gutter_text": "#52616c", "content": "#f4f6f7",
        "diff": "#f2d29a", "current_diff": "#eaa34d", "match": "#eee09a",
        "left_header": "#326789", "right_header": "#90603b", "map_header": "#304552",
        "tooltip": "#fff7c7", "tooltip_text": "#18232c",
    },
    "dark": {
        "window": "#20262c", "surface": "#282f36", "surface_alt": "#323b43",
        "text": "#edf2f6", "muted": "#a9b8c3", "border": "#5d6d79",
        "header": "#142b3d", "header_text": "#f4f8fb", "header_muted": "#bcd9e9",
        "header_button": "#294b64", "header_active": "#376985",
        "button": "#354049", "button_active": "#465865", "entry": "#242b31",
        "selection": "#1976bd", "inactive_selection": "#526b7b",
        "tab_bar": "#354754", "tab_default": "#657887", "tab_text": "#ffffff",
        "tab_lock_bg": "#dedede", "tab_lock_fg": "#252525",
        "menu": "#2b3238", "menu_text": "#edf2f6", "menu_disabled": "#87939c",
        "menu_active": "#176fa8", "menu_active_text": "#ffffff", "separator": "#53616b",
        "gutter": "#242c32", "gutter_text": "#a8bac7", "content": "#1f252a",
        "diff": "#604b27", "current_diff": "#9a5d1f", "match": "#665e28",
        "left_header": "#205777", "right_header": "#754624", "map_header": "#172b37",
        "tooltip": "#414733", "tooltip_text": "#f4f2d8",
    },
}


def color_scheme(name: str) -> dict[str, str]:
    return COLOR_SCHEMES.get(name, COLOR_SCHEMES["light"])


def tab_lock_metrics(linespace: int, style: str) -> tuple[int, int, int]:
    """Same badge size in active/inactive tabs; reuse existing title padding."""
    height = max(30, linespace + 13)
    size = max(16, min(linespace, height - max(4, round(height*.22)) - 7))
    return min(size, 128), (5 if style == 'rounded' else 4), 3


def configure_ttk_theme(root, palette: dict[str, str]) -> None:
    """Apply one coherent palette to all ttk controls in this interpreter."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    common = {"background": palette["window"], "foreground": palette["text"]}
    style.configure(".", **common)
    style.configure("TFrame", background=palette["window"])
    style.configure("TLabel", background=palette["window"], foreground=palette["text"])
    style.configure("TButton", background=palette["button"], foreground=palette["text"],
                    bordercolor=palette["border"], lightcolor=palette["button"],
                    darkcolor=palette["border"])
    style.map("TButton", background=[("active", palette["button_active"]),
                                     ("pressed", palette["selection"])],
              foreground=[("pressed", "#ffffff")])
    for name in ("TCheckbutton", "TRadiobutton"):
        style.configure(name, background=palette["window"], foreground=palette["text"])
        style.map(name, background=[("active", palette["window"])],
                  foreground=[("disabled", palette["muted"])])
    style.configure("TEntry", fieldbackground=palette["entry"], foreground=palette["text"],
                    insertcolor=palette["text"], bordercolor=palette["border"])
    style.configure("TCombobox", fieldbackground=palette["entry"], background=palette["button"],
                    foreground=palette["text"], arrowcolor=palette["text"],
                    bordercolor=palette["border"])
    style.map("TCombobox", fieldbackground=[("readonly", palette["entry"])],
              foreground=[("readonly", palette["text"])])
    style.configure("Treeview", background=palette["surface"], fieldbackground=palette["surface"],
                    foreground=palette["text"], bordercolor=palette["border"])
    style.configure("Treeview.Heading", background=palette["surface_alt"], foreground=palette["text"],
                    bordercolor=palette["border"])
    style.map("Treeview.Heading", background=[("active", palette["button_active"])])
    for name, selected in (("Active.Treeview", palette["selection"]),
                           ("Inactive.Treeview", palette["inactive_selection"]),
                           ("PFCSearch.Treeview", palette["selection"]),
                           ("PFCCompare.Treeview", palette["selection"])):
        style.configure(name, background=palette["surface"], fieldbackground=palette["surface"],
                        foreground=palette["text"], bordercolor=palette["border"])
        style.map(name, background=[("selected", selected)],
                  foreground=[("selected", "#ffffff")])
        style.configure(name + ".Heading", background=palette["surface_alt"],
                        foreground=palette["text"], bordercolor=palette["border"])
    style.configure("TNotebook", background=palette["tab_bar"], bordercolor=palette["border"])
    style.configure("TNotebook.Tab", background=palette["tab_default"], foreground=palette["tab_text"])
    style.configure("TScrollbar", background=palette["button"], troughcolor=palette["surface_alt"],
                    arrowcolor=palette["text"], bordercolor=palette["border"])


def add_scaled_cascade(menu: tk.Menu, label: str, submenu: tk.Menu) -> None:
    """Keep a native menu model; PFC draws header cascades itself."""
    menu.add_cascade(label=label, menu=submenu)


def align_scaled_cascade_arrows(menu: tk.Menu) -> None:
    """Compatibility no-op for the native menu model."""


def _refresh_scaled_indicators(menu: tk.Menu) -> None:
    for index, variable, value in getattr(menu, "_pfc_scaled_indicators", ()):
        selected = bool(variable.get()) if value is None else variable.get() == value
        menu.entryconfigure(index, accelerator="✓" if selected else "")


def _register_scaled_indicator(menu: tk.Menu, variable, value) -> None:
    if not hasattr(menu, "_pfc_scaled_indicators"):
        menu._pfc_scaled_indicators = []
        menu.configure(postcommand=lambda target=menu: _refresh_scaled_indicators(target))
    menu._pfc_scaled_indicators.append((menu.index("end"), variable, value))
    _refresh_scaled_indicators(menu)


def add_scaled_checkbutton(menu: tk.Menu, label: str, variable, command=None) -> None:
    menu.add_checkbutton(label=label, variable=variable, command=command, indicatoron=False)
    _register_scaled_indicator(menu, variable, None)


def add_scaled_radiobutton(menu: tk.Menu, label: str, value, variable, command=None) -> None:
    menu.add_radiobutton(label=label, value=value, variable=variable, command=command,
                         indicatoron=False)
    _register_scaled_indicator(menu, variable, value)


class HeaderPopupController:
    """Draw scalable, keyboard-accessible header menus without native glyphs."""

    def __init__(self, owner, descriptions=None):
        self.owner = owner
        self.descriptions = descriptions or {}
        self.popups = []
        self.tooltip = None
        self.keyboard_pointer = None

    def show(self, button, menu) -> None:
        self.show_at(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height(), menu)

    def show_at(self, x, y, menu) -> None:
        """Use the same scalable cascade model for header and context menus."""
        self.close_all()
        self.keyboard_pointer = None
        popup = _HeaderPopup(self, menu, None)
        self.popups = [popup]
        popup.show(x, y)
        popup.top.grab_set_global()
        popup.canvas.focus_force()

    def open_child(self, parent, index) -> None:
        depth = self.popups.index(parent)
        submenu_name = parent.menu.entrycget(index, "menu")
        if not submenu_name:
            return
        submenu = parent.menu.nametowidget(submenu_name)
        # Reuse a visible cascade. Recreating it during pointer/focus events
        # can lose the next level and leave the parent highlighted but closed.
        if len(self.popups) > depth + 1 and self.popups[depth + 1].menu is submenu:
            return
        self._close_from(depth + 1)
        child = _HeaderPopup(self, submenu, parent)
        self.popups.append(child)
        row_top = parent.row_bounds[index][0]
        x = parent.top.winfo_rootx() + parent.width - 1
        y = parent.top.winfo_rooty() + row_top
        left, _top, width, _height = virtual_screen_bounds(child.top)
        if x + child.width > left + width:
            x = parent.top.winfo_rootx() - child.width + 1
        child.show(x, y)

    def popup_at(self, x, y):
        # A global grab can deliver another popup's event to the root window.
        # Hit-test screen coordinates, including cascades flipped to the left.
        for popup in reversed(self.popups):
            if (popup.top.winfo_rootx() <= x < popup.top.winfo_rootx()+popup.width
                    and popup.top.winfo_rooty() <= y < popup.top.winfo_rooty()+popup.height):
                return popup
        return None

    def close_child(self, popup) -> None:
        depth = self.popups.index(popup)
        parent = popup.parent
        self._close_from(depth)
        if parent is not None:
            parent.canvas.focus_force()

    def close_all(self) -> None:
        self._hide_tooltip()
        if self.popups:
            try:
                self.popups[0].top.grab_release()
            except tk.TclError:
                pass
        self._close_from(0)

    def _close_from(self, depth: int) -> None:
        self._hide_tooltip()
        for popup in reversed(self.popups[depth:]):
            try:
                popup.top.destroy()
            except tk.TclError:
                pass
        del self.popups[depth:]

    def pointer_inside(self, x: int, y: int) -> bool:
        return any(p.top.winfo_exists() and p.top.winfo_rootx() <= x < p.top.winfo_rootx() + p.width
                   and p.top.winfo_rooty() <= y < p.top.winfo_rooty() + p.height
                   for p in self.popups)

    def schedule_tooltip(self, popup, index) -> None:
        self._hide_tooltip()
        label = popup.menu.entrycget(index, "label")
        self.tooltip = popup.help_tip
        self.tooltip.text = self.descriptions.get(label, label)
        self.tooltip._enter()

    def _hide_tooltip(self) -> None:
        if self.tooltip is not None:
            self.tooltip.hide()
            self.tooltip = None


class _HeaderPopup:
    BG, FG, DISABLED, ACTIVE_BG, ACTIVE_FG, BORDER = (
        "#f0f0f0", "#101010", "#808080", "#087bdc", "#ffffff", "#8a8a8a")

    def __init__(self, controller, menu, parent):
        self.controller, self.menu, self.parent = controller, menu, parent
        palette = getattr(controller.owner, "palette", COLOR_SCHEMES["light"])
        self.BG, self.FG = palette["menu"], palette["menu_text"]
        self.DISABLED, self.ACTIVE_BG = palette["menu_disabled"], palette["menu_active"]
        self.ACTIVE_FG, self.BORDER = palette["menu_active_text"], palette["border"]
        self.SEPARATOR = palette["separator"]
        self.top = tk.Toplevel(parent.top if parent is not None else controller.owner)
        self.top.withdraw()
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.font = tkfont.nametofont("TkMenuFont")
        self.selected = None
        self.items = []
        self.row_bounds = {}
        self._run_postcommand()
        self._measure()
        self.canvas = tk.Canvas(self.top, width=self.width, height=self.height, background=self.BG,
                                highlightthickness=1, highlightbackground=self.BORDER, takefocus=True)
        self.canvas.pack()
        self.top.palette = palette
        self.help_tip = ToolTip(self.canvas, "", bind_hover=False)
        self.canvas.bind("<Motion>", self._motion)
        self.canvas.bind("<Enter>", self._motion)
        self.top.bind("<Motion>", self._motion)
        self.top.bind("<ButtonRelease-1>", self._click)
        self.canvas.bind("<Leave>", lambda _event: self.controller._hide_tooltip())
        self.canvas.bind("<ButtonRelease-1>", self._click)
        self.canvas.bind("<ButtonPress-1>", self._outside_click)
        self.top.bind("<ButtonPress-1>", self._outside_click, add="+")
        self.canvas.bind("<Down>", lambda _event: self._move(1))
        self.canvas.bind("<Up>", lambda _event: self._move(-1))
        self.canvas.bind("<Right>", lambda _event: self._open_selected())
        self.canvas.bind("<Left>", lambda _event: self._left())
        self.canvas.bind("<Return>", lambda _event: self._invoke_selected())
        self.canvas.bind("<space>", lambda _event: self._invoke_selected())
        self.canvas.bind("<Escape>", lambda _event: self._escape())
        self._draw()

    def _run_postcommand(self) -> None:
        command = self.menu.cget("postcommand")
        if command:
            try:
                self.menu.tk.eval(command)
            except tk.TclError:
                pass

    def _measure(self) -> None:
        end = self.menu.index("end")
        label_width = accelerator_width = 0
        line = self.font.metrics("linespace")
        self.row_height = max(24, line + max(8, line // 3))
        y = 3
        for index in range(end + 1 if end is not None else 0):
            kind = self.menu.type(index)
            if kind == "tearoff":
                continue
            if kind == "separator":
                height = max(7, line // 3)
                self.items.append((index, kind, "", "", "normal"))
            else:
                label = self.menu.entrycget(index, "label")
                accelerator = self.menu.entrycget(index, "accelerator")
                state = self.menu.entrycget(index, "state")
                label_width = max(label_width, self.font.measure(label))
                if accelerator != "✓":
                    accelerator_width = max(accelerator_width, self.font.measure(accelerator))
                height = self.row_height
                self.items.append((index, kind, label, accelerator, state))
            self.row_bounds[index] = (y, y + height)
            y += height
        marker = max(line, self.font.measure("▶"), self.font.measure("✓"))
        self.left_pad = max(10, line // 2)
        self.label_x = self.left_pad
        self.marker_width = marker + self.left_pad
        gap = max(18, line)
        self.width = self.left_pad + label_width + gap + accelerator_width + self.marker_width
        self.height = y + 3
        self.accelerator_x = self.width - self.marker_width - self.left_pad
        self.marker_x = self.width - self.left_pad

    def show(self, x: int, y: int) -> None:
        x, y = clamp_popup_position(
            x, y, self.width, self.height, virtual_screen_bounds(self.top))
        self.top.geometry(f"{self.width}x{self.height}+{x}+{y}")
        self.top.deiconify()
        self.top.lift()

    def _draw(self) -> None:
        self.canvas.delete("all")
        for index, kind, label, accelerator, state in self.items:
            top, bottom = self.row_bounds[index]
            if kind == "separator":
                y = (top + bottom) // 2
                self.canvas.create_line(self.left_pad, y, self.width - self.left_pad, y,
                                        fill=self.SEPARATOR)
                continue
            active = index == self.selected and state != "disabled"
            bg = self.ACTIVE_BG if active else self.BG
            fg = self.ACTIVE_FG if active else (self.DISABLED if state == "disabled" else self.FG)
            if index in getattr(self.menu, '_vcs_headers', {}).values():
                # Status summaries are informative, not unavailable commands.
                fg = self.FG
            self.canvas.create_rectangle(1, top, self.width - 1, bottom, fill=bg, outline="")
            self.canvas.create_text(self.label_x, (top + bottom) // 2, text=label, anchor="w",
                                    fill=fg, font=self.font)
            if accelerator and accelerator != "✓":
                self.canvas.create_text(self.accelerator_x, (top + bottom) // 2, text=accelerator,
                                        anchor="e", fill=fg, font=self.font)
            marker = "▶" if kind == "cascade" else ("✓" if accelerator == "✓" else "")
            if marker:
                self.canvas.create_text(self.marker_x, (top + bottom) // 2, text=marker,
                                        anchor="e", fill=fg, font=self.font)

    def refresh(self) -> None:
        """Refresh an asynchronous menu model without recreating its window/grab."""
        self.items = []
        self.row_bounds = {}
        self._measure()
        if self.selected not in self.row_bounds:
            self.selected = None
        self.canvas.configure(width=self.width, height=self.height)
        self.show(self.top.winfo_rootx(), self.top.winfo_rooty())
        self._draw()

    def _index_at(self, y):
        for index, (top, bottom) in self.row_bounds.items():
            if top <= y < bottom and self.menu.type(index) != "separator":
                return index
        return None

    def _select(self, index, open_cascade=True) -> None:
        if index == self.selected:
            if (open_cascade and index is not None and self.menu.type(index) == 'cascade'
                    and self.menu.entrycget(index, 'state') != 'disabled'):
                self.controller.open_child(self, index)
            return
        self.selected = index
        self._draw()
        if index is not None:
            if self.menu.type(index) == "cascade" and self.menu.entrycget(index, "state") != "disabled":
                if open_cascade:
                    self.controller.open_child(self, index)
                else:
                    self.controller._close_from(self.controller.popups.index(self) + 1)
            else:
                self.controller._close_from(self.controller.popups.index(self) + 1)
                self.controller.schedule_tooltip(self, index)

    def _event_target(self, event):
        if hasattr(event, 'x_root') and hasattr(event, 'y_root'):
            target = self.controller.popup_at(event.x_root, event.y_root)
            return target, event.y_root-target.top.winfo_rooty() if target else 0
        return self, event.y

    def _motion(self, event) -> str:
        if hasattr(event, 'x_root') and hasattr(event, 'y_root'):
            point = (event.x_root, event.y_root)
            if point == self.controller.keyboard_pointer:
                return 'break'
            self.controller.keyboard_pointer = None
        target, y = self._event_target(event)
        if target is not None:
            target._select(target._index_at(y))
        return 'break'

    def _outside_click(self, event) -> str | None:
        if not self.controller.pointer_inside(event.x_root, event.y_root):
            self.controller.close_all()
            return "break"
        return None

    def _click(self, event) -> str:
        target, y = self._event_target(event)
        if target is None:
            self.controller.close_all()
            return 'break'
        index = target._index_at(y)
        if index is not None:
            target._select(index)
            target._invoke(index)
        return "break"

    def _enabled_indexes(self):
        return [index for index, kind, _label, _accelerator, state in self.items
                if kind != "separator" and state != "disabled"]

    def _move(self, direction: int) -> str:
        self.controller.keyboard_pointer = self.controller.owner.winfo_pointerxy()
        indexes = self._enabled_indexes()
        if not indexes:
            return "break"
        if self.selected not in indexes:
            target = indexes[0 if direction > 0 else -1]
        else:
            target = indexes[(indexes.index(self.selected) + direction) % len(indexes)]
        self._select(target, open_cascade=False)
        return "break"

    def _open_selected(self) -> str:
        self.controller.keyboard_pointer = self.controller.owner.winfo_pointerxy()
        if self.selected is not None and self.menu.type(self.selected) == "cascade":
            self.controller.open_child(self, self.selected)
            child = self.controller.popups[self.controller.popups.index(self)+1]
            child.canvas.focus_force()
            if child.selected is None:
                child._move(1)
        return "break"

    def _invoke_selected(self) -> str:
        if self.selected is not None:
            self._invoke(self.selected)
        return "break"

    def _invoke(self, index) -> None:
        if self.menu.entrycget(index, "state") == "disabled":
            return
        if self.menu.type(index) == "cascade":
            self.controller.open_child(self, index)
            self.controller.popups[-1].canvas.focus_force()
            return
        menu, controller = self.menu, self.controller
        controller.close_all()
        menu.invoke(index)

    def _left(self) -> str:
        self.controller.keyboard_pointer = self.controller.owner.winfo_pointerxy()
        if self.parent is not None:
            self.controller.close_child(self)
        return "break"

    def _escape(self) -> str:
        self.controller.keyboard_pointer = self.controller.owner.winfo_pointerxy()
        if self.parent is not None:
            self.controller.close_child(self)
        else:
            self.controller.close_all()
        return "break"


class ChamferNotebook(ttk.Frame):
    """A small Notebook-compatible container with canvas-drawn colored tabs."""

    def __init__(self, master, on_color_changed=None, on_lock_changed=None,
                 on_tabs_reordered=None, on_tab_drag=None,
                 tab_style="right_skirt", **kwargs):
        super().__init__(master, **kwargs)
        self.on_color_changed = on_color_changed or (lambda _child, _color: None)
        self.on_lock_changed = on_lock_changed or (lambda _child, _mode: None)
        self.on_tabs_reordered = on_tabs_reordered or (lambda: None)
        self.on_tab_drag = on_tab_drag or (lambda _action, _tabs, _child, _event: False)
        self._tabs = []
        self._texts = {}
        self._colors = {}
        self._locks = {}
        self._lock_images = {}
        self._lock_image_spec = None
        self._selected = None
        if tab_style == "compact":
            tab_style = "right_skirt"
        self._tab_style = tab_style if tab_style in TAB_STYLES else "right_skirt"
        self._hitboxes = []
        self._drag_tab = None
        self._drag_start_x = 0
        self._drag_original_order = ()
        self._drag_moved = False
        self._drag_external = False
        self._drop_position = None
        self.panel_number = None
        self._group_ranges = []
        self.group_bar = tk.Canvas(self, height=1, highlightthickness=0, takefocus=False)
        self._group_tip = ''
        ToolTip(self.group_bar, lambda:self._group_tip)
        self.group_bar.bind('<Motion>', self._group_motion)
        self.group_bar.bind('<Button-1>', self._group_click)
        self.bar = tk.Canvas(self, height=34, takefocus=True, highlightthickness=2,
                             highlightbackground="#71879a", highlightcolor="#0078d4",
                             background="#9eafbd")
        self.bar.pack(fill="x", side="top")
        self.tab_scroll=ttk.Scrollbar(self,orient='horizontal',command=self._scroll_tabs)
        self.bar.configure(xscrollcommand=self._tab_view_changed)
        for widget in (self.bar,self.group_bar):
            widget.bind('<MouseWheel>',lambda e:self._wheel_tabs(-1 if e.delta>0 else 1))
            widget.bind('<Button-4>',lambda e:self._wheel_tabs(-1))
            widget.bind('<Button-5>',lambda e:self._wheel_tabs(1))
        self.bar.bind("<ButtonPress-1>", self._tab_press)
        self.bar.bind("<FocusIn>", lambda _event: self.bar.configure(highlightthickness=2))
        self.bar.bind("<B1-Motion>", self._tab_motion)
        self.bar.bind("<ButtonRelease-1>", self._tab_release)
        self.bar.bind("<Button-3>", self._popup)
        self.bar.bind("<Shift-F10>", self._popup_keyboard)
        self.bar.bind("<KeyPress-Menu>", self._popup_keyboard)
        self.bar.bind("<Configure>", lambda _e: self._draw())
        self.palette = COLOR_SCHEMES["light"]

    def add(self, child, text="", color="default", lock="unlocked", position=None, **_kwargs):
        if child not in self._tabs:
            if position is None:
                self._tabs.append(child)
            else:
                self._tabs.insert(max(0, min(position, len(self._tabs))), child)
        self._texts[child] = text
        self._colors[child] = normalize_tab_color(color)
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
        self._see_tab(child)
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

    def reorder(self, tab, position, notify=True):
        child = self._resolve(tab)
        old_position = self._tabs.index(child)
        new_position = max(0, min(int(position), len(self._tabs) - 1))
        if old_position == new_position:
            return False
        self._tabs.pop(old_position)
        self._tabs.insert(new_position, child)
        self._draw()
        if notify:
            self.on_tabs_reordered()
            self.event_generate("<<NotebookTabsReordered>>")
        return True

    def insertion_index_at(self, x_root, y_root):
        """Return a tab insertion index when a screen point is over this tab bar."""
        if not self.bar.winfo_viewable():
            return None
        left, top = self.bar.winfo_rootx(), self.bar.winfo_rooty()
        if not (left <= x_root < left + self.bar.winfo_width() and
                top <= y_root < top + self.bar.winfo_height()):
            return None
        x = self.bar.canvasx(x_root - left)
        insertion = 0
        for tab_left, tab_right, _child in self._hitboxes:
            if x > (tab_left + tab_right) / 2:
                insertion += 1
        return insertion

    def _event_root(self, event):
        return (getattr(event, "x_root", self.bar.winfo_rootx() + event.x),
                getattr(event, "y_root", self.bar.winfo_rooty() +
                        getattr(event, "y", max(1, self.bar.winfo_height() // 2))))

    def set_drop_position(self, position=None):
        self._drop_position = position
        self._draw()

    def set_color(self, tab, color, notify=True):
        child = self._resolve(tab)
        self._colors[child] = normalize_tab_color(color)
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
        if style == "compact":
            style = "right_skirt"
        self._tab_style = style if style in TAB_STYLES else "right_skirt"
        self._draw()

    def set_theme(self, palette):
        self.palette = palette
        self.bar.configure(background=palette["tab_bar"],
                           highlightbackground=palette["border"],
                           highlightcolor=palette["selection"])
        self._draw()

    def _resolve(self, tab):
        if tab in self._tabs:
            return tab
        return self.nametowidget(tab)

    def _draw(self):
        self.bar.delete("all"); self._hitboxes.clear()
        font = getattr(self, '_font_override', None) or tkfont.nametofont("TkDefaultFont")
        font_spec = (font.actual('family'), int(font.cget('size')))
        if getattr(self, '_active_title_font_spec', None) != font_spec:
            if not hasattr(self, '_active_title_font'): self._active_title_font = tkfont.Font(self)
            self._active_title_font.configure(family=font_spec[0], size=font_spec[1], weight='bold')
            self._active_title_font_spec = font_spec
        active_font = self._active_title_font
        right_skirt = self._tab_style == "right_skirt"
        height = max(30, font.metrics("linespace") + 13)
        icon_size, icon_inset, icon_gap = tab_lock_metrics(font.metrics('linespace'), self._tab_style)
        image_spec = (icon_size, self.palette['tab_lock_bg'], self.palette['tab_lock_fg'])
        if image_spec != self._lock_image_spec:
            self._lock_images.clear()
            self._lock_image_spec = image_spec
        self.bar.configure(height=height)
        overlap = {"right_skirt": -2, "rounded": 2, "squarish": 0}[self._tab_style]
        x = 3
        drawings = []
        for child in self._tabs:
            text = self._texts.get(child, "")
            lock = self._locks.get(child, "unlocked")
            selected = child is self._selected
            padding = 20 if right_skirt else 28
            title_width = max(font.measure(text), active_font.measure(text))
            width = max(52 if right_skirt else 58, title_width + padding)
            if lock in {'locked', 'reset'}:
                width = max(width, title_width + icon_inset + icon_size + icon_gap + 6)
            key = normalize_tab_color(self._colors.get(child, "default"))
            color = self.palette["tab_default"] if key == "default" else TAB_COLORS[key][1]
            top = 0 if selected else max(4, round(height * 0.22))
            bottom = height if selected else height - 3
            corner = max(6, round(height * 0.28))
            if self._tab_style == "rounded":
                half_corner = round(corner * 0.45)
                points = (x, bottom,
                          x, top + corner,
                          x + 1, top + half_corner,
                          x + half_corner, top + 1,
                          x + corner, top,
                          x + width - corner, top,
                          x + width - half_corner, top + 1,
                          x + width - 1, top + half_corner,
                          x + width, top + corner,
                          x + width, bottom)
                smooth, inset = False, corner
            elif self._tab_style == "right_skirt":
                tail = max(9, round(height * 0.32))
                skirt_height = max(12, round(height * 0.42))
                points = (x, bottom, x, top,
                          x + width - 5, top, x + width, top + 5,
                          x + width, bottom - skirt_height,
                          x + width + 1, bottom - 8,
                          x + width + 4, bottom - 4,
                          x + width + tail, bottom)
                smooth, inset = False, 5
            else:
                points = (x, bottom, x, top, x + width, top, x + width, bottom)
                smooth, inset = False, 4
            text_color = self.palette["tab_text"] if key == "default" else "#10202c"
            drawings.append((selected, points, color, text, text_color, x, width, top,
                             child, lock, inset, smooth))
            self._hitboxes.append((x, x + width, child))
            x += width - overlap
        # Paint the selected polygon last so its edges sit in front of
        # both neighbours instead of being covered by the tab to its right.
        for selected, points, color, text, text_color, left, width, top, child, lock, tab_inset, smooth in sorted(
                drawings, key=lambda item: item[0]):
            self.bar.create_polygon(points, fill=color,
                                    outline=self.palette["text"] if selected else self.palette["border"],
                                    width=3 if selected else 1, smooth=smooth, splinesteps=18)
            if selected:
                self.bar.create_line(left + 2, height - 2, left + width - 2, height - 2,
                                     fill=color, width=4)
            if lock in {'locked', 'reset'}:
                if lock not in self._lock_images:
                    self._lock_images[lock] = tk.PhotoImage(master=self.bar,
                        data=tab_lock_icon_png(lock, *image_spec), format='png')
                center_y = (top + (height if selected else height - 3)) / 2
                self.bar.create_image(left + icon_inset, center_y, anchor='w',
                    image=self._lock_images[lock], tags=('tab-lock-icon', 'lock:' + str(id(child))))
                self.bar.create_text(left + icon_inset + icon_size + icon_gap, center_y,
                    anchor='w', text=text, font=active_font if selected else font, fill=text_color,
                    tags=('tab-title', 'title:' + str(id(child))))
            else:
                self.bar.create_text(left + width / 2, (top + height) / 2 + 1, text=text, font=active_font if selected else font,
                    fill=text_color, tags=('tab-title', 'title:' + str(id(child))))
        if self._drop_position is not None:
            if not self._hitboxes or self._drop_position <= 0:
                marker_x = self._hitboxes[0][0] if self._hitboxes else 3
            elif self._drop_position >= len(self._hitboxes):
                marker_x = self._hitboxes[-1][1]
            else:
                marker_x = self._hitboxes[self._drop_position][0]
            self.bar.create_line(marker_x, 2, marker_x, height - 2,
                                 fill="#0067c0", width=max(3, round(height * 0.11)))
        self.bar.configure(scrollregion=(0, 0, max(x + overlap, self.bar.winfo_width()), height))
        self._draw_groups(font)
        if self.bar.winfo_manager()=='pack' and x+overlap>self.bar.winfo_width()+2:
            self.tab_scroll.pack(fill='x',after=self.bar)
        else:
            self.tab_scroll.pack_forget()

    def _tab_view_changed(self,first,last):
        self.tab_scroll.set(first,last)
        self.group_bar.xview_moveto(first)

    def _scroll_tabs(self,*args):
        self.bar.xview(*args)
        self.group_bar.xview_moveto(self.bar.xview()[0])

    def _wheel_tabs(self,direction):
        self._scroll_tabs('scroll',direction*3,'units')
        return 'break'

    def _see_tab(self,child):
        total=max(1,float(self.bar.cget('scrollregion').split()[2]))
        start=self.bar.canvasx(0);width=self.bar.winfo_width()
        for left,right,pane in self._hitboxes:
            if pane is child:
                if left<start:self._scroll_tabs('moveto',max(0,left-3)/total)
                elif right>start+width:self._scroll_tabs('moveto',max(0,right-width+8)/total)
                break

    def _group_identity(self, child):
        return self.panel_number, getattr(child,'tab_group','')

    def _draw_groups(self, font):
        self.group_bar.delete('all'); self._group_ranges=[]
        if self.bar.winfo_manager()!='pack' or not self._tabs or not any(self._group_identity(p)[0] for p in self._tabs):
            self.group_bar.pack_forget(); return
        if not hasattr(self,'_group_font'):self._group_font=tkfont.Font(self)
        self._group_font.configure(family=font.actual('family'),size=font.cget('size'),weight='normal')
        height=font.metrics('linespace')+5
        self.group_bar.configure(height=height,background=self.palette['tab_bar'])
        self.group_bar.pack(fill='x',side='top',before=self.bar)
        runs=[]
        for left,right,child in self._hitboxes:
            identity=self._group_identity(child)
            if runs and runs[-1][0]==identity:runs[-1][2]=right
            else:runs.append([identity,left,right,child])
        ink=self.palette['header_text'] if self.palette['tab_text']=='#ffffff' else self.palette['text']
        for (number,group),left,right,child in runs:
            label=str(number)+((' · '+group) if group else '')
            full=tr('Panel {number}',number=number)+((' · '+tr('Group')+': '+group) if group else '')
            shown=label
            available=max(1,right-left-22)
            if font.measure(shown)>available:
                while len(shown)>1 and font.measure(shown+'…')>available:shown=shown[:-1]
                shown=shown+'…' if len(shown)>1 else str(number)
            self.group_bar.create_text(left+4,height/2,anchor='w',text=shown,font=self._group_font,
                                       fill=ink,tags=('tab-group-label',))
            start=min(right-4,left+font.measure(shown)+10)
            self.group_bar.create_line(start,height/2,right-3,height/2,right-3,height-2,
                                       fill=ink,width=1,tags=('tab-group-line',))
            self._group_ranges.append((left,right,child,full))
        self.group_bar.configure(scrollregion=self.bar.cget('scrollregion'))
        self.group_bar.xview_moveto(self.bar.xview()[0])

    def _group_motion(self,event):
        x=self.group_bar.canvasx(event.x)
        self._group_tip=next((label for a,b,_p,label in self._group_ranges if a<=x<=b),'')

    def _group_click(self,event):
        x=self.group_bar.canvasx(event.x)
        pane=next((p for a,b,p,_label in self._group_ranges if a<=x<=b),None)
        if pane is not None:self.select(pane)

    def _at(self, x):
        x=self.bar.canvasx(x)
        if self._selected is not None:
            for left, right, child in self._hitboxes:
                if child is self._selected and left <= x <= right:
                    return child
        for left, right, child in reversed(self._hitboxes):
            if left <= x <= right:
                return child
        return None

    def _tab_press(self, event):
        child = self._at(event.x)
        if child is not None:
            self.select(child)
            self._drag_tab = child
            self._drag_start_x = event.x
            self._drag_original_order = tuple(self._tabs)
            self._drag_moved = False
            self._drag_external = False

    def _tab_motion(self, event):
        child = self._drag_tab
        if child is None:
            return
        if not self._drag_moved and abs(event.x - self._drag_start_x) < 5:
            return
        self._drag_moved = True
        x_root, y_root = self._event_root(event)
        synthetic_local = not hasattr(event, "x_root") or not hasattr(event, "y_root")
        own_bar = synthetic_local or self.insertion_index_at(x_root, y_root) is not None
        if not own_bar:
            self._drag_external = True
            accepted = self.on_tab_drag("motion", self, child, event)
            self.bar.configure(cursor="hand2" if accepted else "fleur")
            return
        if self._drag_external:
            self.on_tab_drag("cancel", self, child, event)
            self._tabs[:] = [tab for tab in self._drag_original_order if tab in self._tabs]
            self._draw()
            self._drag_external = False
        self.bar.configure(cursor="fleur")
        insertion = 0
        for left, right, _candidate in self._hitboxes:
            if self.bar.canvasx(event.x) > (left + right) / 2:
                insertion += 1
        current = self._tabs.index(child)
        if insertion > current:
            insertion -= 1
        self.reorder(child, insertion, notify=False)

    def _tab_release(self, event):
        if self._drag_tab is None:
            return
        child = self._drag_tab
        x_root, y_root = self._event_root(event)
        synthetic_local = not hasattr(event, "x_root") or not hasattr(event, "y_root")
        external = self._drag_external or (not synthetic_local and
                                            self.insertion_index_at(x_root, y_root) is None)
        if external:
            self._tabs[:] = [tab for tab in self._drag_original_order if tab in self._tabs]
            self._draw()
            self.on_tab_drag("drop", self, child, event)
        changed = self._drag_moved and tuple(self._tabs) != self._drag_original_order
        self._drag_tab = None
        self._drag_original_order = ()
        self._drag_moved = False
        self._drag_external = False
        self.bar.configure(cursor="")
        if changed and not external:
            self.on_tabs_reordered()
            self.event_generate("<<NotebookTabsReordered>>")

    def _build_context_menu(self, child=None):
        old=getattr(self,'_context_menu',None)
        if old is not None: old.destroy()
        menu = tk.Menu(self, tearoff=False, font=tkfont.nametofont("TkMenuFont"))
        self._context_menu=menu
        if child is not None:
            owner=self._root()
            if hasattr(owner,'set_tab_group') and child in owner.all_panes():
                groups=tk.Menu(menu,tearoff=False,font='TkMenuFont')
                groups.add_command(label=tr('Set group…'),command=lambda:owner.edit_tab_group(child))
                names=sorted({getattr(p,'tab_group','') for p in owner.all_panes()}-{''},key=str.casefold)
                groups._group_var=chosen=tk.StringVar(self,value=getattr(child,'tab_group',''))
                for name in names:
                    add_scaled_radiobutton(groups,name,name,chosen,command=lambda n=name:owner.set_tab_group(child,n))
                groups.add_separator()
                groups.add_command(label=tr('Remove from group'),command=lambda:owner.set_tab_group(child,''),
                                   state='normal' if getattr(child,'tab_group','') else 'disabled')
                add_scaled_cascade(menu,tr('Tab Group'),groups)
            colors=tk.Menu(menu,tearoff=False,font='TkMenuFont')
            menu._color_var=color=tk.StringVar(self,value=self._colors.get(child,'default'))
            for key, (label, _color) in TAB_COLORS.items():
                add_scaled_radiobutton(colors,tr(label),key,color,
                                       command=lambda value=key:self.set_color(child,value))
            add_scaled_cascade(menu,tr('Tab Color'),colors)
            menu.add_separator()
            menu._lock_var=lock_mode=tk.StringVar(self,value=self._locks.get(child,'unlocked'))
            for label, value in (("Unlocked", "unlocked"),
                                 ("Lock (open folder in new tab)", "locked"),
                                 ("Lock (open folder is allowed)", "reset")):
                add_scaled_radiobutton(menu, tr(label), value, lock_mode,
                                       command=lambda mode=value: self.set_lock(child, mode))
            menu.add_separator()
        owner=self._root()
        style_menu=getattr(owner,'tab_style_menu',None)
        if style_menu is not None:
            add_scaled_cascade(menu,tr('Tab Style'),style_menu)
        else:
            style_menu=tk.Menu(menu,tearoff=False,font='TkMenuFont')
            menu._style_var=selected=tk.StringVar(self,value=self._tab_style)
            for value,label in TAB_STYLES.items():
                add_scaled_radiobutton(style_menu,tr(label),value,selected,
                                       command=lambda value=value:self.set_style(value))
            add_scaled_cascade(menu,tr('Tab Style'),style_menu)
        workspace_picker = getattr(owner, 'show_workspace_picker', None)
        if callable(workspace_picker):
            menu.add_command(label=tr('Workspaces')+'…', command=workspace_picker)
        return menu

    def _show_context_menu(self,child,x,y):
        if child is not None:self.select(child)
        owner=self._root()
        controller=getattr(owner,'header_popup',None)
        if controller is not None:controller.close_all()
        menu=self._build_context_menu(child)
        if controller is not None:controller.show_at(x,y,menu)
        else:
            try:menu.tk_popup(x,y)
            finally:menu.grab_release()
        return 'break'

    def _popup(self,event):
        return self._show_context_menu(self._at(event.x),event.x_root,event.y_root)

    def _popup_keyboard(self,event=None):
        return self._show_context_menu(self._selected,self.bar.winfo_rootx()+12,
                                       self.bar.winfo_rooty()+self.bar.winfo_height())
