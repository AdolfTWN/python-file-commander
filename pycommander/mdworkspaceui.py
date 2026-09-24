"""A compact opt-in Markdown discovery dialog; no scan until Search is pressed."""
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog

from .i18n import tr, get_language
from .mdjobs import MarkdownJobs
from .mdworkspace import workspace_root, remember_markdown_workspace
from .workflows import workflow_dialog_geometry, style_workflow_controls


class MarkdownWorkspaceDialog(tk.Toplevel):
    def __init__(self, page, module_file, packaged, mode='files', query='', fragment=''):
        super().__init__(page)
        self.page = page; self.document = page.path; self.fragment = fragment; self.initial_query = query
        self.title(tr('Markdown workspace')); workflow_dialog_geometry(self, page.host, 840, 540)
        self.minsize(min(600,self.winfo_screenwidth()-60),min(440,self.winfo_screenheight()-100))
        self.jobs = MarkdownJobs(module_file, packaged); self.poll_id = None
        self.results = []; self.result_root = None; self.request = None
        self.previous_suspended = page._md_auto_suspended
        page._md_auto_suspended = True
        if page._md_jobs.pending: page._md_jobs.cancel()
        page._md_request = None; page._md_queued = None
        config = page.config_data
        remembered = config.get('markdown_workspace', 'root', fallback=str(self.document.parent))
        try: remembered = str(workspace_root(remembered, self.document))
        except ValueError: remembered = str(self.document.parent)
        self.root_var = tk.StringVar(value=remembered)
        saved_depth = config.get('markdown_workspace', 'depth', fallback='3')
        self.depth_var = tk.StringVar(value=saved_depth if saved_depth in ('1','3','5','8') else '3')
        self.query_var = tk.StringVar(value=query)
        self.modes = {tr('Find Markdown files'): 'files', tr('Resolve wiki link'): 'wiki',
                      tr('Backlinks to this document'): 'backlinks'}
        self.mode_var = tk.StringVar(value=next(k for k,v in self.modes.items() if v == mode))
        outer = ttk.Frame(self, padding=10); outer.pack(fill='both', expand=True)
        outer.columnconfigure(1, weight=1); outer.rowconfigure(4, weight=1)
        ttk.Label(outer, text=tr('Project folder')).grid(row=0,column=0,sticky='w',padx=(0,8))
        self.scope = ttk.Entry(outer,textvariable=self.root_var,state='readonly')
        self.scope.grid(row=0,column=1,sticky='ew')
        self.browse = ttk.Button(outer,text=tr('Browse')+'…',command=self.choose_root)
        self.browse.grid(row=0,column=2,padx=(6,0))
        self.mode = ttk.Combobox(outer,textvariable=self.mode_var,values=list(self.modes),state='readonly',width=28)
        self.mode.grid(row=1,column=0,columnspan=2,sticky='ew',pady=8)
        self.mode.bind('<<ComboboxSelected>>',lambda e:self.changed())
        depth = ttk.Frame(outer); depth.grid(row=1,column=2,padx=(8,0))
        ttk.Label(depth,text=tr('Depth')).pack(side='left')
        self.depth = ttk.Combobox(depth,textvariable=self.depth_var,values=('1','3','5','8'),state='readonly',width=3)
        self.depth.pack(side='left',padx=4)
        self.depth.bind('<<ComboboxSelected>>',lambda e:self.changed())
        self.query = ttk.Entry(outer,textvariable=self.query_var)
        self.query.grid(row=2,column=0,columnspan=2,sticky='ew')
        self.search = ttk.Button(outer,text=tr('Search'),command=self.start)
        self.search.grid(row=2,column=2,sticky='ew',padx=(8,0))
        self.note = ttk.Label(outer,text=tr('No automatic index. Up to 5,000 entries / 3 seconds / 50 results. Excluded and unavailable folders are skipped.'),wraplength=790)
        self.note.grid(row=3,column=0,columnspan=3,sticky='ew',pady=8)
        listing = ttk.Frame(outer); listing.grid(row=4,column=0,columnspan=3,sticky='nsew')
        self.tree = ttk.Treeview(listing,columns=('path','kind'),show='headings',selectmode='browse')
        self.tree.heading('path',text=tr('Relative path'));self.tree.heading('kind',text=tr('Match type'))
        self.tree.column('path',width=440,minwidth=180);self.tree.column('kind',width=240,minwidth=130)
        vertical = ttk.Scrollbar(listing,command=self.tree.yview)
        horizontal = ttk.Scrollbar(listing,orient='horizontal',command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        vertical.pack(side='right',fill='y');horizontal.pack(side='bottom',fill='x');self.tree.pack(fill='both',expand=True)
        self.status = ttk.Label(outer,text=tr('Confirm the project folder, then press Search.'),wraplength=790)
        self.status.grid(row=5,column=0,columnspan=3,sticky='ew',pady=8)
        footer = ttk.Frame(outer);footer.grid(row=6,column=0,columnspan=3,sticky='ew')
        self.cancel = ttk.Button(footer,text=tr('Cancel search'),command=self.cancel_search,state='disabled')
        self.cancel.pack(side='left')
        self.open_button = ttk.Button(footer,text=tr('Open selected'),command=self.open_selected,state='disabled')
        self.open_button.pack(side='right')
        ttk.Button(footer,text=tr('Close'),command=self.close).pack(side='right',padx=6)
        self.tree.bind('<<TreeviewSelect>>',lambda e:self.open_button.state(['!disabled'] if self.tree.selection() else ['disabled']))
        self.tree.bind('<Double-1>',lambda e:self.open_selected())
        self.tree.bind('<Return>',lambda e:self.open_selected())
        self.query.bind('<Return>',lambda e:self.start())
        self.query_var.trace_add('write',lambda *a:self.changed())
        self.bind('<Escape>',lambda e:self.close());self.protocol('WM_DELETE_WINDOW',self.close)
        self.bind('<Configure>',self.resize)
        self.bind('<Destroy>',self.destroyed,add='+')
        style_workflow_controls(self);self.changed();self.grab_set();self.query.focus_set()
        font=self._root()._workflow_fonts['body']
        for widget in (self.mode,self.depth):widget.configure(font=font)
        self.poll_id = self.after(40,self.poll)

    def resize(self,event):
        if event.widget is self:
            for widget in (self.note,self.status):widget.configure(wraplength=max(250,self.winfo_width()-30))

    def changed(self):
        self.cancel_search(announce=False)
        self.results=[];self.result_root=None
        self.tree.delete(*self.tree.get_children());self.open_button.state(['disabled'])
        backlink = self.modes[self.mode_var.get()] == 'backlinks'
        self.query.configure(state='disabled' if backlink else 'normal')
        self.status.configure(text=(tr('Backlinks scan local Markdown content on demand; filename-only references may be ambiguous.')
                                    if backlink else tr('Confirm the project folder, then press Search.')))

    def choose_root(self):
        chosen = filedialog.askdirectory(parent=self,initialdir=self.root_var.get(),mustexist=True)
        if not self.winfo_exists():return
        self.grab_set()
        if chosen:self.root_var.set(chosen);self.changed()

    def start(self):
        self.changed();self.jobs.reap()
        try:
            root = workspace_root(self.root_var.get(),self.document)
            request = {'action':'workspace','path':str(self.document),'root':str(root),
                       'depth':int(self.depth_var.get()),'mode':self.modes[self.mode_var.get()],
                       'query':self.query_var.get(),'language':get_language()}
            if not self.jobs.submit(request):
                self.status.configure(text=tr('Previous search is stopping; try again shortly.'));return 'break'
            self.request=request;self.search.state(['disabled']);self.cancel.state(['!disabled'])
            self.status.configure(text=tr('Searching within the confirmed folder…'))
        except (ValueError,OSError) as exc:self.status.configure(text=tr(str(exc)))
        return 'break'

    def poll(self):
        self.poll_id=None
        result=self.jobs.poll()
        if result is not None and self.request:
            request=self.request;self.request=None;self.search.state(['!disabled']);self.cancel.state(['disabled'])
            if 'error' in result:self.status.configure(text=tr(result['error']))
            else:
                self.results=result['results'];self.result_root=Path(result['root'])
                for i,item in enumerate(self.results):self.tree.insert('','end',iid=str(i),values=(item['path'],tr(item['detail'])))
                prefix=tr('Search incomplete') if result['reasons'] else tr('Search complete within this depth and exclusions')
                detail=tr('{count} results; {visited} entries; {skipped} skipped',count=len(self.results),visited=result['visited'],skipped=result['skipped'])
                reasons=' / '.join(tr(r) for r in result['reasons'])
                self.status.configure(text=prefix+' — '+detail+(' ('+reasons+')' if reasons else ''))
                config=self.page.config_data
                remember_markdown_workspace(config,self.result_root,request['depth'])
                self.page.save_config()
        if self.jobs.pending and time.monotonic()-self.jobs.started>4:
            self.cancel_search(announce=False)
            self.status.configure(text=tr('Search timed out; no complete result. Narrow the project folder.'))
        self.poll_id=self.after(40,self.poll)

    def cancel_search(self,announce=True):
        self.jobs.cancel();self.request=None;self.search.state(['!disabled']);self.cancel.state(['disabled'])
        if announce:self.status.configure(text=tr('Search canceled; no complete result.'))

    def open_selected(self):
        selected=self.tree.selection()
        if not selected or self.result_root is None:return 'break'
        item=self.results[int(selected[0])];root=self.result_root;path=root/item['path']
        fragment=self.fragment if self.modes[self.mode_var.get()]=='wiki' and self.query_var.get()==self.initial_query else ''
        self.close()
        self.page._queue_markdown(path,navigation=True,fragment=fragment)
        self.page._md_queued['request']['boundary']=str(root)
        self.page._md_queued['bookmark_boundary']=str(root)
        return 'break'

    def close(self):
        self.jobs.close()
        if self.poll_id is not None:self.after_cancel(self.poll_id);self.poll_id=None
        self.page._md_auto_suspended=self.previous_suspended
        self.page._md_last_probe=time.monotonic()
        self.grab_release();self.destroy();return 'break'

    def destroyed(self,event):
        if event.widget is self:
            self.jobs.close()
            if self.poll_id is not None:self.after_cancel(self.poll_id);self.poll_id=None
