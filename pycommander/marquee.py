"""A single clipped, font-sized moving name; file identities never change."""
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk


def forward_tree_event(tree, event, sequence):
    """Keep text overlays transparent to native selection, drag and wheel input."""
    options = dict(x=event.x_root-tree.winfo_rootx(),
                   y=event.y_root-tree.winfo_rooty(),
                   rootx=event.x_root, rooty=event.y_root,
                   state=event.state, time=event.time, when="now")
    if sequence == "<MouseWheel>":
        options["delta"] = event.delta
    tree.event_generate(sequence, **options)
    return "break"


def marquee_offset(elapsed, overflow, speed):
    """One second at the start, forward reading, 1.5 seconds at the end."""
    if overflow <= 0 or speed <= 0:
        return 0.0
    travel = overflow / speed
    phase = max(0, elapsed) % (1.0 + travel + 1.5)
    return min(overflow, max(0, phase - 1.0) * speed)


class NameMarquee:
    def __init__(self, pane):
        self.pane, self.tree = pane, pane.tree
        self.owner = pane.winfo_toplevel()
        self.job = self.pending = None
        self.item = ""
        self.suspended = False
        self.closed = False
        self.canvas = tk.Canvas(self.tree, highlightthickness=0, borderwidth=0,
                                takefocus=0, cursor="arrow")
        self.text_id = self.canvas.create_text(0, 0, anchor="w")
        for sequence in ("<<TreeviewSelect>>", "<FocusIn>", "<KeyRelease>",
                         "<ButtonRelease-1>", "<Configure>", "<Map>",
                         "<<TreeviewOpen>>", "<<TreeviewClose>>"):
            self.tree.bind(sequence, self.request, add="+")
        for sequence in ("<FocusOut>", "<Unmap>"):
            self.tree.bind(sequence, lambda _e: self.stop(), add="+")
        self.tree.bind("<Destroy>", self._destroy, add="+")
        # Forward raw events with their original time/state. Tk itself recognizes
        # double clicks; generating synthetic Double events is not supported.
        for sequence in ("<ButtonPress-1>", "<ButtonRelease-1>",
                         "<ButtonPress-2>", "<ButtonRelease-2>",
                         "<ButtonPress-3>", "<ButtonRelease-3>",
                         "<Motion>", "<MouseWheel>", "<ButtonPress-4>",
                         "<ButtonPress-5>"):
            self.canvas.bind(sequence, lambda e, s=sequence: self._forward(e, s))

    def _forward(self, event, sequence):
        return forward_tree_event(self.tree, event, sequence)

    def request(self, _event=None):
        if self.closed:
            return
        self.stop()
        self.pending = self.tree.after_idle(self.start)

    def stop(self):
        for key in ("job", "pending"):
            job = getattr(self, key)
            if job is not None:
                try: self.tree.after_cancel(job)
                except tk.TclError: pass
                setattr(self, key, None)
        self.item = ""
        try: self.canvas.place_forget()
        except tk.TclError: pass

    def _eligible(self):
        setting = getattr(self.owner, "long_name_scrolling_var", None)
        context = getattr(self.owner, "file_context_menu", None)
        return (not self.closed and not self.suspended and setting is not None and setting.get()
                and getattr(self.owner, "active", None) is self.pane
                and self.owner.state() != "iconic"
                and not (context is not None and context.winfo_exists() and context.winfo_ismapped())
                and self.tree.winfo_ismapped() and self.tree.focus_get() is self.tree
                and not self.tree.grab_current()
                and not self.pane._drag_press_item and not self.pane._dragging
                and self.pane._inline_editor is None)

    def text_bounds(self, iid):
        """Locate native text after indentation, expander and icon (any theme)."""
        box = self.tree.bbox(iid, "#0")
        if not box:
            return None
        x, y, width, height = box
        right = min(x+width-2, self.tree.winfo_width()-2)
        center = y+height//2
        if y < 0 or y+height > self.tree.winfo_height():
            return None
        for left in range(max(2, x), right):
            if self.tree.identify_element(left, center) == "text":
                return left, y+1, right-left, height-2
        return None

    def clipped(self, iid):
        bounds = self.text_bounds(iid)
        return bool(bounds and tkfont.nametofont("TkDefaultFont").measure(
            str(self.tree.item(iid, "text"))) > bounds[2])

    def start(self):
        self.pending = None
        if not self._eligible():
            return
        iid = self.tree.focus()
        if not iid or iid not in self.tree.selection():
            return
        bounds = self.text_bounds(iid)
        if not bounds or bounds[2] <= 0:
            return
        text = str(self.tree.item(iid, "text"))
        font = tkfont.nametofont("TkDefaultFont")
        self.overflow = font.measure(text)-bounds[2]+2
        if self.overflow <= 2:
            return
        self.item = iid
        self.pane._name_tooltip.hide()
        style = ttk.Style(self.tree)
        name = self.tree.cget("style") or "Treeview"
        states = ("selected", "focus")
        palette = getattr(self.owner, "palette", {})
        background = style.lookup(name, "background", states) or palette.get("selection", "#0078d4")
        foreground = style.lookup(name, "foreground", states) or "#ffffff"
        self.canvas.configure(background=background)
        self.canvas.itemconfigure(self.text_id, text=text, font=font, fill=foreground)
        self.canvas.coords(self.text_id, 0, bounds[3]/2)
        self.canvas.place(x=bounds[0], y=bounds[1], width=bounds[2], height=bounds[3])
        self.canvas.tk.call("raise", self.canvas._w)
        self.height = bounds[3]
        self.started = time.monotonic()
        self.speed = 36 * self.owner._font_scales.get(self.owner.font_size_var.get(), 1.0)
        self.job = self.tree.after(33, self.tick)

    def tick(self):
        if self.job is not None:
            self.tree.after_cancel(self.job)
        self.job = None
        if (not self._eligible() or self.tree.focus() != self.item
                or self.item not in self.tree.selection()):
            self.stop()
            return
        offset = marquee_offset(time.monotonic()-self.started, self.overflow, self.speed)
        self.canvas.coords(self.text_id, -offset, self.height/2)
        self.job = self.tree.after(33, self.tick)

    def _destroy(self, event):
        if event.widget is self.tree:
            self.stop()
            self.closed = True
