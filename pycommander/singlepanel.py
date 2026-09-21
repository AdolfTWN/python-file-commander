"""Shared tab strip and bounded, on-demand folder navigation for one-panel mode."""
import ctypes
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

from .i18n import tr
from .tabs import ChamferNotebook


def root_folders():
    # Enumerate drive letters, never probe every drive/share for availability.
    if os.name == 'nt':
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        return [Path(f'{chr(65+i)}:/') for i in range(26) if mask & (1 << i)]
    return [Path('/')]


def child_folders(path, stop, limit=2000, seconds=3):
    """One directory only, no recursive walk and no file-content reads."""
    found, seen, partial = [], 0, False
    deadline = time.monotonic()+seconds
    with os.scandir(path) as entries:
        for entry in entries:
            if stop.is_set() or seen >= limit or time.monotonic() > deadline:
                partial = True
                break
            seen += 1
            try:
                if entry.is_dir(follow_symlinks=False):
                    found.append(Path(entry.path))
            except OSError:
                continue
    return sorted(found, key=lambda p:p.name.casefold()), partial


def branch_segments(following, expanded, indent, height):
    """Solid connector geometry; flags run from the root through this row."""
    depth, mid = len(following)-1, height/2
    lines = []
    for level in range(1, depth):
        if following[level]:
            x = (level-.5)*indent
            lines.append((x, 0, x, height))
    if depth:
        x = (depth-.5)*indent
        lines.extend(((x, 0, x, height if following[-1] else mid),
                      (x, mid, (depth+.5)*indent, mid)))
    if expanded:
        x = (depth+.5)*indent
        lines.append((x, mid, x, height))
    return lines


class RootFolderTree(ttk.Frame):
    def __init__(self, master, on_navigate, on_context):
        super().__init__(master)
        self.on_navigate = on_navigate
        self.on_context = on_context
        self.caption = ttk.Label(self, text=tr('Folders'))
        self.caption.pack(anchor='w', padx=6, pady=4)
        body = ttk.Frame(self); body.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(body, show='tree', selectmode='browse', style='FolderNav.Treeview')
        self._line_rows = []
        self._line_signature = None
        self._line_indent = None
        self._line_job = None
        scroll = ttk.Scrollbar(body, command=self.tree.yview)
        scroll.pack(side='right', fill='y'); self.tree.pack(fill='both', expand=True)
        self.tree.configure(yscrollcommand=lambda *args:(scroll.set(*args), self._schedule_lines()))
        horizontal = ttk.Scrollbar(self, orient='horizontal', command=self.tree.xview)
        horizontal.pack(fill='x')
        self.tree.configure(xscrollcommand=lambda *args:(horizontal.set(*args), self._schedule_lines()))
        self.status = ttk.Label(self, text='', wraplength=280)
        self.status.pack(fill='x', padx=4)
        self.paths, self.nodes, self.loaded, self.pending = {}, {}, set(), {}
        self.results = queue.Queue(); self.slots = threading.BoundedSemaphore(2)
        self.stop = threading.Event(); self.serial = 0; self.program_selection = None
        self.pc = self.tree.insert('', 'end', text=tr('This PC'), open=True)
        for path in root_folders(): self._node(path, self.pc)
        self.tree.bind('<<TreeviewOpen>>', self._expand)
        self.tree.bind('<<TreeviewSelect>>', self._select)
        self.tree.bind('<Button-3>', on_context)
        self.tree.bind('<Shift-F10>', on_context)
        self.tree.bind('<KeyPress-Menu>', on_context)
        for event in ('<Configure>', '<Expose>', '<<TreeviewOpen>>', '<<TreeviewClose>>', '<<TreeviewSelect>>'):
            self.tree.bind(event, self._schedule_lines, add='+')
        # These belong to the file list, never silently operate on its old row
        # while the navigation tree has focus. Arrow keys keep native tree use.
        for key in ('<Delete>', '<Shift-Delete>', '<F2>', '<Control-c>', '<Control-x>'):
            self.tree.bind(key, lambda _e:'break')
        self._poll_job = self.after(80, self._poll)

    def _schedule_lines(self, _event=None):
        if self._line_job is None:
            self._line_job = self.after_idle(self._redraw_lines)

    def _redraw_lines(self):
        self._line_job = None
        self._draw_lines()

    def _line_click(self, canvas, event):
        iid = canvas.row_id
        if not self.tree.exists(iid): return 'break'
        self.tree.focus_set(); self.tree.focus(iid)
        if (abs(event.x-canvas.arrow_x) <= canvas.arrow_radius+3
                and self.tree.get_children(iid) and not self.tree.item(iid, 'open')):
            self.tree.item(iid, open=True)
            self.load(iid)
        else:
            self.tree.selection_set(iid)
        self._draw_lines()
        return 'break'

    def _line_wheel(self, event):
        if getattr(event, 'num', None) in (4, 5):
            self.tree.yview_scroll(-3 if event.num == 4 else 3, 'units')
        else:
            self.tree.event_generate('<MouseWheel>', delta=event.delta, state=event.state)
        self._draw_lines()
        return 'break'

    def _draw_lines(self):
        """Paint only visible indentation cells, leaving native text/keys intact.

        Tk Treeview has no portable solid-connector option. Small row canvases
        provide actual solid strokes, not Unicode line characters or dotted
        theme glyphs. Rendering reads only cached tree items, never the disk.
        """
        if not self.tree.winfo_viewable(): return
        style = ttk.Style(self)
        font = tkfont.nametofont('TkDefaultFont')
        indent = max(20, round(font.metrics('linespace')*1.1))
        if indent != self._line_indent:
            self._line_indent = indent
            style.configure('FolderNav.Treeview', indent=indent)
            style.configure('FolderNav.Treeview.Item', indicatorsize=indent, indicatormargins=0)
            self._line_signature = None
        height, width = self.tree.winfo_height(), self.tree.winfo_width()
        selected = self.tree.selection()
        bg = style.lookup('FolderNav.Treeview', 'background') or '#ffffff'
        fg = style.lookup('FolderNav.Treeview', 'foreground') or '#303030'
        selbg = style.lookup('FolderNav.Treeview', 'background', ('selected',)) or '#3478bb'
        selfg = style.lookup('FolderNav.Treeview', 'foreground', ('selected',)) or '#ffffff'
        rows, seen = [], set()
        # Probe screen rows, not every expanded node in the cached directory tree.
        y = 1
        while y < height:
            iid = self.tree.identify_row(y)
            if not iid or iid in seen:
                y += 1; continue
            seen.add(iid)
            bbox = self.tree.bbox(iid)
            if not bbox: y += 1; continue
            x, top, _w, h = bbox
            chain, item = [], iid
            while item:
                chain.append(item); item = self.tree.parent(item)
            chain.reverse()
            flags = tuple(bool(self.tree.next(item)) for item in chain)
            children = bool(self.tree.get_children(iid))
            opened = bool(self.tree.item(iid, 'open')) and children
            rows.append((iid, x, top, h, flags, children, opened, iid in selected))
            y = max(y+1, top+h)
        signature = (tuple(rows), width, height, indent, bg, fg, selbg, selfg)
        if signature == self._line_signature: return
        self._line_signature = signature
        for index, (iid, x, top, h, flags, children, opened, active) in enumerate(rows):
            if index == len(self._line_rows):
                canvas = tk.Canvas(self.tree, highlightthickness=0, borderwidth=0, takefocus=False)
                canvas.bind('<Button-1>', lambda e, c=canvas:self._line_click(c, e))
                canvas.bind('<Button-3>', self.on_context)
                for event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                    canvas.bind(event, self._line_wheel)
                self._line_rows.append(canvas)
            canvas = self._line_rows[index]
            depth = len(flags)-1
            # Keep native text fully visible; reserve exactly its indentation.
            prefix = (depth+1)*indent
            left, right = max(1, x), min(width-1, x+prefix)
            if right <= left:
                canvas.place_forget(); continue
            offset = x-left
            canvas.configure(background=selbg if active else bg)
            canvas.place(x=left, y=top, width=right-left, height=h)
            canvas.delete('all')
            color = selfg if active else fg
            stroke = max(1, round(font.metrics('linespace')/18))
            for x1,y1,x2,y2 in branch_segments(flags, opened, indent, h):
                canvas.create_line(x1+offset,y1,x2+offset,y2, fill=color, width=stroke, tags='branch')
            center, radius = (depth+.5)*indent+offset, max(3, round(indent*.16))
            canvas.row_id, canvas.arrow_x, canvas.arrow_radius = iid, center, radius
            if children and not opened:
                canvas.create_rectangle(center-radius-2,h/2-radius-2,center+radius+2,h/2+radius+2,
                                        fill=selbg if active else bg, outline='')
                points = (center-radius/2,h/2-radius, center-radius/2,h/2+radius, center+radius,h/2)
                canvas.create_polygon(*points, fill=color, tags='indicator')
        for canvas in self._line_rows[len(rows):]: canvas.place_forget()

    def _node(self, path, parent):
        key = os.path.normcase(str(path))
        if key in self.nodes: return self.nodes[key]
        iid = self.tree.insert(parent, 'end', text=path.name or str(path))
        self.paths[iid] = path; self.nodes[key] = iid
        self.tree.insert(iid, 'end', text='…')
        return iid

    def sync(self, path):
        path = Path(path)
        if not path.is_absolute(): return
        existing = self.nodes.get(os.path.normcase(str(path)))
        if existing and self.tree.selection() == (existing,):
            self.tree.item(existing, open=True)
            self.load(existing)
            return
        chain = list(reversed(path.parents))+[path]
        parent = self.pc
        for part in chain:
            parent = self._node(part, parent)
            if part != path:
                # Ancestors shown for a known path do not need visible dummy
                # rows. They remain unscanned and can load on manual expansion.
                for child in self.tree.get_children(parent):
                    if child not in self.paths: self.tree.delete(child)
                self.tree.item(parent, open=True)
        self.program_selection = parent
        # Expand the active folder immediately, but enumerate only this level.
        # Ancestors are already open; unrelated descendants stay lazy-loaded.
        self.tree.item(parent, open=True)
        self.load(parent)
        if self.tree.selection() != (parent,): self.tree.selection_set(parent)
        self.tree.see(parent)

    def _select(self, _event=None):
        selected = self.tree.selection()
        if not selected or selected[0] == self.program_selection: return
        self.program_selection = None
        path = self.paths.get(selected[0])
        if path is not None: self.on_navigate(path)

    def _expand(self, _event=None):
        self.load(self.tree.focus())

    def load(self, iid):
        if iid not in self.paths or iid in self.loaded or iid in self.pending: return
        if len(self.nodes) >= 10000:
            self.status.configure(text=tr('Folder tree limit reached. Refresh to reload.')); return
        if not self.slots.acquire(blocking=False):
            self.status.configure(text=tr('Folder scan busy. Try expanding again.')); return
        self.serial += 1
        token, path = self.serial, self.paths[iid]
        self.pending[iid] = (token, time.monotonic())
        self.status.configure(text=tr('Loading folders…'))
        # Workers never touch Tk. Two daemon workers maximum, even if an offline
        # drive blocks a system call; stale/late results are ignored.
        def work():
            try:
                values, partial = child_folders(path, self.stop)
                result = (values, partial, '')
            except Exception as exc:
                result = ([], False, str(exc))
            finally:
                self.slots.release()
            if not self.stop.is_set(): self.results.put((iid, token, result))
        threading.Thread(target=work, daemon=True, name='PFC-folder-tree').start()

    def _poll(self):
        for iid, (token, started) in list(self.pending.items()):
            if time.monotonic()-started > 5:
                self.pending.pop(iid, None)
                self.status.configure(text=tr('Folder scan timed out. Try expanding again.'))
        while not self.results.empty():
            iid, token, (paths, partial, error) = self.results.get_nowait()
            if iid not in self.pending or self.pending[iid][0] != token: continue
            self.pending.pop(iid, None)
            if not self.tree.exists(iid): continue
            for child in self.tree.get_children(iid):
                if child not in self.paths: self.tree.delete(child)
            for path in paths:
                if len(self.nodes) >= 10000: partial = True; break
                self._node(path, iid)
            if not error: self.loaded.add(iid)
            self.status.configure(text=error or (tr('Folder list limited. Use the file list or Refresh.') if partial else ''))
            if error and not self.tree.get_children(iid): self.tree.insert(iid, 'end', text='…')
        self._draw_lines()
        self._poll_job = self.after(80, self._poll)

    def refresh(self):
        # Explicit refresh bounds cache lifetime and picks up drive/folder changes.
        selected = self.tree.selection()
        path = self.paths.get(selected[0]) if selected else None
        self.pending.clear(); self.loaded.clear(); self.paths.clear(); self.nodes.clear()
        self.tree.delete(*self.tree.get_children(self.pc))
        for drive in root_folders(): self._node(drive, self.pc)
        if path is not None:
            self.sync(path)
            self.load(self.nodes[os.path.normcase(str(path))])

    def destroy(self):
        self.stop.set()
        self.after_cancel(self._poll_job)
        if self._line_job is not None: self.after_cancel(self._line_job)
        super().destroy()


class SharedTabBar(ChamferNotebook):
    """Present existing FilePanes without reparenting, copying or closing them."""
    def __init__(self, master, owner):
        self.owner = owner
        super().__init__(master, tab_style=owner.tab_style_var.get(),
                         on_color_changed=self._color_changed,
                         on_lock_changed=self._lock_changed,
                         on_tabs_reordered=owner.save_config)

    def sync(self, panes, active):
        self._tabs = [p for p in self._tabs if p in panes]
        self._tabs.extend(p for p in panes if p not in self._tabs)
        self._texts = {p:self.owner._tabs_for(p)._texts.get(p, '') for p in self._tabs}
        self._colors = {p:self.owner._tabs_for(p)._colors.get(p, 'default') for p in self._tabs}
        self._locks = {p:p.lock_mode for p in self._tabs}
        self._selected = active if active in self._tabs else (self._tabs[0] if self._tabs else None)
        self._draw()

    def select(self, tab=None):
        if tab is None: return str(self._selected) if self._selected is not None else ''
        pane = self._resolve(tab)
        self.owner._select_single_tab(pane)
        return str(pane)

    def current(self): return self._selected

    def _color_changed(self, pane, value):
        self.owner._tabs_for(pane).set_color(pane, value)

    def _lock_changed(self, pane, value):
        self.owner._tabs_for(pane).set_lock(pane, value)
