from __future__ import annotations

import fnmatch
import os
import queue
import threading
import time
import zipfile
import zlib
import math
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, simpledialog, ttk

from .tooltip import install_button_tooltips, ToolTip
from .i18n import retranslate_widgets, tr
from .tabs import color_scheme
from .settings import readable_check_style
from .multirename import execute_rename_pairs


OFFICE_XML = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}
CONTENT_LIMIT = 32 * 1024 * 1024
RESULT_LIMIT = 10000


def search_attributes(path: Path, metadata) -> str:
    """Use the search worker's stat snapshot; no additional per-row disk I/O."""
    flags = getattr(metadata, 'st_file_attributes', 0)
    labels = []
    if path.name.startswith('.') or flags & 2: labels.append(tr('Hidden'))
    if flags & 4: labels.append(tr('System'))
    return ' · '.join(labels)


def search_row_height(linespace: int, scale: float) -> int:
    """Leave enough vertical padding for scaled Search result text."""
    return max(24, int(linespace) + max(8, round(6 * float(scale))))


def search_column_widths(available: int, desired: dict[str, int]) -> dict[str, int]:
    """Fit result columns while reserving useful space for both name and folder."""
    available = max(520, int(available))
    fixed = {
        "attributes": min(max(desired.get("attributes", 90), 72), 400),
        "size": min(max(desired.get("size", 80), 72), 180),
        "modified": min(max(desired.get("modified", 150), 148), 400),
        "ext": min(max(desired.get("ext", 54), 48), 150),
    }
    flexible = max(280, available - sum(fixed.values()) - 8)
    wanted_name = min(max(desired.get("name", 160), 130), int(available * .48))
    # A long containing path must not crowd short, otherwise-readable names.
    name = wanted_name
    folder = max(150, flexible - name)
    return {"name": name, "folder": folder, **fixed}


def name_matches(name: str, masks: str, case_sensitive: bool) -> bool:
    patterns = [part.strip() for part in masks.split(";") if part.strip()] or ["*"]
    patterns = [pattern if any(char in pattern for char in "*?[]") else f"*{pattern}*" for pattern in patterns]
    if not case_sensitive:
        name, patterns = name.casefold(), [pattern.casefold() for pattern in patterns]
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def content_matches(path: Path, needle: str, case_sensitive: bool, *, on_error=None) -> bool:
    if not needle: return True
    target = needle if case_sensitive else needle.casefold()
    try:
        if path.suffix.casefold() in OFFICE_XML and zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                chunks, remaining = [], CONTENT_LIMIT
                for info in archive.infolist():
                    if remaining <= 0:
                        break
                    if info.filename.endswith(".xml"):
                        if chunks:
                            remaining -= 1
                        if remaining <= 0:
                            break
                        with archive.open(info) as stream:
                            chunk = stream.read(remaining)
                        chunks.append(chunk)
                        remaining -= len(chunk)
                data = b" ".join(chunks)
        else:
            with path.open("rb") as stream: data = stream.read(CONTENT_LIMIT)
        utf32 = data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff"))
        utf16 = data.startswith((b"\xff\xfe", b"\xfe\xff"))
        if b"\x00" in data[:4096] and not (utf32 or utf16): return False
        if utf32: text = data.decode("utf-32", errors="replace")
        elif utf16: text = data.decode("utf-16", errors="replace")
        else:
            try: text = data.decode("utf-8-sig")
            except UnicodeDecodeError: text = data.decode("cp1252", errors="replace")
        return target in (text if case_sensitive else text.casefold())
    except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, zlib.error):
        if on_error:on_error()
        return False


class SearchWindow(tk.Toplevel):
    def __init__(self, master, config, save_config, start_path, on_go, on_preview,
                 on_compare=None, on_send_listing=None):
        super().__init__(master)
        self.config_data, self.save_config = config, save_config
        self.on_go, self.on_preview = on_go, on_preview
        self.on_compare, self.on_send_listing = on_compare, on_send_listing
        self.results, self.worker = [], None
        self.item_data = {}
        self.sort_column, self.sort_reverse = "name", False
        self.cancel_event = threading.Event(); self.messages = queue.Queue(); self.poll_job = None
        self._column_resize_job = None
        self._column_desired = {}
        self._progress_started = 0.0
        self._elapsed_finished = None
        self.search_state = 'ready'
        self._scanned_folders = self._skipped = 0
        self._query_states = []
        self.path_var = tk.StringVar(value=str(start_path))
        self.mask_var = tk.StringVar(value="")
        self.content_var = tk.StringVar(value="")
        self.case_var = tk.BooleanVar(value=config.getboolean("search", "case_sensitive", fallback=False))
        saved_depth = config.get("search", "depth", fallback="All")
        self.depth_values = {tr("Current"): "Current", "1": "1", "2": "2", "3": "3", "5": "5", tr("All"): "All"}
        self.depth_var = tk.StringVar(value=next((label for label, value in self.depth_values.items()
                                                  if value == saved_depth), tr("All")))
        self.files_var = tk.BooleanVar(value=config.getboolean("search", "files", fallback=True))
        self.folders_var = tk.BooleanVar(value=config.getboolean("search", "folders", fallback=True))
        self.min_size_var = tk.StringVar(value=config.get("search", "min_size_kb", fallback=""))
        self.max_size_var = tk.StringVar(value=config.get("search", "max_size_kb", fallback=""))
        self.days_var = tk.StringVar(value=config.get("search", "modified_days", fallback=""))
        self.size_unit_var = tk.StringVar(value=config.get('search', 'size_unit', fallback='kB'))
        if self.size_unit_var.get() not in ('kB', 'MB', 'GB'): self.size_unit_var.set('kB')
        for variable in (self.min_size_var,self.max_size_var):
            if variable.get() and self.size_unit_var.get()!='kB':
                try:variable.set(f'{float(variable.get()) / (1024 ** (1 if self.size_unit_var.get()=="MB" else 2)):g}')
                except ValueError:pass
        self.title(tr("PFC Search")); self.geometry(config.get("search", "geometry", fallback="1100x720")); self.minsize(720, 480)
        self.protocol("WM_DELETE_WINDOW", self.close); self.bind("<Escape>", lambda _e: (self.escape(),'break')[1])
        self.bind("<F3>", lambda _e: (self.preview_selected(),'break')[1])
        self.bind("<F9>", lambda _e: (self.compare_selected(),'break')[1])
        self.bind('<F2>', lambda _e: self.rename_selected())
        self.bind('<F11>', lambda _e: (self.copy_paths(),'break')[1])

        form = ttk.Frame(self, padding=7); form.pack(fill="x")
        self.form = form
        self.query_rows = []
        self.mask_entry = None
        for row, (label, variable) in enumerate((("Start in:", self.path_var), ("Name/mask:", self.mask_var),
                                                 ("Containing text:", self.content_var))):
            ttk.Label(form, text=tr(label)).grid(row=row, column=0, sticky="w", padx=(0, 5), pady=2)
            group = ttk.Frame(form); group.grid(row=row, column=1, columnspan=2 if row == 0 else 1, sticky='ew', pady=2)
            related = ttk.Frame(group); related.pack(side='right', padx=(5, 0))
            entry = ttk.Entry(group, textvariable=variable, width=10)
            entry.pack(side='left', fill='x', expand=True)
            self.query_rows.append((entry, related))
            entry.bind("<Return>", lambda _event: (self.start(),'break')[1])
            if row == 1: self.mask_entry = entry
        options = self.query_rows[0][1]
        ttk.Label(options, text=tr("Depth:")).pack(side="left")
        self.depth_combo = ttk.Combobox(options, textvariable=self.depth_var, state="readonly", width=6,
                                        values=tuple(self.depth_values))
        self.depth_combo.pack(side="left", padx=(3, 0))
        options = self.query_rows[1][1]
        ttk.Checkbutton(options, text=tr("Files"), variable=self.files_var).pack(side="left")
        ttk.Checkbutton(options, text=tr("Folders"), variable=self.folders_var).pack(side="left", padx=(3, 0))
        self.case_check = ttk.Checkbutton(self.query_rows[2][1], text=tr("Case sensitive"), variable=self.case_var)
        self.case_check.pack(side="left")
        ToolTip(self.case_check, lambda: tr('Case sensitive for both name and content'))
        advanced = self.advanced = ttk.Frame(form)
        advanced.grid(row=3,column=0,columnspan=3,sticky='ew',pady=2)
        size = self.size_controls = ttk.Frame(advanced)
        size.grid(row=0,column=0,sticky='w')
        for col,(label,variable) in enumerate((('Size min:',self.min_size_var),('max:',self.max_size_var))):
            ttk.Label(size,text=tr(label)).grid(row=0,column=col*2,sticky='w',padx=(0,3))
            ttk.Entry(size,textvariable=variable,width=5).grid(row=0,column=col*2+1,padx=(0,5))
        ttk.Combobox(size,textvariable=self.size_unit_var,values=('kB','MB','GB'),state='readonly',width=4).grid(row=0,column=4)
        days = self.days_controls = ttk.Frame(advanced)
        days.grid(row=0,column=1,sticky='e',padx=(8,0))
        ttk.Label(days,text=tr('Modified within:')).pack(side='left')
        ttk.Entry(days,textvariable=self.days_var,width=4).pack(side='left',padx=3)
        ttk.Label(days,text=tr('days')).pack(side='left')
        advanced.columnconfigure(1,weight=1)
        self.find_button = ttk.Button(form, text=tr('Search'), width=0, padding=(14,5), command=self.start)
        self.find_button.grid(row=1,column=2,sticky='nsew',padx=(8,0))
        self.cancel_button = ttk.Button(form, text=tr('Stop'), width=0, command=self.cancel, state='disabled')
        self.cancel_button.grid(row=2,column=2,sticky='ew',padx=(8,0))
        self.results_menu = tk.Menu(self, tearoff=False, font='TkMenuFont')
        for label, command in (('Go to File', self.go_selected), ('Preview', self.preview_selected),
                ('Compare', self.compare_selected), ('Send Listing to New Tab', self.send_listing),
                ('Copy Path', self.copy_paths), ('Rename', self.rename_selected)):
            self.results_menu.add_command(label=tr(label), command=command)
        form.columnconfigure(1, weight=1)

        activity = self.activity = ttk.Frame(self, padding=(7, 3))
        activity.pack(fill='x')
        activity.columnconfigure(1, weight=1)
        self.status = ttk.Label(activity, anchor='w', font='TkHeadingFont')
        self.status.grid(row=0,column=0,sticky='ew',padx=(0,8))
        self.progress = ttk.Progressbar(activity, mode='determinate', value=0, length=120)
        self.progress.grid(row=0,column=1,sticky='ew')
        self.progress_eta = ttk.Label(activity, anchor='w')
        self.progress_eta.grid(row=1,column=0,columnspan=2,sticky='ew')
        activity.bind('<Configure>',lambda e:(self.status.configure(wraplength=max(160,e.width-150)),
                                               self.progress_eta.configure(wraplength=max(160,e.width-20))))
        actions = self.result_actions = ttk.Frame(self,padding=(7,2))
        actions.pack(fill='x')
        self.result_buttons=[]
        for label,command in (('Go to File',self.go_selected),('List → New Tab',self.send_listing),
                ('F2 Rename',self.rename_selected),('F3 Preview',self.preview_selected),
                ('F9 Compare',self.compare_selected),('F11 Copy Path',self.copy_paths)):
            button=ttk.Button(actions,text=tr(label),width=0,command=command,state='disabled')
            self.result_buttons.append(button)
        ToolTip(self.result_buttons[1],lambda:tr('Send Listing to New Tab'))
        ToolTip(self.result_buttons[0],lambda:tr('Double-click locates and closes search; Enter / Go to File keeps search open. F3 previews; F9 compares.'))
        self.bind('<Configure>',self._layout_controls,add='+')
        footer = ttk.Frame(self, padding=(7, 2)); footer.pack(side='bottom', fill='x')
        self.criteria_label = ttk.Label(footer, anchor='w', width=1)
        self.criteria_label.pack(side='left', fill='x', expand=True)
        ToolTip(self.criteria_label, lambda: self.criteria_label.cget('text'))
        body = ttk.Frame(self); body.pack(fill="both", expand=True)
        columns = ("folder", "size", "modified", "ext", "attributes")
        self.tree = ttk.Treeview(body, columns=columns, show="tree headings", selectmode="extended",
                                 displaycolumns=('attributes','folder','size','modified','ext'),
                                 style="PFCSearch.Treeview")
        self.tree.heading("#0", text=tr("Name") + " ▲", command=lambda: self.change_sort("name")); self.tree.column("#0", width=260, stretch=False)
        for col, width in (("folder", 460), ("size", 90), ("modified", 140), ("ext", 60), ("attributes", 90)):
            self.tree.heading(col, text=tr(col.title()), command=lambda c=col: self.change_sort(c))
            self.tree.column(col, width=width, anchor="e" if col == "size" else "w", stretch=False)
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview); self.tree.configure(yscrollcommand=scroll.set)
        horizontal = ttk.Scrollbar(body, orient='horizontal', command=self.tree.xview)
        self.tree.configure(xscrollcommand=horizontal.set)
        horizontal.pack(side='bottom', fill='x')
        scroll.pack(side="right", fill="y"); self.tree.pack(side="left", fill="both", expand=True)
        self.empty_hint = ttk.Label(body,anchor='center',justify='center',padding=12)
        body.bind('<Configure>',lambda e:self.empty_hint.configure(wraplength=max(150,e.width-60)))
        self.tree.bind("<Double-1>", self.double_click_result)
        self.tree.bind("<Return>", lambda _e: (self.go_selected(),'break')[1])
        self.tree.bind('<Button-3>',self.context_menu)
        self.tree.bind('<Shift-F10>',self.context_menu)
        self.tree.bind('<<TreeviewSelect>>',lambda _e:self._sync_result_actions())
        self.tree.bind("<Configure>", self._schedule_column_resize)
        for variable in (self.mask_var, self.content_var, self.case_var, self.depth_var,
                         self.files_var, self.folders_var, self.min_size_var,
                         self.max_size_var, self.days_var, self.size_unit_var):
            variable.trace_add("write", self._update_criteria_summary)
        self._update_criteria_summary()
        self._show_search_state()
        self.apply_color_scheme(getattr(master, "palette", color_scheme("light")))
        install_button_tooltips(self); self.after_idle(self.activate)

    def _layout_controls(self,event=None):
        if event is not None and event.widget is not self:return
        available=max(1,self.winfo_width()-14)
        narrow=self.size_controls.winfo_reqwidth()+self.days_controls.winfo_reqwidth()+12>available
        self.days_controls.grid_configure(row=1 if narrow else 0,column=0 if narrow else 1,
                                          sticky='w' if narrow else 'e',padx=0 if narrow else (8,0))
        # Equal-width columns must fit the widest label, not just the sum of
        # unequal requested widths (Windows fonts exposed clipping otherwise).
        widest=max(b.winfo_reqwidth()+4 for b in self.result_buttons)
        columns=next((n for n in (6,3,2,1) if widest*n<=available),1)
        for col in range(6):self.result_actions.columnconfigure(col,weight=1 if col<columns else 0,uniform='actions' if col<columns else '')
        for i,button in enumerate(self.result_buttons):button.grid(row=i//columns,column=i%columns,sticky='ew',padx=2,pady=1)

    def _sync_result_actions(self):
        selected=len(self.tree.selection());busy=self.search_state in ('running','cancelling','resetting')
        available=(selected>0,bool(self.results) and self.on_send_listing is not None,selected==1 and not busy,selected>0,
                   selected>=2 and self.on_compare is not None,selected>0)
        if getattr(self,'_result_availability',None)==available:return
        self._result_availability=available
        for button,enabled in zip(self.result_buttons,available):button.configure(state='normal' if enabled else 'disabled')
        for index,enabled in enumerate((available[0],available[3],available[4],available[1],available[5],available[2])):
            self.results_menu.entryconfigure(index,state='normal' if enabled else 'disabled')

    def context_menu(self,event):
        if getattr(event,'keysym','')=='F10':
            iid=self.tree.focus();box=self.tree.bbox(iid) if iid else ()
            if not box:return 'break'
            x,y=self.tree.winfo_rootx()+box[0]+20,self.tree.winfo_rooty()+box[1]+box[3]
        else:
            iid=self.tree.identify_row(event.y)
            if not iid or self.tree.identify_region(event.x,event.y) not in ('tree','cell'):return 'break'
            x,y=event.x_root,event.y_root
        if iid not in self.tree.selection():self.tree.selection_set(iid)
        self.tree.focus(iid);self.tree.focus_set();self._sync_result_actions()
        try:self.results_menu.tk_popup(x,y)
        finally:self.results_menu.grab_release()
        return 'break'

    def _reset_column_measurements(self) -> None:
        font = tkfont.nametofont("TkDefaultFont")
        heading = tkfont.nametofont("TkHeadingFont")
        self._column_desired = {
            "name": heading.measure(tr("Name") + " ▲") + 32,
            "folder": heading.measure(tr("Folder")) + 32,
            "size": heading.measure(tr("Size")) + 28,
            "modified": heading.measure(tr("Modified")) + 28,
            "ext": heading.measure(tr("Ext")) + 28,
            "attributes": max(heading.measure(tr("Attributes")), font.measure(tr('Hidden')+' · '+tr('System'))) + 24,
        }
        for iid in self.tree.get_children():
            values = self.tree.item(iid, "values")
            if len(values) >= 4:
                self._measure_result(str(self.tree.item(iid, "text")), *map(str, values[:5]),
                                     schedule=False)
        self._schedule_column_resize()

    def _measure_result(self, name: str, folder: str, size: str, modified: str, ext: str,
                        attributes: str = '', schedule: bool = True) -> None:
        font = tkfont.nametofont("TkDefaultFont")
        for key, value in (("name", name), ("folder", folder), ("size", size),
                           ("modified", modified), ("ext", ext), ("attributes", attributes)):
            self._column_desired[key] = max(self._column_desired.get(key, 0),
                                            font.measure(value) + (38 if key == "name" else 24))
        if schedule:
            self._schedule_column_resize()

    def _schedule_column_resize(self, _event=None) -> None:
        if self._column_resize_job is not None:
            self.after_cancel(self._column_resize_job)
        self._column_resize_job = self.after(90, self._resize_columns)

    def _resize_columns(self) -> None:
        self._column_resize_job = None
        widths = search_column_widths(self.tree.winfo_width(), self._column_desired)
        self.tree.column("#0", width=widths["name"])
        for column in ("folder", "size", "modified", "ext", "attributes"):
            self.tree.column(column, width=widths[column])

    def apply_color_scheme(self, palette) -> None:
        self.palette = palette
        self.configure(background=palette["window"])
        self._style_checks()

    def _style_checks(self):
        bg = self.winfo_rgb(self.palette.get('window', '#eeeeee'))
        style = readable_check_style(self, tkfont.nametofont('TkDefaultFont'),
                                      sum(bg)/3 < 32768, prefix='SearchCheck')
        pending = [self.form]
        while pending:
            widget = pending.pop(); pending.extend(widget.winfo_children())
            if isinstance(widget, ttk.Checkbutton): widget.configure(style=style)

    def apply_scale(self, scale: float) -> None:
        self._style_checks()
        style = ttk.Style(self)
        default_font = tkfont.nametofont("TkDefaultFont")
        style.configure("PFCSearch.Treeview", font=default_font,
                        rowheight=search_row_height(default_font.metrics("linespace"), scale))
        style.configure("PFCSearch.Treeview.Heading", font=tkfont.nametofont("TkHeadingFont"))
        self._reset_column_measurements()
        self.after_idle(self._layout_controls)

    def apply_language(self, old_language: str) -> None:
        depth = self.depth_values.get(self.depth_var.get(), self.depth_var.get())
        retranslate_widgets(self, old_language)
        for index,label in enumerate(('Go to File','Preview','Compare','Send Listing to New Tab','Copy Path','Rename')):
            self.results_menu.entryconfigure(index,label=tr(label))
        self.depth_values = {tr("Current"): "Current", "1": "1", "2": "2", "3": "3",
                             "5": "5", tr("All"): "All"}
        self.depth_combo.configure(values=tuple(self.depth_values))
        self.depth_var.set(next(label for label, value in self.depth_values.items() if value == depth))
        self.title(tr("PFC Search"))
        self.after_idle(self._layout_controls)
        self._apply_sort()
        self._reset_column_measurements()
        self._update_criteria_summary()
        self._show_search_state()

    def activate(self):
        self.reset_for_open()
        self.deiconify(); self.lift(); self.focus_force()
        self._update_criteria_summary()
        if self.mask_entry is not None:
            self.mask_entry.focus_set(); self.mask_entry.selection_range(0, "end"); self.mask_entry.icursor("end")

    def reset_for_open(self):
        """Start a fresh query; never let a previous worker refill old results."""
        self.cancel_event.set()
        if self.poll_job is not None:
            self.after_cancel(self.poll_job)
            self.poll_job = None
        reset_job = getattr(self, '_reset_job', None)
        if reset_job is not None:
            self.after_cancel(reset_job)
        self.clear_filters()
        self.mask_var.set('')
        self.tree.delete(*self.tree.get_children())
        self.results = []
        self.item_data.clear()
        self.search_state = 'ready'
        self._set_query_enabled(True)
        self.progress.stop(); self.progress.configure(value=0)
        self.progress_eta.configure(text='')
        self._show_search_state()
        self.find_button.configure(state='disabled')
        self.cancel_button.configure(state='disabled')
        self._finish_reset()

    def _finish_reset(self):
        self._reset_job = None
        if self.worker and self.worker.is_alive():
            self.search_state='resetting';self._show_search_state()
            if str(self.progress.cget('mode'))!='indeterminate':
                self.progress.configure(mode='indeterminate');self.progress.start(30)
            self._reset_job = self.after(50, self._finish_reset)
            return
        while True:
            try: self.messages.get_nowait()
            except queue.Empty: break
        self.worker = None
        self.search_state='ready';self.progress.stop();self.progress.configure(mode='determinate',value=0)
        self.progress_eta.configure(text='');self._show_search_state()
        self.find_button.configure(state='normal')

    def _update_criteria_summary(self, *_args) -> None:
        if not hasattr(self, "criteria_label"):
            return
        mask = self.mask_var.get().strip() or "*"
        scope = "/".join(label for label, enabled in (
            (tr("Files"), self.files_var.get()), (tr("Folders"), self.folders_var.get())) if enabled) or "—"
        parts = [f"{tr('Name/mask:')} {mask}", scope,
                 f"{tr('Depth:')} {self.depth_var.get()}"]
        if self.content_var.get().strip():
            parts.append(f"{tr('Containing text:')} {self.content_var.get().strip()}")
        if self.min_size_var.get().strip() or self.max_size_var.get().strip():
            parts.append(f"{tr('Size')}: {self.min_size_var.get().strip() or '0'}–{self.max_size_var.get().strip() or '∞'} {self.size_unit_var.get()}")
        if self.days_var.get().strip():
            parts.append(f"{tr('Modified within days:')} {self.days_var.get().strip()}")
        if self.case_var.get():
            parts.append(tr("Case sensitive"))
        self.criteria_label.configure(text=f"{tr('Filters:')} " + " · ".join(parts))

    def clear_filters(self) -> None:
        self.mask_var.set("*")
        self.content_var.set("")
        self.case_var.set(False)
        self.depth_var.set(tr("All"))
        self.files_var.set(True)
        self.folders_var.set(True)
        self.min_size_var.set("")
        self.max_size_var.set("")
        self.size_unit_var.set('kB')
        self.days_var.set("")
        if self.search_state not in ('running','cancelling'):
            self.status.configure(text=tr("Filters cleared"))
        self.mask_entry.focus_set()
        self.mask_entry.selection_range(0, "end")

    def change_sort(self, column):
        self.sort_reverse = not self.sort_reverse if self.sort_column == column else False
        self.sort_column = column
        self._apply_sort()

    def _apply_sort(self):
        column = self.sort_column
        labels = {"name": tr("Name"), "folder": tr("Folder"), "size": tr("Size"),
                  "modified": tr("Modified"), "ext": tr("Ext"), "attributes": tr('Attributes')}
        for name, label in labels.items():
            marker = (" ▲" if not self.sort_reverse else " ▼") if name == column else ""
            self.tree.heading("#0" if name == "name" else name, text=label + marker)
        for index, iid in enumerate(sorted(self.tree.get_children(),
                                            key=lambda item: self.item_data[item][column],
                                            reverse=self.sort_reverse)):
            self.tree.move(iid, "", index)

    def criteria(self):
        def number(value, factor=1):
            if not value.strip():
                return None
            try:
                result = float(value) * factor
            except ValueError as exc:
                raise ValueError("Enter a finite, non-negative number.") from exc
            if not math.isfinite(result) or result < 0:
                raise ValueError("Enter a finite, non-negative number.")
            return result
        depth = self.depth_values.get(self.depth_var.get(), self.depth_var.get())
        max_depth = None if depth == "All" else (0 if depth == "Current" else int(depth))
        days = number(self.days_var.get())
        factor={'kB':1024,'MB':1024**2,'GB':1024**3}[self.size_unit_var.get()]
        minimum, maximum = number(self.min_size_var.get(), factor), number(self.max_size_var.get(), factor)
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("Minimum size cannot exceed maximum size.")
        return dict(root=Path(self.path_var.get().strip().strip('"')), masks=self.mask_var.get(), content=self.content_var.get(),
                    case=self.case_var.get(), max_depth=max_depth, files=self.files_var.get(), folders=self.folders_var.get(),
                    min_size=minimum, max_size=maximum,
                    since=datetime.now() - timedelta(days=days) if days is not None else None)

    def start(self):
        if getattr(self, '_reset_job', None) is not None: return
        if self.search_state in ('running','cancelling') or (self.worker and self.worker.is_alive()): return
        try:
            criteria = self.criteria()
        except (ValueError, OverflowError) as exc:
            messagebox.showerror(tr("Search"), tr(str(exc)), parent=self)
            return
        if not criteria["root"].is_dir(): messagebox.showerror(tr("Search"), tr("Start path is not a folder."), parent=self); return
        self.tree.delete(*self.tree.get_children()); self.results=[]; self.item_data.clear(); self.cancel_event.clear()
        self._reset_column_measurements()
        self.find_button.configure(state="disabled"); self.cancel_button.configure(state="normal")
        self.search_state='running'; self._scanned_folders=self._skipped=0
        self._set_query_enabled(False)
        self._progress_started = time.monotonic(); self._elapsed_finished = None
        self.progress.stop(); self.progress.configure(mode="indeterminate", maximum=100, value=0); self.progress.start(30)
        self._show_search_state()
        self.worker = threading.Thread(target=self._search, args=(criteria,), daemon=True); self.worker.start(); self._poll()

    def _search(self, c):
        count = 0; processed_folders = 0; discovered_folders = 1
        try:
            for current, dirs, files in os.walk(c["root"],onerror=lambda exc:self.messages.put(('skipped',))):
                if self.cancel_event.is_set() or count >= RESULT_LIMIT: break
                depth = len(Path(current).relative_to(c["root"]).parts)
                folder_names = list(dirs)
                if c["max_depth"] is not None and depth >= c["max_depth"]: dirs[:] = []
                discovered_folders += len(dirs)
                processed_folders += 1
                self.messages.put(("progress", processed_folders, discovered_folders))
                candidates = ([Path(current) / name for name in folder_names] if c["folders"] else []) + ([Path(current) / name for name in files] if c["files"] else [])
                for path in candidates:
                    if self.cancel_event.is_set() or count >= RESULT_LIMIT: break
                    try:
                        stat = path.stat()
                        if not name_matches(path.name, c["masks"], c["case"]): continue
                        if path.is_file() and c["min_size"] is not None and stat.st_size < c["min_size"]: continue
                        if path.is_file() and c["max_size"] is not None and stat.st_size > c["max_size"]: continue
                        if c["since"] is not None and datetime.fromtimestamp(stat.st_mtime) < c["since"]: continue
                        if path.is_file() and not content_matches(path, c["content"], c["case"],on_error=lambda:self.messages.put(('skipped',))): continue
                        if path.is_dir() and c["content"]: continue
                        self.messages.put(("item", path, stat)); count += 1
                    except OSError: self.messages.put(('skipped',)); continue
            self.messages.put(("done", count, self.cancel_event.is_set(), count >= RESULT_LIMIT))
        except BaseException as exc:
            log=getattr(getattr(self,'master',None),'debug_log',None)
            if log:log.exception('search.worker.failed',exc)
            self.messages.put(("error", str(exc)))

    def _poll(self):
        self.poll_job = None
        processed = 0
        while processed < 250:
            try: message = self.messages.get_nowait()
            except queue.Empty: break
            processed += 1
            if message[0] == "item":
                _, path, stat = message; self.results.append(path)
                folder = str(path.parent)
                size_text = "<DIR>" if path.is_dir() else f"{stat.st_size:,}"
                modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                extension = "" if path.is_dir() else path.suffix[1:].upper()
                attributes = search_attributes(path, stat)
                iid = self.tree.insert("", "end", text=path.name, tags=(str(path),),
                                       values=(folder, size_text, modified, extension, attributes))
                self._measure_result(path.name, folder, size_text, modified, extension, attributes)
                self.item_data[iid] = {"name": path.name.casefold(), "folder": str(path.parent).casefold(),
                                       "size": stat.st_size, "modified": stat.st_mtime,
                                       "ext": ("" if path.is_dir() else path.suffix[1:]).casefold(),
                                       "attributes": attributes.casefold()}
            elif message[0] == "done":
                _, count, cancelled, limited = message
                self.search_state='cancelled' if cancelled else 'limited' if limited else 'partial' if self._skipped else 'complete'
                self.find_button.configure(state="normal"); self.cancel_button.configure(state="disabled")
                self._set_query_enabled(True)
                self.progress.stop(); self.progress.configure(mode="determinate",value=100 if self.search_state=='complete' else 0)
                self.worker = None
                self._apply_sort()
            elif message[0] == "error":
                self.find_button.configure(state="normal"); self.cancel_button.configure(state="disabled")
                self.progress.stop(); self.progress.configure(mode="determinate", value=0)
                self.search_state='failed'; self._set_query_enabled(True)
                self.worker = None
                self._show_search_state()
                self.update_idletasks()
                messagebox.showerror(tr("Search failed"), message[1], parent=self)
            elif message[0] == 'skipped':
                self._skipped+=1
            elif message[0] == "progress":
                _, completed, total = message
                self._scanned_folders=completed
        self._show_search_state()
        if not self.messages.empty() or self.search_state in ('running','cancelling'):
            self.poll_job = self.after(40, self._poll)

    def _set_query_enabled(self, enabled):
        if enabled:
            for widget,state in self._query_states:
                if widget.winfo_exists(): widget.configure(state=state)
            self._query_states=[]
            return
        if self._query_states: return
        pending=[self.form]
        while pending:
            widget=pending.pop(); pending.extend(widget.winfo_children())
            if isinstance(widget,(ttk.Entry,ttk.Combobox,ttk.Checkbutton)) or (isinstance(widget,ttk.Button) and widget not in (self.find_button,self.cancel_button)):
                self._query_states.append((widget,str(widget.cget('state'))))
                widget.configure(state='disabled')

    def _show_search_state(self):
        count=len(self.results)
        self._sync_result_actions()
        if self.search_state in ('running','cancelling','resetting'):
            if not self.progress.winfo_manager():self.progress.grid()
        elif self.progress.winfo_manager():self.progress.grid_remove()
        labels={'ready':'Ready to search', 'resetting':'Stopping previous search… please wait', 'running':'Searching… {count} found so far',
                'cancelling':'Cancelling… {count} found so far',
                'complete':'Search complete — {count} found',
                'cancelled':'Search cancelled — {count} partial results',
                'limited':'Result limit reached — {count} partial results',
                'partial':'Search incomplete — {count} found; some items could not be read',
                'failed':'Search failed — {count} partial results'}
        status=tr(labels[self.search_state],count=count)
        if self.status.cget('text')!=status:self.status.configure(text=status)
        if self.search_state!='ready':
            elapsed=max(0,int(time.monotonic()-self._progress_started))
            # Freeze the displayed duration after reaching a terminal state.
            if self.search_state not in ('running','cancelling','resetting'):
                if self._elapsed_finished is None:self._elapsed_finished=elapsed
                elapsed=self._elapsed_finished
            detail=tr('Elapsed {minutes:02d}:{seconds:02d} · Folders scanned: {folders} · Unreadable: {skipped}',
                minutes=elapsed//60,seconds=elapsed%60,folders=self._scanned_folders,skipped=self._skipped)
            if self.progress_eta.cget('text')!=detail:self.progress_eta.configure(text=detail)
        hints={'ready':'Enter a name or mask, then choose Find.', 'resetting':'Waiting for the current read to stop…',
               'running':'Searching… results will appear here.',
               'cancelling':'Waiting for the current read to stop…',
               'complete':'No matching items. Try another name or folder.',
               'cancelled':'Search cancelled. No results collected.',
               'limited':'Search stopped at the result limit.',
               'partial':'Some locations could not be read. Check access and try again.',
               'failed':'Search failed. Check the error and try again.'}
        if count:self.empty_hint.place_forget()
        else:
            hint=tr(hints[self.search_state])
            if self.empty_hint.cget('text')!=hint:self.empty_hint.configure(text=hint)
            if not self.empty_hint.winfo_manager():
                self.empty_hint.place(relx=.5,rely=.35,anchor='center');self.empty_hint.lift()

    def selected_paths(self):
        return [Path(self.tree.item(iid, "tags")[0]) for iid in self.tree.selection()
                if self.tree.item(iid, "tags")]

    def rename_selected(self):
        # A live worker may still emit paths under the old name. Do not mutate
        # files until traversal has stopped and all queued results are drained.
        if self.search_state in ('running','cancelling','resetting'):return 'break'
        paths=self.selected_paths()
        if len(paths)!=1:return 'break'
        original=paths[0]
        name=simpledialog.askstring(tr('Rename'),tr('New name:'),initialvalue=original.name,parent=self)
        if name is None or name==original.name:return 'break'
        try:
            target=original.with_name(name)
            execute_rename_pairs([(original,target)])
        except (OSError,ValueError) as exc:
            log=getattr(self.master,'debug_log',None)
            if log:log.exception('search.rename.failed',exc)
            messagebox.showerror(tr('Rename failed'),str(exc),parent=self)
            return 'break'
        updated=[]
        for iid in self.tree.get_children():
            path=Path(self.tree.item(iid,'tags')[0])
            try:new=target/path.relative_to(original)
            except ValueError:new=path
            updated.append(new)
            if new!=path:
                values=list(self.tree.item(iid,'values'));values[0]=str(new.parent)
                self.tree.item(iid,text=new.name,tags=(str(new),),values=values)
                try:values[4]=search_attributes(new,new.stat())
                except OSError:pass  # A concurrent removal is handled on navigation.
                self.item_data[iid].update(name=new.name.casefold(),folder=str(new.parent).casefold(),ext=new.suffix[1:].casefold() if values[1]!='<DIR>' else '',attributes=values[4].casefold())
                values[3]=self.item_data[iid]['ext'].upper();self.tree.item(iid,values=values)
        self.results=updated;self._apply_sort();self._reset_column_measurements();self._show_search_state()
        return 'break'
    def double_click_result(self, event):
        iid = self.tree.identify_row(event.y)
        if iid and self.tree.identify_region(event.x,event.y) in ('tree','cell'):
            self.tree.selection_set(iid); self.tree.focus(iid)
            self.go_selected(close_after=True)
        return 'break'

    def go_selected(self, close_after=False):
        paths=self.selected_paths()
        if paths:
            if self.on_go(paths[0]) is False: return
            if close_after:
                self.close()
                return
            try: self.lower(self.master)
            except tk.TclError: pass
    def preview_selected(self):
        paths=self.selected_paths()
        if paths:
            ordered = [Path(self.tree.item(iid, "tags")[0]) for iid in self.tree.get_children()
                       if self.tree.item(iid, "tags")]
            self.on_preview(ordered, paths[0], paths)
    def compare_selected(self):
        paths = self.selected_paths()
        if len(paths) < 2:
            messagebox.showinfo(tr("Compare"), tr("Select two search results first."), parent=self)
            return
        if self.on_compare is not None:
            self.on_compare(paths[0], paths[1])
    def send_listing(self):
        paths = [Path(self.tree.item(iid, "tags")[0]) for iid in self.tree.get_children()
                 if self.tree.item(iid, "tags")]
        if paths and self.on_send_listing is not None:
            self.on_send_listing(paths)
    def copy_paths(self):
        paths=self.selected_paths()
        if paths: self.clipboard_clear(); self.clipboard_append("\n".join(map(str, paths))); self.update_idletasks()
    def cancel(self):
        if self.search_state not in ('running','cancelling'):return
        self.cancel_event.set(); self.search_state='cancelling'; self.cancel_button.state(['disabled'])
        self._show_search_state()
    def escape(self): self.cancel() if self.worker and self.worker.is_alive() else self.close()
    def close(self):
        self.cancel_event.set()
        if getattr(self, '_reset_job', None) is not None:
            self.after_cancel(self._reset_job)
        if self.poll_job is not None:
            try: self.after_cancel(self.poll_job)
            except tk.TclError: pass
        if self._column_resize_job is not None:
            try: self.after_cancel(self._column_resize_job)
            except tk.TclError: pass
        if not self.config_data.has_section("search"): self.config_data.add_section("search")
        for key in ("mask", "content"):
            self.config_data.remove_option("search", key)
        def stored_kb(variable):
            try:return f'{float(variable.get()) * {"kB":1,"MB":1024,"GB":1024**2}[self.size_unit_var.get()]:g}' if variable.get().strip() else ''
            except ValueError:return ''
        for key, value in (("geometry", self.geometry()),
                           ("case_sensitive", str(self.case_var.get()).lower()),
                           ("depth", self.depth_values.get(self.depth_var.get(), self.depth_var.get())),
                           ("files", str(self.files_var.get()).lower()), ("folders", str(self.folders_var.get()).lower()),
                           ("min_size_kb", stored_kb(self.min_size_var)), ("max_size_kb", stored_kb(self.max_size_var)),
                           ('size_unit',self.size_unit_var.get()),
                           ("modified_days", self.days_var.get())):
            self.config_data.set("search", key, value.replace("%", "%%"))
        self.save_config(); self.destroy()
