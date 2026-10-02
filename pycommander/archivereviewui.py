"""Background archive staging and explicit reviewed commit around Folder Compare."""
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk,messagebox
from .archivereview import ArchiveReviewSession,archive_manifest
from .i18n import tr


class ArchiveReviewCompare(ttk.Frame):
    def __init__(self,master,left,right,folder_factory,file_factory,sync_executor,**options):
        super().__init__(master);self.view=self;self.paths=[Path(left),Path(right)]
        self.sessions=[None,None];self.inner=None;self.cancel_event=threading.Event();self.results=queue.Queue()
        self.busy=False;self._job=None;self.closed=False;self.palette=None
        self.folder_factory=folder_factory;self.file_factory=file_factory;self.sync_executor=sync_executor;self.options=options
        bar=ttk.Frame(self);bar.pack(fill='x')
        ttk.Button(bar,text=tr('Review archive changes…'),command=self.review_changes).pack(side='left')
        actions=ttk.Menubutton(bar,text=tr('Draft actions'));actions.pack(side='left')
        menu=tk.Menu(actions,tearoff=False);actions.configure(menu=menu)
        for side in (0,1):
            menu.add_command(label=tr('Delete selected from LEFT draft' if side==0 else 'Delete selected from RIGHT draft'),command=lambda s=side:self.delete_selected(s))
            menu.add_command(label=tr('Undo last LEFT deletion' if side==0 else 'Undo last RIGHT deletion'),command=lambda s=side:self.undo_delete(s))
        ttk.Button(bar,text=tr('Cancel'),command=self.cancel_scan).pack(side='left')
        self.status=ttk.Label(bar,text=tr('Preparing isolated archive drafts…'),width=1);self.status.pack(side='left',fill='x',expand=True)
        self.bind('<Destroy>',self.destroyed,add='+')
        self.run('open',self.prepare)

    def prepare(self):
        roots=[];sessions=[None,None]
        try:
            for i,p in enumerate(self.paths):
                if p.suffix.lower() in ('.zip','.7z') and p.is_file():
                    sessions[i]=ArchiveReviewSession(p,self.cancel_event);roots.append(sessions[i].root)
                else:roots.append(p)
            return roots,sessions
        except Exception:
            for s in sessions:
                if s:s.cleanup()
            raise

    def run(self,action,callback):
        if self.busy:return
        self.cancel_event.clear()
        self.busy=True;self.status.configure(text=tr('Working… original archives unchanged until verified save'))
        def worker():
            try:result=callback();error=None
            except Exception as exc:result=None;error=str(exc)
            self.results.put((action,result,error))
        threading.Thread(target=worker,daemon=True).start();self._job=self.after(50,self.poll)

    def poll(self):
        self._job=None
        try:action,result,error=self.results.get_nowait()
        except queue.Empty:self._job=self.after(50,self.poll);return
        self.busy=False
        if error:self.status.configure(text=error);return
        if action=='open':
            roots,self.sessions=result
            self.inner=self.folder_factory(self,*roots,self.file_factory,self.sync_executor,
                left_label=self.paths[0],right_label=self.paths[1],left_read_only=False,right_read_only=False,**self.options)
            self.inner.content_var.set(True);self.inner.start_scan()
            self.inner.pack(fill='both',expand=True)
            if self.palette:self.apply_color_scheme(self.palette)
            self.status.configure(text=tr('Archive sides are drafts · Review archive changes to save · local folders use normal confirmed sync'))
        elif action=='review':self.show_review(result)
        else:self.status.configure(text=tr('Archive saved; backup: ')+str(result))

    def review_changes(self):
        if self.busy or not self.inner:return
        if any(getattr(d['detail'],'busy',False) or getattr(d['detail'],'_editors',None) or
               (hasattr(d['detail'],'texts') and any(t!=doc.text for t,doc in zip(d['detail'].texts,d['detail'].documents)))
               for d in self.inner.nested_details.values()):
            self.status.configure(text=tr('Save or discard nested file drafts before reviewing the archive'));return
        self.run('review',lambda:[(i,s.changes(),archive_manifest(s.root,self.cancel_event)) for i,s in enumerate(self.sessions) if s])

    def delete_selected(self,side):
        if self.busy or not self.inner or not self.sessions[side]:return
        if self.inner.nested_details:
            self.status.configure(text=tr('Close nested file tabs before deleting archive members'));return
        session=self.sessions[side];names=[]
        for iid in self.inner._selected_items():
            path=self.inner.item_paths.get(iid,(None,None))[side]
            if path:names.append(path.relative_to(session.root).as_posix())
        if not names:return
        if not messagebox.askyesno(tr('Delete from draft'),tr('Only the archive draft changes; review is required before saving.')+'\n'+'\n'.join(names[:15]),default='no',parent=self):return
        try:session.delete_from_draft(names);self.inner.start_scan()
        except OSError as exc:messagebox.showerror(tr('Archive draft'),str(exc),parent=self)

    def undo_delete(self,side):
        if self.busy or not self.inner or not self.sessions[side]:return
        try:self.sessions[side].undo_delete();self.inner.start_scan()
        except OSError as exc:messagebox.showerror(tr('Archive draft'),str(exc),parent=self)

    def show_review(self,items):
        changes=[(i,rows,manifest) for i,rows,manifest in items if rows]
        if not changes:self.status.configure(text=tr('No archive changes'));return
        # Each side is a separate transaction: never claim a two-file atomic save.
        dialog=tk.Toplevel(self);dialog.title(tr('Review archive changes'));dialog.geometry('950x580')
        ttk.Label(dialog,text=tr('Select one archive to save. Adds, replacements and explicit deletions are listed below.')).pack(fill='x')
        tabs=ttk.Notebook(dialog);tabs.pack(fill='both',expand=True)
        for i,rows,manifest in changes:
            frame=ttk.Frame(tabs);tabs.add(frame,text=('L · ' if i==0 else 'R · ')+self.paths[i].name)
            tree=ttk.Treeview(frame,columns=('action','member'),show='headings');tree.heading('action',text=tr('Action'));tree.heading('member',text=tr('Member'))
            tree.column('action',width=100,stretch=False);tree.column('member',width=600);tree.pack(fill='both',expand=True)
            for name,action in rows:tree.insert('','end',values=(tr(action),name))
            def save(side=i,approved=manifest):
                if not messagebox.askyesno(tr('Save'),tr('Write exactly these changes? A backup will be retained.')+'\n'+str(self.paths[side]),parent=dialog):return
                dialog.destroy()
                def commit():
                    if archive_manifest(self.sessions[side].root,self.cancel_event)!=approved:raise OSError('Draft changed after review; review again before saving')
                    return self.sessions[side].commit(approved)
                self.run('save',commit)
            ttk.Button(frame,text=tr('Save this archive'),command=save).pack(side='right')
        ttk.Button(dialog,text=tr('Cancel'),command=dialog.destroy).pack(side='right')

    def cancel_scan(self):
        if self.busy:self.cancel_event.set();self.status.configure(text=tr('Cancelling…'));return True
        if self.inner:return self.inner.cancel_scan()
        return False

    def export_report(self):
        if self.inner:self.inner.export_report()

    def next(self):
        if self.inner:self.inner.next()
    def previous(self):
        if self.inner:self.inner.previous()
    def focus_search(self):
        if self.inner:return self.inner.focus_search()
    def find_next(self):
        if self.inner:return self.inner.find_next()
    def find_previous(self):
        if self.inner:return self.inner.find_previous()
    def close_nested_detail(self):
        return bool(self.inner and self.inner.close_nested_detail())
    def apply_scale(self,scale):
        if self.inner:self.inner.apply_scale(scale)
    def apply_color_scheme(self,palette):
        self.palette=palette
        if self.inner:self.inner.apply_color_scheme(palette)

    def confirm_close(self):
        if self.busy:self.cancel_scan();return False
        if self.inner and not self.inner.confirm_close():return False
        if any(self.sessions) and not messagebox.askyesno(tr('Close comparison'),tr('Close archive drafts? Any changes not saved to the archives will be discarded.'),parent=self):return False
        return True

    def destroyed(self,event):
        if event.widget is not self:return
        self.closed=True;self.cancel_event.set()
        if self._job is not None:self.after_cancel(self._job)
        for session in self.sessions:
            if session:session.cleanup()
