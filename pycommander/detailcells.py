"""Font-scaled rich size units over native Treeview cells; no polling or I/O."""
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from .marquee import forward_tree_event
from .columnsettings import font_snapshot


class SizeUnitCells:
    def __init__(self, pane):
        self.pane, self.tree = pane, pane.tree
        self.pending = None
        self.closed = False
        self.cells = []
        self.font = tkfont.nametofont("TkDefaultFont")
        self.bold = tkfont.Font(self.tree, **font_snapshot(self.font))
        self.bold.configure(weight="bold")
        for event in ("<<TreeviewSelect>>", "<FocusIn>", "<FocusOut>",
                      "<Configure>", "<Map>", "<ButtonRelease-1>",
                      "<<TreeviewOpen>>", "<<TreeviewClose>>"):
            self.tree.bind(event, self.request, add="+")
        self.tree.bind("<Unmap>", self.hide, add="+")
        self.tree.bind("<Destroy>", self.destroy, add="+")

    def hide(self, _event=None):
        if self.pending is not None:
            self.tree.after_cancel(self.pending)
            self.pending = None
        for cell in self.cells:
            try:
                cell.place_forget()
            except tk.TclError:
                pass  # Child canvases may already be destroyed with their tree.

    def request(self, _event=None):
        if self.closed or self.pending is not None:
            return
        self.pending = self.tree.after_idle(self.draw)

    def sync_font(self):
        self.bold.configure(**font_snapshot(self.font))
        self.bold.configure(weight="bold")

    def measure(self, text):
        number, _, unit = str(text).rpartition(" ")
        if unit in ("GB", "TB"):
            return self.font.measure(number + " ") + self.bold.measure(unit)
        return self.font.measure(str(text))

    def _cell(self, index):
        if index == len(self.cells):
            cell = tk.Canvas(self.tree, highlightthickness=0, borderwidth=0,
                             takefocus=0, cursor="arrow")
            cell.create_text(0, 0, anchor="e", tags="unit")
            cell.create_text(0, 0, anchor="e", tags="number")
            for sequence in ("<ButtonPress-1>", "<ButtonRelease-1>",
                             "<ButtonPress-2>", "<ButtonRelease-2>",
                             "<ButtonPress-3>", "<ButtonRelease-3>",
                             "<Motion>", "<MouseWheel>", "<ButtonPress-4>",
                             "<ButtonPress-5>"):
                cell.bind(sequence, lambda e, s=sequence: forward_tree_event(self.tree, e, s))
            self.cells.append(cell)
        return self.cells[index]

    def draw(self):
        self.pending = None
        if self.closed:
            return
        if (not self.tree.winfo_ismapped() or 'size' not in self.tree.cget('displaycolumns')
                or not self.pane.winfo_toplevel().size_emphasis_var.get()):
            self.hide()
            return
        font = self.font
        self.sync_font()
        style = ttk.Style(self.tree)
        name = self.tree.cget("style") or "Treeview"
        selected = set(self.tree.selection())
        focused = self.tree.focus_get() is self.tree
        height, width = self.tree.winfo_height(), self.tree.winfo_width()
        # Walk screen rows, not all directory entries (including expanded trees).
        y, used, seen = 1, 0, set()
        while y < height:
            iid = self.tree.identify_row(y)
            if not iid or iid in seen:
                y += 1
                continue
            seen.add(iid)
            box = self.tree.bbox(iid, "size")
            if not box:
                y += 1
                continue
            x, top, cell_width, row_height = box
            y = top + row_height
            text = self.tree.set(iid, "size")
            number, _, unit = text.rpartition(" ")
            if unit not in ("GB", "TB") or x < 0 or x+cell_width > width or top < 0:
                continue
            states = (("selected",) if iid in selected else ()) + (("focus",) if focused else ())
            bg = style.lookup(name, "background", states) or "white"
            fg = style.lookup(name, "foreground", states) or "black"
            # A lighter red remains distinct against both dark and selection backgrounds.
            rgb = self.tree.winfo_rgb(bg)
            luminance = sum(c*w for c, w in zip(rgb, (.2126, .7152, .0722))) / 65535
            red = "#ff8585" if luminance < .5 else "#b00020"
            cell = self._cell(used); used += 1
            cell.configure(background=bg)
            right = cell_width-4
            cell.coords('unit', right, (row_height-2)/2)
            cell.itemconfigure('unit', text=unit, font=self.bold, fill=red if unit == "TB" else fg)
            cell.coords('number', right-self.bold.measure(unit), (row_height-2)/2)
            cell.itemconfigure('number', text=number+" ", font=font, fill=fg)
            cell.place(x=x+1, y=top+1, width=max(1, cell_width-2), height=max(1, row_height-2))
            cell.tk.call("raise", cell._w)
        for cell in self.cells[used:]:
            cell.place_forget()

    def destroy(self, event):
        if event.widget is self.tree:
            self.closed = True
            self.hide()
