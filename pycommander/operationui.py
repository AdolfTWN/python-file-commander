"""Recoverable operation results with a scannable list and full selected detail."""
import tkinter as tk
from tkinter import ttk, font as tkfont
from .flowlayout import FlowToolbar
from .i18n import tr
from .windowplacement import popup_work_area, position_popup_in_work_area


class OperationResultWindow(tk.Toplevel):
    def __init__(self,master,verb,result,retry=None):
        super().__init__(master);self.withdraw();self.transient(master.winfo_toplevel())
        self.title(tr('{verb} result',verb=tr(verb)))
        self.summary=tr('{verb}: {completed} completed, {skipped} skipped, {failed} failed.',
            verb=tr(verb),completed=len(result.completed),skipped=len(result.skipped),failed=len(result.failures))
        outer=ttk.Frame(self,padding=10);outer.pack(fill='both',expand=True)
        self.heading=ttk.Label(outer,text=self.summary,font='TkHeadingFont',wraplength=700)
        self.heading.pack(fill='x',pady=(0,8))
        # Reserve actions before expanding data; very large reading fonts must
        # never push recovery/close controls below the window.
        self.actions=FlowToolbar(outer);self.actions.pack(side='bottom',fill='x')
        body=ttk.Frame(outer);body.pack(fill='both',expand=True)
        body.columnconfigure(0,weight=1);body.rowconfigure(0,weight=1)
        self.tree=ttk.Treeview(body,columns=('status',),show='tree headings',selectmode='browse',height=7)
        self.tree.heading('#0',text=tr('File'));self.tree.heading('status',text=tr('Status'))
        status_width=max(tkfont.nametofont('TkDefaultFont').measure(tr(label)) for label in ('Failed','Skipped','Status'))+24
        self.tree.column('#0',width=500,minwidth=100);self.tree.column('status',width=status_width,minwidth=status_width,stretch=False)
        vertical=ttk.Scrollbar(body,command=self.tree.yview);horizontal=ttk.Scrollbar(body,orient='horizontal',command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        self.tree.grid(row=0,column=0,sticky='nsew');vertical.grid(row=0,column=1,sticky='ns');horizontal.grid(row=1,column=0,sticky='ew')
        full=ttk.Frame(outer);full.pack(fill='both',expand=True,pady=8)
        scroll=ttk.Scrollbar(full);scroll.pack(side='right',fill='y')
        palette=getattr(master,'palette',{})
        self.detail=tk.Text(full,height=5,wrap='word',font='TkDefaultFont',yscrollcommand=scroll.set,takefocus=True,
            background=palette.get('content','#ffffff'),foreground=palette.get('text','#101010'))
        self.detail.pack(fill='both',expand=True);scroll.configure(command=self.detail.yview)
        self.records=[]
        for failure in result.failures:
            self.records.append((failure.source,tr('Failed'),str(failure.source)+
                ('\n→ '+str(failure.target) if failure.target else '')+'\n'+failure.message))
        for path in result.skipped:self.records.append((path,tr('Skipped'),str(path)+'\n'+tr('Skipped')))
        for index,(path,status,_) in enumerate(self.records):self.tree.insert('','end',iid=str(index),text=str(path),values=(status,))
        self.report=self.summary+'\n\n'+'\n\n'.join(detail for _,_,detail in self.records)
        self.tree.bind('<<TreeviewSelect>>',lambda e:self.select())
        self.copy_button=ttk.Button(self.actions,text=tr('Copy Details'),width=0,command=self.copy_report);self.actions.add(self.copy_button)
        if retry is not None and result.failures:
            def retry_failed():
                failed=list(dict.fromkeys(failure.source for failure in result.failures))
                self.destroy();retry(failed)
            self.retry_button=ttk.Button(self.actions,text=tr('Retry Failed'),width=0,command=retry_failed);self.actions.add(self.retry_button)
        self.close_button=ttk.Button(self.actions,text=tr('Close'),width=0,command=self.destroy);self.actions.add(self.close_button)
        self.bind('<Escape>',lambda e:self.destroy());self.bind('<KeyPress>',lambda e:'break')
        self.bind('<Return>',lambda e:self.focus_get().invoke() if isinstance(self.focus_get(),ttk.Button) else 'break')
        self.bind('<Configure>',lambda e:self.heading.configure(wraplength=max(100,e.width-24)) if e.widget is self else None)
        area=popup_work_area(master);line=tkfont.nametofont('TkDefaultFont').metrics('linespace')
        width=min(round(800*max(1,line/20)),area[2]-area[0]-48)
        height=min(round(500*max(1,line/20)),area[3]-area[1]-64)
        self.geometry(f'{width}x{height}');self.minsize(min(420,width),min(300,height))
        if self.records:self.tree.selection_set('0');self.tree.focus('0');self.select()
        self.deiconify();position_popup_in_work_area(self,master,area);self.lift();self.tree.focus_force()

    def select(self):
        selected=self.tree.selection()
        self.detail.configure(state='normal');self.detail.delete('1.0','end')
        if selected:self.detail.insert('1.0',self.records[int(selected[0])][2])
        self.detail.configure(state='disabled')

    def copy_report(self):
        self.clipboard_clear();self.clipboard_append(self.report);self.update_idletasks()
