"""Measured, task-grouped toolbars without shrinking fonts or equal-width waste."""
from tkinter import ttk


def toolbar_rows(width, sizes, gap=6):
    """Greedily retain adjacent semantic groups; exact fits stay on one row."""
    rows, row, used = [], [], 0
    for index, size in enumerate(sizes):
        size = max(1, int(size))
        if row and used + gap + size > max(1, width):
            rows.append(row); row, used = [], 0
        used += (gap if row else 0) + size
        row.append(index)
    if row: rows.append(row)
    return rows


class FlowToolbar(ttk.Frame):
    """Place whole groups by measured minimum widths; expand only useful inputs.

    Children keep their pack/grid layout internally. Requested geometry is never
    derived from the width just assigned by us (avoids resize feedback loops).
    No polling, file I/O, font reduction, or widget recreation during reflow.
    """
    def __init__(self, master, *, gap=6, row_gap=3, **kwargs):
        super().__init__(master, **kwargs)
        self.gap, self.row_gap = gap, row_gap
        self.groups = []
        self.rows = []
        self._flow_job = None
        self._flow_signature = None
        self.bind('<Configure>', self.schedule, add='+')
        self.bind('<Map>', self.schedule, add='+')
        self.bind('<<ThemeChanged>>', self.schedule, add='+')
        self.bind('<Destroy>', self._flow_destroy, add='+')

    def add(self, widget, *, expand=False, minimum=None):
        self.groups.append((widget, expand, minimum))
        widget.bind('<Configure>', self.schedule, add='+')
        self.schedule()

    def schedule(self, _event=None):
        if self._flow_job is None:
            self._flow_job = self.after_idle(self.layout)

    def _flow_destroy(self, event):
        if event.widget is self and self._flow_job is not None:
            self.after_cancel(self._flow_job)
            self._flow_job = None

    def layout(self):
        self._flow_job = None
        width = max(1, self.winfo_width())
        sizes = [max(1, int(minimum() if callable(minimum) else minimum or w.winfo_reqwidth()))
                 for w, _, minimum in self.groups]
        heights = [w.winfo_reqheight() for w, _, _ in self.groups]
        signature = (width, tuple(sizes), tuple(heights))
        if signature == self._flow_signature: return
        self._flow_signature = signature
        self.rows = toolbar_rows(width, sizes, self.gap)
        y = 0
        for row in self.rows:
            height = max(heights[i] for i in row)
            spare = max(0, width-sum(sizes[i] for i in row)-self.gap*(len(row)-1))
            growing = [i for i in row if self.groups[i][1]]
            x = 0
            for i in row:
                extra = (spare//len(growing)+(i == growing[-1])*(spare % len(growing))) if i in growing else 0
                allocated = min(width, sizes[i]+extra)
                self.groups[i][0].place(x=x, y=y, width=allocated, height=height)
                x += allocated+self.gap
            y += height+self.row_gap
        self.configure(height=max(1, y-self.row_gap))
