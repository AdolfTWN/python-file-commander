"""Shared tab strip and bounded, on-demand folder navigation for one-panel mode."""
import ctypes
from collections import deque
import os
from pathlib import Path
import queue
import stat
import threading
import time
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

from .i18n import tr
from .tabs import ChamferNotebook
from .icons import folder_nav_icon_png
from .tooltip import ToolTip


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


def folder_has_children(path, stop, limit=2000, seconds=.2):
    """True/False only when verified; None means unknown, not an empty folder.

    A visible-row hint, not a directory index: stop at the first subdirectory,
    never open file contents, and avoid automatically probing drives, shares,
    symlinks or Windows cloud/reparse placeholders.
    """
    if stop.is_set() or path.parent == path or str(path).startswith(('\\\\', '//')):
        return None
    deadline = time.monotonic()+seconds
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & (0x400 | 0x1000):
            return None
        uncertain = False
        with os.scandir(path) as entries:
            for index, entry in enumerate(entries):
                if stop.is_set() or index >= limit or time.monotonic() > deadline:
                    return None
                try:
                    if entry.is_dir(follow_symlinks=False): return True
                except OSError:
                    uncertain = True
        return None if uncertain or stop.is_set() else False
    except OSError:
        return None


def branch_segments(following, expanded, indent, height):
    """Connect actual siblings; an expanded last child still ends its parent line."""
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
    EXPAND_SECONDS = 30
    EXPAND_FOLDERS = 500
    EXPAND_DEPTH = 32

    def __init__(self, master, on_navigate, on_context):
        super().__init__(master)
        # The splitter owns our size. A tall floating ancestry must not grow
        # the pane's requested height and push the app's bottom controls away.
        self.configure(width=240, height=240)
        self.pack_propagate(False)
        self.on_navigate = on_navigate
        self.on_context = on_context
        header = ttk.Frame(self); header.pack(fill='x', padx=6, pady=4)
        self.caption = ttk.Label(header, text=tr('Folders'))
        self.caption.pack(side='left')
        self.expand_all_var = tk.BooleanVar(self, value=False)
        self.expand_all_button = ttk.Checkbutton(header, text=tr('Expand All'),
            variable=self.expand_all_var, command=self.toggle_expand_all)
        self.expand_all_button.pack(side='right', padx=(8,0))
        ToolTip(self.expand_all_button, lambda: tr('Expand descendants of the current folder. Uncheck to stop.'))
        self._sticky = tk.Canvas(self, height=0, highlightthickness=0, borderwidth=0,
                                 takefocus=False, cursor='hand2')
        self._sticky_chain = ()
        self._sticky_rows = []
        self._sticky_height = 0
        self._sticky_signature = None
        self._sticky_font = tkfont.Font(self, font='TkDefaultFont')
        self._sticky_icons = {}
        self._sticky.bind('<Button-1>', self._sticky_click)
        self._sticky.bind('<Double-Button-1>', lambda _e:'break')
        for event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self._sticky.bind(event, self._line_wheel)
        self._sticky.bind('<Motion>', self._sticky_motion)
        self._sticky_tip = ''
        ToolTip(self._sticky, lambda: self._sticky_tip)
        body = self._body = ttk.Frame(self); body.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(body, show='tree', selectmode='browse', style='FolderNav.Treeview')
        self._line_rows = []
        self._line_signature = None
        self._line_indent = None
        self._line_job = None
        self._view_epoch = 0
        self._view_settle_job = None
        scroll = ttk.Scrollbar(body, command=self._scroll_view)
        scroll.pack(side='right', fill='y'); self.tree.pack(fill='both', expand=True)
        self.tree.configure(yscrollcommand=lambda *args:(scroll.set(*args), self._schedule_lines()))
        horizontal = self._horizontal = ttk.Scrollbar(self, orient='horizontal', command=self.tree.xview)
        horizontal.pack(side='bottom', fill='x')
        self.tree.configure(xscrollcommand=lambda *args:(horizontal.set(*args), self._schedule_lines()))
        self.status = ttk.Label(self, text='', wraplength=280)
        self.status.pack(side='bottom', fill='x', padx=4)
        # Reserve the bottom controls before giving the tree its remaining area.
        body.pack_forget(); body.pack(fill='both', expand=True)
        self.paths, self.nodes, self.loaded, self.pending = {}, {}, set(), {}
        self.failed, self.partial = set(), set()
        self._child_hints = {}  # absent = not checked; None = inconclusive
        self._probe_results = queue.Queue()
        self._probe_cancel = None
        self._visible_nodes = ()
        self._context_queue = deque()
        self._bulk_queue = deque(); self._bulk_seen = set(); self._bulk_pending = set(); self._bulk_checked = set()
        self._bulk_running = False; self._bulk_incomplete = False
        self._current_node = None
        self._icons = {kind: tk.PhotoImage(master=self, data=folder_nav_icon_png(kind, 16), format='png')
                       for kind in ('folder', 'drive', 'pc')}
        self._icon_size = 16
        self.results = queue.Queue(); self.slots = threading.BoundedSemaphore(2)
        self.stop = threading.Event(); self.serial = 0; self.program_selection = None
        self.pc = self.tree.insert('', 'end', text=tr('This PC'), open=True)
        for path in root_folders(): self._node(path, self.pc)
        self.tree.bind('<<TreeviewOpen>>', self._expand)
        self.tree.bind('<<TreeviewSelect>>', self._select)
        self._press_node = None
        self._press_open = False
        self.tree.bind('<Button-1>', self._remember_press)
        for event in ('<MouseWheel>', '<Button-4>', '<Button-5>', '<KeyPress>'):
            self.tree.bind(event, self._cancel_view_settle, add='+')
        self.tree.bind('<Double-Button-1>', self._double_click)
        self.tree.bind('<<TreeviewClose>>', self._manual_collapse, add='+')
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
        self.bind('<Unmap>', lambda e: self.stop_expand_all() if e.widget is self else None)

    def _schedule_lines(self, _event=None):
        if self._line_job is None:
            self._line_job = self.after_idle(self._redraw_lines)

    def _redraw_lines(self):
        self._line_job = None
        self._draw_lines()

    def _line_click(self, canvas, event):
        iid = canvas.row_id
        if not self.tree.exists(iid): return 'break'
        self._remember_press(event, iid)
        self.tree.focus_set(); self.tree.focus(iid)
        if (abs(event.x-canvas.arrow_x) <= canvas.arrow_radius
                and abs(event.y-canvas.arrow_y) <= canvas.arrow_radius
                and self._has_branch(iid) and not self.tree.item(iid, 'open')):
            self.tree.item(iid, open=True)
            self.failed.discard(iid)
            self.load(iid)
        else:
            self.tree.selection_set(iid)
        self._draw_lines()
        return 'break'

    def _remember_press(self, event, iid=None):
        self._cancel_view_settle()
        self._press_node = iid if iid is not None else self.tree.identify_row(event.y)
        self._press_open = bool(self.tree.item(self._press_node, 'open')) if self._press_node else False

    def _manual_collapse(self, _event=None):
        # Manual intent wins over an in-flight/completed Expand All action.
        if self.expand_all_var.get(): self.stop_expand_all()

    def _double_click(self, event):
        iid = self._press_node
        if not iid or not self.tree.exists(iid): return 'break'
        self._manual_collapse()
        self.tree.focus_set(); self.tree.focus(iid)
        # Single-click navigation may already have opened this node. Toggle the
        # state at the FIRST press, not that incidental intermediate state.
        opening = not self._press_open
        self.tree.item(iid, open=opening)
        if opening:
            self.failed.discard(iid)
            self.load(iid)
        self._draw_lines()
        # Suppress ttk's second toggle and focus/see handling.
        return 'break'

    def _line_wheel(self, event):
        self._cancel_view_settle()
        if getattr(event, 'num', None) in (4, 5):
            self.tree.yview_scroll(-3 if event.num == 4 else 3, 'units')
        else:
            self.tree.event_generate('<MouseWheel>', delta=event.delta, state=event.state)
        self._draw_lines()
        return 'break'

    def _cancel_view_settle(self, _event=None):
        self._view_epoch += 1
        if self._view_settle_job is not None:
            self.after_cancel(self._view_settle_job)
            self._view_settle_job = None

    def _scroll_view(self, *args):
        self._cancel_view_settle()
        self.tree.yview(*args)

    def _sticky_motion(self, event):
        row = next((iid for top, bottom, iid in self._sticky_rows if top <= event.y < bottom), '')
        if row and not self.tree.exists(row): row = ''
        self._sticky_tip = str(self.paths.get(row, self.tree.item(row, 'text'))) if row else ''

    def _reveal_ancestor(self, iid):
        if not self.tree.exists(iid): return
        self.tree.focus_set(); self.tree.focus(iid)
        self.tree.selection_set(iid)
        self.tree.see(iid)
        self._schedule_lines()

    def _sticky_click(self, event):
        for top, bottom, iid in self._sticky_rows:
            if not top <= event.y < bottom: continue
            self._reveal_ancestor(iid)
            break
        return 'break'

    def _draw_sticky(self, rows, width, height, indent, bg, fg, font):
        # Only the ancestors of the first visible row describe this viewport;
        # selection may be elsewhere. No traversal/scanning of other subtrees.
        chain = []
        if rows:
            item = self.tree.parent(rows[0][0])
            while item:
                chain.append(item); item = self.tree.parent(item)
            chain.reverse()
        self._sticky_chain = tuple(chain)
        if not chain:
            self._sticky.pack_forget()
            self._sticky_height = 0
            self._sticky_rows = []
            self._sticky_signature = None
            return
        normal_height = rows[0][3]
        # Never omit ancestors. Very deep paths use a denser context band while
        # leaving two ordinary tree rows available for navigation.
        actual_band = self._sticky.winfo_height() if self._sticky.winfo_ismapped() else 0
        available = max(1, self._body.winfo_height()+actual_band-2*normal_height-4)
        row_height = min(normal_height, max(1, int(available)//len(chain)))
        band_height = round(len(chain)*row_height)+1
        x = rows[0][1]
        following = tuple(bool(self.tree.next(item)) for item in chain)
        signature = (tuple(chain), following, width, row_height, indent, x,
                     bg, fg, tuple(sorted(font.actual().items())),
                     tuple(self.tree.item(i, 'text') for i in chain))
        if signature == self._sticky_signature: return
        self._sticky_signature = signature
        self._sticky_height = band_height
        self._sticky_font.configure(**font.actual())
        if row_height < font.metrics('linespace')+4:
            self._sticky_font.configure(size=-max(1, int(row_height-4)))
        icon_size = max(1, min(self._icon_size, int(row_height-3)))
        if self._sticky_icons.get('size') != icon_size:
            self._sticky_icons = {'size':icon_size, **{
                kind:tk.PhotoImage(master=self,data=folder_nav_icon_png(kind,icon_size),format='png')
                for kind in ('pc','drive','folder')}}
        font = self._sticky_font
        ink, paper = self.winfo_rgb(fg), self.winfo_rgb(bg)
        tint = '#'+''.join(f'{round((a*.06+b*.94)/257):02x}' for a,b in zip(ink,paper))
        muted = '#'+''.join(f'{round((a*.48+b*.52)/257):02x}' for a,b in zip(ink,paper))
        canvas = self._sticky
        canvas.configure(height=band_height, background=tint)
        canvas.pack(before=self._body, fill='x', padx=(0, max(0,self._body.winfo_width()-width)))
        canvas.delete('all'); self._sticky_rows = []
        for index, iid in enumerate(chain):
            top, mid = index*row_height, (index+.5)*row_height
            self._sticky_rows.append((top, top+row_height, iid))
            depth = index
            joint = round(x+(depth+.5)*indent)
            # Horizontal scrolling or extreme indentation can put the joint
            # outside the viewport. Keep its context readable at the edge.
            center = joint
            if joint < icon_size/2 or joint > width-icon_size/2:
                clipped_left = joint < icon_size/2
                center = round(max(icon_size/2+6,
                                   min(joint,width-max(100,indent*3))))
                canvas.create_text(3 if clipped_left else width-4,mid,
                                   text='‹' if clipped_left else '›',font=font,fill=muted,
                                   anchor='w' if clipped_left else 'e',tags='ancestor-offscreen')
            for x1, y1, x2, y2 in branch_segments(following[:index+1], True, indent, row_height):
                canvas.create_line(round(x+x1),top+y1,round(x+x2),top+y2,
                                   fill=muted,dash=(1,2),tags='ancestor-branch')
            path = self.paths.get(iid)
            kind = 'pc' if iid == self.pc else 'drive' if path and path.parent == path else 'folder'
            canvas.create_image(center,round(mid),image=self._sticky_icons[kind],tags='ancestor-icon')
            canvas.create_text(round(center+indent/2+4),mid,
                               text=self.tree.item(iid,'text'),font=font,fill=fg,anchor='w',
                               tags='ancestor-name')
        canvas.create_line(0,band_height-1,width,band_height-1,fill=muted,tags='ancestor-edge')

    def _draw_lines(self):
        """Paint only visible indentation cells, leaving native text/keys intact.

        Small row canvases draw crisp, muted dotted connectors independently
        of native theme glyphs. Rendering reads cached items only, never disk.
        """
        if not self.tree.winfo_viewable(): return
        style = ttk.Style(self)
        font = tkfont.nametofont('TkDefaultFont')
        icon_size = max(14, round(font.metrics('linespace')*.9))
        if icon_size != self._icon_size:
            self._icon_size = icon_size
            for kind, icon in self._icons.items():
                icon.configure(data=folder_nav_icon_png(kind, icon_size), format='png')
            self._line_signature = None
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
            actual_children = any(child in self.paths for child in self.tree.get_children(iid))
            children = actual_children or self._child_hints.get(iid) is True
            opened = bool(self.tree.item(iid, 'open'))
            rows.append((iid, x, top, h, flags, children, opened, actual_children, iid in selected))
            y = max(y+1, top+h)
        self._visible_nodes = tuple(row[0] for row in rows)
        self._draw_sticky(rows, width, height, indent, bg, fg, font)
        signature = (tuple(rows), width, height, indent, bg, fg, selbg, selfg)
        if signature == self._line_signature: return
        self._line_signature = signature
        for index, (iid, x, top, h, flags, children, opened, actual_children, active) in enumerate(rows):
            if index == len(self._line_rows):
                canvas = tk.Canvas(self.tree, highlightthickness=0, borderwidth=0, takefocus=False)
                canvas.bind('<Button-1>', lambda e, c=canvas:self._line_click(c, e))
                canvas.bind('<Double-Button-1>', self._double_click)
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
            background = selbg if active else bg
            ink, paper = self.winfo_rgb(color), self.winfo_rgb(background)
            muted = '#'+''.join(f'{round((a*.48+b*.52)/257):02x}' for a,b in zip(ink,paper))
            for x1,y1,x2,y2 in branch_segments(flags, opened and actual_children, indent, h):
                canvas.create_line(round(x1+offset),round(y1),round(x2+offset),round(y2),
                                   fill=muted, width=1, dash=(1,2), tags='branch')
            # Put the folder ON its tree joint, rather than placing a second
            # native icon to the right of the indentation. Descendant lines
            # emerge directly below the parent's icon; text starts just after it.
            center, mid = round((depth+.5)*indent+offset), round(h/2)
            path = self.paths.get(iid)
            kind = 'pc' if iid == self.pc else 'drive' if path and path.parent == path else 'folder'
            canvas.create_image(center,mid,image=self._icons[kind],tags='folder-icon')
            canvas.icon_x, canvas.icon_y = center, mid
            radius = max(3, min(5, round(indent*.13)))
            plus_x = center+round(self._icon_size*.28)
            plus_y = mid+round(self._icon_size*.26)
            canvas.row_id, canvas.arrow_x, canvas.arrow_y, canvas.arrow_radius = iid, plus_x, plus_y, radius
            if children and not opened:
                canvas.create_rectangle(plus_x-radius,plus_y-radius,plus_x+radius,plus_y+radius,
                                        fill=background, outline=muted, width=1, tags='indicator')
                canvas.create_line(plus_x-radius+2,plus_y,plus_x+radius-2,plus_y,fill=color, tags='indicator')
                canvas.create_line(plus_x,plus_y-radius+2,plus_x,plus_y+radius-2,fill=color, tags='indicator')
        for canvas in self._line_rows[len(rows):]: canvas.place_forget()

    def _has_branch(self, iid):
        return (self._child_hints.get(iid) is True or
                any(child in self.paths for child in self.tree.get_children(iid)))

    def _probe_visible(self):
        # Independent single worker: a slow hint must never monopolize the two
        # navigation workers. A blocked OS call cannot create more threads.
        if self._probe_cancel is not None or not self.tree.winfo_viewable(): return
        candidates = []
        for iid in self._visible_nodes:
            if (iid not in self.paths or iid in self.loaded or iid in self.pending
                    or iid in self.failed or iid in self._child_hints
                    or self.tree.item(iid, 'open') or self._has_branch(iid)):
                continue
            candidates.append((iid, self.paths[iid]))
            if len(candidates) >= 32: break
        if not candidates: return
        cancel = self._probe_cancel = threading.Event()
        def work():
            deadline = time.monotonic()+1
            try:
                for iid, path in candidates:
                    if cancel.is_set() or self.stop.is_set() or time.monotonic() > deadline: break
                    value = folder_has_children(path, cancel)
                    self._probe_results.put((cancel, iid, value))
            finally:
                self._probe_results.put((cancel, None, None))
        threading.Thread(target=work, daemon=True, name='PFC-folder-hints').start()

    def _poll_probes(self):
        while not self._probe_results.empty():
            cancel, iid, value = self._probe_results.get_nowait()
            if cancel is not self._probe_cancel: continue
            if iid is None:
                self._probe_cancel = None
                continue
            if (cancel.is_set() or iid not in self.paths or iid in self.loaded
                    or iid in self.pending or self._has_branch(iid)):
                continue
            self._child_hints[iid] = value
            if value is False:
                # Remove only the keyboard-expansion placeholder, never a real
                # child inserted by navigation while a hint was in flight.
                for child in self.tree.get_children(iid):
                    if child not in self.paths: self.tree.delete(child)

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
        if existing is not None and existing == self._current_node:
            # Autosave/refresh repeatedly sync the same path. They must not undo
            # a manual collapse, reset tree selection, or scroll back to it.
            return
        if existing and self.tree.selection() == (existing,):
            # A native tree click selects the row BEFORE navigation calls sync.
            # Still update the expansion boundary and cancel the previous run.
            if existing != self._current_node:
                self.stop_expand_all()
                self._current_node = existing
            self.program_selection = existing
            self.tree.item(existing, open=True)
            self._queue_context(existing)
            return
        chain = list(reversed(path.parents))+[path]
        parent = self.pc
        for part in chain:
            parent = self._node(part, parent)
            if part != path:
                # Seed the known path immediately, without showing dummy rows.
                # Background one-level scans will fill in its actual siblings.
                for child in self.tree.get_children(parent):
                    if child not in self.paths: self.tree.delete(child)
                self.tree.item(parent, open=True)
        self.program_selection = parent
        if parent != self._current_node:
            self.stop_expand_all()
            self._current_node = parent
        # Fill each expanded level, never recurse into unrelated descendants.
        self.tree.item(parent, open=True)
        self._queue_context(parent)
        if self.tree.selection() != (parent,): self.tree.selection_set(parent)
        self.tree.see(parent)

    def _queue_context(self, iid):
        # Active folder first, then nearest ancestors. Keep work bounded to the
        # current path and retry queued levels when the two workers are busy.
        self._context_queue.clear()
        while iid in self.paths:
            self._context_queue.append(iid)
            iid = self.tree.parent(iid)
        self._load_context()

    def _load_context(self):
        while self._context_queue:
            iid = self._context_queue[0]
            if (iid not in self.paths or iid in self.loaded or iid in self.failed
                    or iid in self.pending or not self.tree.item(iid, 'open')):
                self._context_queue.popleft()
                continue
            if len(self.nodes) >= 10000:
                self._context_queue.clear()
                self.status.configure(text=tr('Folder tree limit reached. Refresh to reload.'))
                return
            if not self.load(iid, quiet_busy=True): return
            self._context_queue.popleft()

    def _select(self, _event=None):
        selected = self.tree.selection()
        if not selected or selected[0] == self.program_selection: return
        self.program_selection = None
        path = self.paths.get(selected[0])
        if path is not None: self.on_navigate(path)

    def _expand(self, _event=None):
        self.failed.discard(self.tree.focus())
        self.load(self.tree.focus())

    def load(self, iid, bulk=False, quiet_busy=False):
        if iid not in self.paths or iid in self.pending: return
        if not bulk and (iid in self.loaded or iid in self.failed): return
        if len(self.nodes) >= 10000:
            self.status.configure(text=tr('Folder tree limit reached. Refresh to reload.')); return
        if not self.slots.acquire(blocking=False):
            if not quiet_busy:
                self.status.configure(text=tr('Folder scan busy. Try expanding again.'))
            return
        self.serial += 1
        token, path = self.serial, self.paths[iid]
        cancel = threading.Event()
        self.pending[iid] = (token, time.monotonic(), cancel)
        if bulk: self._bulk_pending.add(iid)
        else: self.status.configure(text=tr('Loading folders…'))
        self.failed.discard(iid)
        # Workers never touch Tk. Two daemon workers maximum, even if an offline
        # drive blocks a system call; stale/late results are ignored.
        def work():
            try:
                # Keep cloud/link folders visible for manual navigation, but
                # never follow them automatically during recursive expansion.
                if bulk and (path.is_symlink() or (os.name == 'nt' and
                        path.lstat().st_file_attributes & 0x400)):
                    raise OSError(tr('Linked or cloud folders are skipped during Expand All.'))
                values, partial = child_folders(path, cancel)
                result = (values, partial, '')
            except Exception as exc:
                result = ([], False, str(exc))
            finally:
                self.slots.release()
            if not self.stop.is_set(): self.results.put((iid, token, result))
        threading.Thread(target=work, daemon=True, name='PFC-folder-tree').start()
        return True

    def toggle_expand_all(self):
        if not self.expand_all_var.get():
            self.stop_expand_all()
            return
        anchor = self._current_node
        if anchor not in self.paths:
            self.expand_all_var.set(False)
            return
        self._bulk_queue = deque([(anchor, 0)]); self._bulk_seen.clear()
        self._bulk_checked.clear()
        self._bulk_deadline = time.monotonic()+self.EXPAND_SECONDS
        self._bulk_running = True; self._bulk_incomplete = False
        self.status.configure(text=tr('Expanding folders…'))

    def stop_expand_all(self, message=''):
        self._bulk_running = False
        self.expand_all_var.set(False)
        self._bulk_queue.clear()
        for iid in self._bulk_pending:
            pending = self.pending.pop(iid, None)
            if pending: pending[2].set()
        self._bulk_pending.clear()
        self.status.configure(text=tr(message) if message else '')

    def _expand_batch(self):
        if not self._bulk_running: return
        if time.monotonic() >= self._bulk_deadline or len(self.nodes) >= 10000:
            self.stop_expand_all('Expansion limited. Expand individual folders or refresh to continue.')
            return
        # Bound both filesystem concurrency and Tk work per event-loop turn.
        for _ in range(24):
            if not self._bulk_queue:
                self._bulk_running = False
                self.status.configure(text=tr('Some folders could not be expanded.') if self._bulk_incomplete else '')
                return
            iid, depth = self._bulk_queue.popleft()
            if iid in self._bulk_seen or not self.tree.exists(iid): continue
            if depth > self.EXPAND_DEPTH or len(self._bulk_seen) >= self.EXPAND_FOLDERS:
                self.stop_expand_all('Expansion limited. Expand individual folders or refresh to continue.')
                return
            if iid in self.failed:
                self._bulk_incomplete = True; self._bulk_seen.add(iid)
                continue
            if iid not in self.loaded or iid not in self._bulk_checked:
                self._bulk_queue.appendleft((iid, depth))
                if iid not in self.pending: self.load(iid, bulk=True)
                return
            self._bulk_seen.add(iid)
            self._bulk_incomplete |= iid in self.partial
            self.tree.item(iid, open=True)
            self._bulk_queue.extend((child, depth+1) for child in self.tree.get_children(iid) if child in self.paths)

    def _poll(self):
        self._poll_probes()
        for iid, (token, started, cancel) in list(self.pending.items()):
            if time.monotonic()-started > 5:
                self.pending.pop(iid, None)
                cancel.set(); self.failed.add(iid); self._bulk_pending.discard(iid)
                self.status.configure(text=tr('Folder scan timed out. Try expanding again.'))
        anchor = None
        while not self.results.empty():
            iid, token, (paths, partial, error) = self.results.get_nowait()
            if iid not in self.pending or self.pending[iid][0] != token: continue
            self.pending.pop(iid, None)
            if iid in self._bulk_pending: self._bulk_checked.add(iid)
            self._bulk_pending.discard(iid)
            if not self.tree.exists(iid): continue
            if anchor is None: anchor = self._view_anchor()
            for child in self.tree.get_children(iid):
                if child not in self.paths: self.tree.delete(child)
            for path in paths:
                if len(self.nodes) >= 10000: partial = True; break
                self._node(path, iid)
            # A saved path may already have seeded one child before this scan.
            # Merge in place, sorted, preserving IDs, open states and selection.
            children = self.tree.get_children(iid)
            ordered = sorted(children, key=lambda child: self.tree.item(child, 'text').casefold())
            if tuple(ordered) != children: self.tree.set_children(iid, *ordered)
            if not error: self.loaded.add(iid)
            else: self.failed.add(iid)
            self._child_hints[iid] = (True if self.tree.get_children(iid) else
                                      None if error or partial else False)
            if partial: self.partial.add(iid)
            self.status.configure(text=error or (tr('Folder list limited. Use the file list or Refresh.') if partial else ''))
            if error and not self.tree.get_children(iid): self.tree.insert(iid, 'end', text='…')
        if anchor is not None: self._restore_view_anchor(anchor)
        self._load_context()
        self._expand_batch()
        self._draw_lines()
        self._probe_visible()
        if anchor is not None and self.tree.selection() == (anchor[0],):
            self._cancel_view_settle()
            self._view_settle_job = self.after_idle(self._settle_scan_selection, anchor[0], self._view_epoch, 32)
        self._poll_job = self.after(80, self._poll)

    def _settle_scan_selection(self, iid, epoch, remaining):
        # A new floating ancestry changes the viewport AFTER Tk lays it out.
        # Keep the previously visible row whole, but never fight user scrolling,
        # keyboard navigation, a changed selection or a collapsed branch.
        self._view_settle_job = None
        if (not remaining or epoch != self._view_epoch or not self.tree.winfo_viewable()
                or not self.tree.exists(iid) or self.tree.selection() != (iid,)):
            return
        box = self.tree.bbox(iid)
        if box and box[1] >= 1 and box[1]+box[3] < self.tree.winfo_height(): return
        parent = self.tree.parent(iid)
        while parent:
            if not self.tree.item(parent, 'open'): return
            parent = self.tree.parent(parent)
        self.tree.see(iid)
        self._draw_lines()
        self._view_settle_job = self.after_idle(self._settle_scan_selection, iid, epoch, remaining-1)

    def _view_anchor(self):
        # Keep a visible selection at its screen row while ancestors gain
        # siblings. If the user scrolled away, preserve their top row instead.
        for iid in (*self.tree.selection(), self.tree.identify_row(1)):
            if not iid: continue
            box = self.tree.bbox(iid)
            if box and 0 <= box[1] < self.tree.winfo_height():
                return iid, max(0, (box[1]-1)//box[3])

    def _restore_view_anchor(self, anchor):
        iid, offset = anchor
        if not self.tree.exists(iid): return
        # Cached Tk nodes only, and only after a scan changes the tree. Never
        # enumerate the filesystem or rescan every node on ordinary redraws.
        stack = list(reversed(self.tree.get_children('')))
        position = 0
        while stack:
            item = stack.pop()
            if item == iid:
                self.tree.yview(max(0, position-offset))
                return
            position += 1
            if self.tree.item(item, 'open'):
                stack.extend(reversed(self.tree.get_children(item)))

    def refresh(self):
        # Explicit refresh bounds cache lifetime and picks up drive/folder changes.
        selected = self.tree.selection()
        path = self.paths.get(selected[0]) if selected else None
        self.stop_expand_all()
        if self._probe_cancel is not None: self._probe_cancel.set()
        self._child_hints.clear(); self._visible_nodes = ()
        for _, _, cancel in self.pending.values(): cancel.set()
        self.pending.clear(); self.loaded.clear(); self.paths.clear(); self.nodes.clear()
        self._context_queue.clear()
        self.failed.clear(); self.partial.clear(); self._current_node = None
        self.tree.delete(*self.tree.get_children(self.pc))
        for drive in root_folders(): self._node(drive, self.pc)
        if path is not None:
            self.sync(path)
            self.load(self.nodes[os.path.normcase(str(path))])

    def destroy(self):
        self._cancel_view_settle()
        self.stop_expand_all()
        if self._probe_cancel is not None: self._probe_cancel.set()
        for _, _, cancel in self.pending.values(): cancel.set()
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
