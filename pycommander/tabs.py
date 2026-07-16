from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from .i18n import tr


TAB_COLORS = {
    "default": ("Default", "#c7d3dd"),
    "amber": ("Amber", "#f2c14e"),
    "coral": ("Coral", "#f58b68"),
    "pink": ("Pink", "#e96ba8"),
    "violet": ("Violet", "#8d7be5"),
    "teal": ("Teal", "#55b9ae"),
}

TAB_STYLES = {
    "right_skirt": "Right Skirt",
    "rounded": "Rounded",
    "squarish": "Squarish",
}


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
        self.tooltip_job = None

    def show(self, button, menu) -> None:
        self.close_all()
        popup = _HeaderPopup(self, menu, None)
        self.popups = [popup]
        popup.show(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())
        popup.top.grab_set_global()
        popup.canvas.focus_force()

    def open_child(self, parent, index) -> None:
        depth = self.popups.index(parent)
        self._close_from(depth + 1)
        submenu_name = parent.menu.entrycget(index, "menu")
        if not submenu_name:
            return
        submenu = parent.menu.nametowidget(submenu_name)
        child = _HeaderPopup(self, submenu, parent)
        self.popups.append(child)
        row_top = parent.row_bounds[index][0]
        x = parent.top.winfo_rootx() + parent.width - 1
        y = parent.top.winfo_rooty() + row_top
        if x + child.width > child.top.winfo_screenwidth():
            x = parent.top.winfo_rootx() - child.width + 1
        child.show(x, y)
        child.canvas.focus_force()

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
        self.tooltip_job = self.owner.after(5000, lambda: self._show_tooltip(popup, index))

    def _show_tooltip(self, popup, index) -> None:
        self.tooltip_job = None
        if popup not in self.popups:
            return
        label = popup.menu.entrycget(index, "label")
        text = self.descriptions.get(label, label)
        tip = tk.Toplevel(self.owner)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        x, y = self.owner.winfo_pointerxy()
        tip.geometry(f"+{x + 14}+{y + 18}")
        tk.Label(tip, text=text, justify="left", background="#fffbd6", foreground="#18232c",
                 relief="solid", borderwidth=1, padx=7, pady=4,
                 font=tkfont.nametofont("TkDefaultFont")).pack()
        self.tooltip = tip

    def _hide_tooltip(self) -> None:
        if self.tooltip_job is not None:
            try:
                self.owner.after_cancel(self.tooltip_job)
            except tk.TclError:
                pass
            self.tooltip_job = None
        if self.tooltip is not None:
            try:
                self.tooltip.destroy()
            except tk.TclError:
                pass
            self.tooltip = None


class _HeaderPopup:
    BG, FG, DISABLED, ACTIVE_BG, ACTIVE_FG, BORDER = (
        "#f0f0f0", "#101010", "#808080", "#087bdc", "#ffffff", "#8a8a8a")

    def __init__(self, controller, menu, parent):
        self.controller, self.menu, self.parent = controller, menu, parent
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
        self.canvas.bind("<Motion>", self._motion)
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
        screen_w, screen_h = self.top.winfo_screenwidth(), self.top.winfo_screenheight()
        x = max(0, min(x, screen_w - self.width))
        y = max(0, min(y, screen_h - self.height))
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
                                        fill="#b8b8b8")
                continue
            active = index == self.selected and state != "disabled"
            bg = self.ACTIVE_BG if active else self.BG
            fg = self.ACTIVE_FG if active else (self.DISABLED if state == "disabled" else self.FG)
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

    def _index_at(self, y):
        for index, (top, bottom) in self.row_bounds.items():
            if top <= y < bottom and self.menu.type(index) != "separator":
                return index
        return None

    def _select(self, index) -> None:
        if index == self.selected:
            return
        self.selected = index
        self._draw()
        if index is not None:
            self.controller.schedule_tooltip(self, index)
            if self.menu.type(index) == "cascade" and self.menu.entrycget(index, "state") != "disabled":
                self.controller.open_child(self, index)
            else:
                self.controller._close_from(self.controller.popups.index(self) + 1)

    def _motion(self, event) -> None:
        self._select(self._index_at(event.y))

    def _outside_click(self, event) -> str | None:
        if not self.controller.pointer_inside(event.x_root, event.y_root):
            self.controller.close_all()
            return "break"
        return None

    def _click(self, event) -> str:
        index = self._index_at(event.y)
        if index is not None:
            self._select(index)
            self._invoke(index)
        return "break"

    def _enabled_indexes(self):
        return [index for index, kind, _label, _accelerator, state in self.items
                if kind != "separator" and state != "disabled"]

    def _move(self, direction: int) -> str:
        indexes = self._enabled_indexes()
        if not indexes:
            return "break"
        if self.selected not in indexes:
            target = indexes[0 if direction > 0 else -1]
        else:
            target = indexes[(indexes.index(self.selected) + direction) % len(indexes)]
        self._select(target)
        return "break"

    def _open_selected(self) -> str:
        if self.selected is not None and self.menu.type(self.selected) == "cascade":
            self.controller.open_child(self, self.selected)
            self.controller.popups[-1]._move(1)
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
        if self.parent is not None:
            self.controller.close_child(self)
        return "break"

    def _escape(self) -> str:
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
        self.bar = tk.Canvas(self, height=34, highlightthickness=0, background="#9eafbd")
        self.bar.pack(fill="x", side="top")
        self.bar.bind("<ButtonPress-1>", self._tab_press)
        self.bar.bind("<B1-Motion>", self._tab_motion)
        self.bar.bind("<ButtonRelease-1>", self._tab_release)
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
        x = x_root - left
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
        if style == "compact":
            style = "right_skirt"
        self._tab_style = style if style in TAB_STYLES else "right_skirt"
        self._draw()

    def _resolve(self, tab):
        if tab in self._tabs:
            return tab
        return self.nametowidget(tab)

    def _draw(self):
        self.bar.delete("all"); self._hitboxes.clear()
        font = tkfont.nametofont("TkDefaultFont")
        if not hasattr(self, "_active_tab_font"):
            self._active_tab_font = tkfont.Font(root=self, font=font)
        else:
            self._active_tab_font.configure(**font.actual())
        self._active_tab_font.configure(weight="bold")
        right_skirt = self._tab_style == "right_skirt"
        height = max(30, font.metrics("linespace") + 13)
        self.bar.configure(height=height)
        overlap = {"right_skirt": -2, "rounded": 2, "squarish": 0}[self._tab_style]
        x = 3
        drawings = []
        for child in self._tabs:
            text = self._texts.get(child, "")
            lock = self._locks.get(child, "unlocked")
            selected = child is self._selected
            padding = 20 if right_skirt else 28
            width = max(52 if right_skirt else 58, font.measure(text) + padding + (10 if selected else 0))
            color = TAB_COLORS[self._colors.get(child, "default")][1]
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
            drawings.append((selected, points, color, text, x, width, top, child, lock, inset, smooth))
            self._hitboxes.append((x, x + width, child))
            x += width - overlap
        # Paint the selected polygon last so its edges sit in front of
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
            draw_font = self._active_tab_font if selected else font
            self.bar.create_text(left + width / 2, (top + height) / 2 + 1, text=text, font=draw_font,
                                 fill="#10202c")
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

    def _at(self, x):
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
            if event.x > (left + right) / 2:
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

    def _popup(self, event):
        child = self._at(event.x)
        if child is None:
            return
        self.select(child)
        menu = tk.Menu(self, tearoff=False, font=tkfont.nametofont("TkMenuFont"))
        for key, (label, _color) in TAB_COLORS.items():
            menu.add_command(label=tr(label), command=lambda value=key: self.set_color(child, value))
        menu.add_separator()
        lock_mode = tk.StringVar(value=self._locks.get(child, "unlocked"))
        for label, value in (("Unlocked", "unlocked"),
                             ("Lock (open folder in new tab)", "locked"),
                             ("Lock (open folder is allowed)", "reset")):
            add_scaled_radiobutton(menu, tr(label), value, lock_mode,
                                   command=lambda mode=value: self.set_lock(child, mode))
        menu.tk_popup(event.x_root, event.y_root)
