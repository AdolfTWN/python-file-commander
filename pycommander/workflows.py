"""Compact, keyboard-first workflow pickers; no indexing or background polling."""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, font as tkfont

from .i18n import tr
from .workflowdata import WorkflowRecords
from .tooltip import ToolTip


def workflow_dialog_geometry(window, master, width=650, height=420):
    width = min(width, master.winfo_screenwidth() - 60)
    height = min(height, master.winfo_screenheight() - 100)
    x = max(0, min(master.winfo_screenwidth() - width, master.winfo_rootx() + 60))
    y = max(0, min(master.winfo_screenheight() - height, master.winfo_rooty() + 70))
    window.geometry(f'{width}x{height}+{x}+{y}')
    window.minsize(min(420, width), min(280, height))
    window.transient(master)
    window.bind('<KeyPress>', lambda e: 'break')
    def traverse(back=False):
        current = window.focus_get() or window
        target = current.tk_focusPrev() if back else current.tk_focusNext()
        if target is not None: target.focus_set()
        return 'break'
    window.bind('<Tab>', lambda e: traverse())
    window.bind('<Shift-Tab>', lambda e: traverse(True))
    window.bind('<ISO_Left_Tab>', lambda e: traverse(True))


def style_workflow_controls(window):
    root = window._root()
    base = tkfont.nametofont('TkDefaultFont', root=root)
    if not hasattr(root, '_workflow_fonts'):
        root._workflow_fonts = {name: tkfont.Font(root) for name in ('body', 'heading')}
    for name, font in root._workflow_fonts.items():
        font.configure(family=base.actual('family'), size=-min(22, max(14, abs(int(base.cget('size'))))),
                       weight='bold' if name == 'heading' else 'normal')
    font = root._workflow_fonts['body']; heading = root._workflow_fonts['heading']
    style = ttk.Style(root)
    for kind in ('TLabel', 'TButton', 'TEntry', 'Treeview'):
        style.configure('PFCWorkflow.'+kind, font=font)
    style.configure('PFCWorkflow.Treeview', rowheight=font.metrics('linespace')+8)
    style.configure('PFCWorkflow.Treeview.Heading', font=heading)
    pending = list(window.winfo_children())
    while pending:
        child = pending.pop(); pending.extend(child.winfo_children())
        kind = child.winfo_class()
        if kind in ('TLabel', 'TButton', 'TEntry', 'Treeview'):
            child.configure(style='PFCWorkflow.'+kind)
            if kind in ('TLabel', 'TEntry'): child.configure(font=font)
        elif isinstance(child, tk.Listbox): child.configure(font=font)


class WorkflowPicker(tk.Toplevel):
    def __init__(self, master, title, records, save_config, capture, activate, describe):
        super().__init__(master)
        self.title(tr(title)); workflow_dialog_geometry(self, master)
        self.records, self.save_config = records, save_config
        self.capture, self.activate, self.describe = capture, activate, describe
        area = ttk.Frame(self, padding=10); area.pack(fill='both', expand=True)
        area.columnconfigure(0, weight=1); area.rowconfigure(1, weight=1)
        ttk.Label(area, text=tr(title), font='TkHeadingFont').grid(row=0, column=0, sticky='w', pady=(0, 6))
        frame = ttk.Frame(area); frame.grid(row=1, column=0, sticky='nsew')
        self.list = tk.Listbox(frame, exportselection=False, activestyle='dotbox', borderwidth=0,
                               highlightthickness=1, font='TkDefaultFont')
        palette = getattr(master, 'palette', None)
        if palette:
            self.list.configure(background=palette['content'], foreground=palette['text'],
                                 selectbackground=palette['selection'], selectforeground='#ffffff')
        scroll = ttk.Scrollbar(frame, command=self.list.yview)
        self.list.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y'); self.list.pack(fill='both', expand=True)
        self.detail = ttk.Label(area, anchor='nw', wraplength=600)
        self.detail_tooltip = ToolTip(self.detail, '')
        self.detail.grid(row=2, column=0, sticky='ew', pady=8)
        self.bind('<Configure>', lambda e: self.detail.configure(wraplength=max(200, self.winfo_width()-30)))
        bar = ttk.Frame(area); bar.grid(row=3, column=0, sticky='ew')
        self.save_button = ttk.Button(bar, text=tr('Save current')+'…', command=self.save_current)
        self.save_button.pack(side='left')
        self.remove_button = ttk.Button(bar, text=tr('Remove'), command=self.remove)
        self.remove_button.pack(side='left', padx=5)
        self.open_button = ttk.Button(bar, text=tr('Open'), command=self.open)
        self.open_button.pack(side='right')
        ttk.Button(bar, text=tr('Close'), command=self.close).pack(side='right', padx=5)
        self.list.bind('<<ListboxSelect>>', lambda e: self.selected())
        self.list.bind('<Double-1>', lambda e: self.open())
        self.bind('<Return>', lambda e: (self.focus_get().invoke(), 'break')[1]
                  if isinstance(self.focus_get(), ttk.Button) else self.open())
        self.bind('<Escape>', lambda e: self.close())
        self.protocol('WM_DELETE_WINDOW', self.close)
        style_workflow_controls(self)
        self.refresh(); self.grab_set(); self.list.focus_set()

    def refresh(self):
        self.entries = self.records.read()
        self.list.delete(0, 'end')
        for item in self.entries: self.list.insert('end', item['name'])
        if self.entries: self.list.selection_set(0)
        self.selected()

    def selected(self):
        selected = self.list.curselection()
        has = bool(selected)
        self.open_button.state(['!disabled'] if has else ['disabled'])
        self.remove_button.state(['!disabled'] if has else ['disabled'])
        value = self.describe(self.entries[selected[0]]['data']) if has else tr('Nothing saved yet. Use Save current to create a named entry.')
        self.detail_tooltip.text = str(value)
        # Keep the list usable with long paths. Full path remains in the saved
        # record; the focused item's concise context is not a second document.
        lines = str(value).splitlines()[:3]
        self.detail.configure(text='\n'.join(line if len(line) <= 110 else line[:45]+'…'+line[-60:] for line in lines))

    def save_current(self):
        name = simpledialog.askstring(self.title(), tr('Name'), parent=self)
        # Python's simpledialog releases its own grab without restoring ours.
        if self.winfo_exists(): self.grab_set()
        if name is None: return
        if any(r['name'].casefold() == name.strip().casefold() for r in self.entries):
            if not messagebox.askyesno(self.title(), tr('Replace this saved entry?'), parent=self): return
        try:
            data = self.capture()
            if data is None: return
            self.records.put(name, data); self.save_config(); self.refresh()
        except (OSError, ValueError) as exc:
            messagebox.showerror(self.title(), str(exc), parent=self)

    def remove(self):
        selection = self.list.curselection()
        if not selection: return
        name = self.entries[selection[0]]['name']
        if messagebox.askyesno(self.title(), tr('Remove saved entry?')+'\n'+name, parent=self):
            self.records.remove(name); self.save_config(); self.refresh()

    def open(self):
        selected = self.list.curselection()
        if not selected: return 'break'
        try:
            if self.activate(self.entries[selected[0]]['data']) is not False:
                self.close()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror(self.title(), str(exc), parent=self)
        return 'break'

    def close(self):
        self.grab_release(); self.destroy()
        return 'break'


def command_matches(commands, query):
    words = query.casefold().split()
    return [item for item in commands if all(word in ' '.join(map(str, item[:4])).casefold()
                                            for word in words)]


class CommandPalette(tk.Toplevel):
    def __init__(self, master, commands):
        super().__init__(master)
        self.title(tr('Command search')); workflow_dialog_geometry(self, master, 680, 390)
        self.commands = commands
        self.previous_focus = master.focus_get()
        area = ttk.Frame(self, padding=10); area.pack(fill='both', expand=True)
        area.columnconfigure(0, weight=1); area.rowconfigure(1, weight=1)
        self.query = tk.StringVar()
        self.entry = ttk.Entry(area, textvariable=self.query)
        self.entry.grid(row=0, column=0, sticky='ew', pady=(0, 7))
        self.list = ttk.Treeview(area, columns=('category', 'key'), show='tree headings', height=9,
                                 selectmode='browse')
        self.list.heading('#0', text=tr('Command')); self.list.heading('category', text=tr('Category'))
        self.list.heading('key', text=tr('Shortcut'))
        self.list.column('#0', width=340, minwidth=180)
        self.list.column('category', width=150, minwidth=90, stretch=False)
        self.list.column('key', width=110, minwidth=85, stretch=False)
        self.list.grid(row=1, column=0, sticky='nsew')
        self.hint = ttk.Label(area, text=tr('Type to filter • ↑ ↓ select • Enter run • Esc close'), anchor='w', wraplength=640)
        self.hint.grid(row=2, column=0, sticky='ew', pady=(7, 0))
        self.bind('<Configure>', lambda e: self.hint.configure(wraplength=max(200,self.winfo_width()-30)))
        self.query.trace_add('write', lambda *args: self.refresh())
        self.entry.bind('<Down>', lambda e: self.step(1)); self.entry.bind('<Up>', lambda e: self.step(-1))
        self.bind('<Return>', lambda e: self.run()); self.list.bind('<Double-1>', lambda e: self.run())
        self.bind('<Escape>', lambda e: self.close()); self.protocol('WM_DELETE_WINDOW', self.close)
        style_workflow_controls(self)
        self.refresh(); self.grab_set(); self.entry.focus_set()

    def refresh(self):
        self.filtered = command_matches(self.commands, self.query.get())
        self.list.delete(*self.list.get_children())
        for index, (label, category, key, aliases, callback) in enumerate(self.filtered):
            self.list.insert('', 'end', iid=str(index), text=label, values=(category, key))
        if self.filtered: self.list.selection_set('0')
        self.hint.configure(text=tr('Type to filter • ↑ ↓ select • Enter run • Esc close') if self.filtered
                            else tr('No matching commands. Try another word.'))

    def step(self, direction):
        selected = self.list.selection()
        if self.filtered:
            index = max(0, min(len(self.filtered)-1, (int(selected[0]) if selected else 0)+direction))
            self.list.selection_set(str(index)); self.list.see(str(index))
        return 'break'

    def run(self):
        selected = self.list.selection()
        if not selected: return 'break'
        command = self.filtered[int(selected[0])][4]
        root = self.master
        self.close(); root.after_idle(command)
        return 'break'

    def close(self):
        self.grab_release(); self.destroy()
        if self.previous_focus is not None and self.previous_focus.winfo_exists(): self.previous_focus.focus_set()
        return 'break'
