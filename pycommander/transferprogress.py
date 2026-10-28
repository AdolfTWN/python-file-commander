"""General copy/move I/O off Tk, preserving conflict and partial-result semantics."""
import queue
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, font as tkfont

from .fileops import OperationFailure, OperationResult
from .i18n import tr
from .windowplacement import popup_work_area, position_popup_in_work_area


def resolve_progress_conflict(owner,source,target):
    """UI-thread reply; resolver faults must not masquerade as user Cancel."""
    try:action='cancel' if owner.cancelled.is_set() else owner.resolver(source,target)
    except Exception as exc:
        log=getattr(owner._root(),'debug_log',None)
        if log is not None:log.exception('operation.conflict.failed',exc)
        owner.conflict_failures.append(OperationFailure(source,target,tr('Conflict selection failed. No changes were made to this item.')))
        action='cancel'
    if action=='cancel':owner.cancelled.set()
    return action


def merge_progress_conflicts(result,failures):
    if failures:
        failed={failure.source for failure in failures}
        result.skipped=[path for path in result.skipped if path not in failed]
        result.failures.extend(failures)
    return result


class TransferProgress(tk.Toplevel):
    """Cancel at an item boundary; never pretend to interrupt a filesystem write.

    The worker never reads a Tk variable or calls Tk. Conflict replies cross a
    queue and are resolved by the Tk thread, including the existing Apply All.
    The caller may wait_window without blocking input, repaint or other timers.
    """
    def __init__(self,master,verb,operation,items,destination,resolver,continue_errors):
        super().__init__(master);self.withdraw();self.transient(master.winfo_toplevel())
        self.title(tr(verb));self.result=OperationResult()
        self.items=tuple(items);self.destination=Path(destination)
        self.previous_grab=master.grab_current();self.previous_focus=master.focus_get()
        self.cancelled=threading.Event();self.messages=queue.Queue();self.resolver=resolver
        self.conflict_failures=[];log=getattr(master._root(),'debug_log',None)
        self.started=time.monotonic();self._poll_job=None;self._finished=False
        self.done_count=0;self.current_name='';self.verb=verb
        area=ttk.Frame(self,padding=12);area.pack(fill='both',expand=True)
        self.status=ttk.Label(area,text=tr('Preparing…'),font='TkHeadingFont');self.status.pack(fill='x')
        self.activity=ttk.Progressbar(area,mode='indeterminate');self.activity.pack(fill='x',pady=8)
        self.item_label=ttk.Label(area,text='',wraplength=520);self.item_label.pack(fill='x')
        target=ttk.Frame(area);target.pack(fill='x',pady=(6,0))
        ttk.Label(target,text=tr('Destination')+':').pack(side='left',padx=(0,6))
        self.target_var=tk.StringVar(self,value=str(self.destination))
        self.target_entry=ttk.Entry(target,textvariable=self.target_var,state='readonly',font='TkDefaultFont')
        self.target_entry.pack(side='left',fill='x',expand=True)
        self.detail=ttk.Label(area,text=tr('Cancel stops after the current item, including its contents.'),wraplength=520)
        self.detail.pack(fill='x',pady=8)
        self.cancel_button=ttk.Button(area,text=tr('Cancel'),command=self.cancel)
        self.cancel_button.pack(anchor='e')
        self.bind('<KeyPress>',lambda e:'break');self.bind('<Escape>',lambda e:self.cancel())
        self.protocol('WM_DELETE_WINDOW',self.cancel)
        self.bind('<Configure>',self._wrap)
        work_area=popup_work_area(master)
        font=tkfont.nametofont('TkDefaultFont',root=self)
        width=min(round(560*max(1,font.metrics('linespace')/20)),work_area[2]-work_area[0]-48)
        self.geometry(f'{width}x{min(work_area[3]-work_area[1]-64,max(270,font.metrics("linespace")*10+80))}')
        self.minsize(min(width,400),min(230,work_area[3]-work_area[1]-64))
        self.deiconify();position_popup_in_work_area(self,master,work_area)
        self.grab_set();self.cancel_button.focus_force();self.activity.start(20)

        items,destination=self.items,self.destination
        cancelled,messages=self.cancelled,self.messages
        def conflict(source,target):
            reply=queue.Queue(maxsize=1)
            messages.put(('conflict',source,target,reply))
            while not cancelled.is_set():
                try:return reply.get(timeout=.1)
                except queue.Empty:pass
            return 'cancel'

        def worker():
            result=OperationResult();index=-1;source=Path('.')
            try:
                for index,source in enumerate(items):
                    if cancelled.is_set():
                        result.skipped.extend(items[index:]);break
                    messages.put(('progress',index,source.name))
                    try:
                        partial=operation([source],destination,conflict,continue_errors)
                        if not isinstance(partial,OperationResult):raise TypeError('Invalid file operation result.')
                    except Exception as exc:
                        if log is not None:log.exception('transfer.worker.failed',exc)
                        partial=OperationResult(failures=[OperationFailure(source,destination/source.name,str(exc))])
                    result.completed.extend(partial.completed);result.skipped.extend(partial.skipped)
                    result.failures.extend(partial.failures)
                    messages.put(('progress',index+1,source.name))
                    if (partial.failures and not continue_errors) or cancelled.is_set():
                        result.skipped.extend(items[index+1:]);break
            except BaseException as exc:
                # Even an unexpected backend/bookkeeping fault must publish a
                # terminal result, never strand a modal window waiting forever.
                if log is not None:log.exception('transfer.worker.failed',exc)
                result.failures.append(OperationFailure(source,None,str(exc)))
                result.skipped.extend(items[index+1:])
            finally:messages.put(('done',result))
        self.worker=threading.Thread(target=worker,name='PFC-Transfer',daemon=True)
        self.worker.start();self._poll_job=self.after(30,self.poll)

    def _wrap(self,event):
        if event.widget is self:
            for label in (self.item_label,self.detail,self.status):label.configure(wraplength=max(100,event.width-28))

    def cancel(self):
        self.cancelled.set();self.cancel_button.state(['disabled'])
        self.detail.configure(text=tr('Stopping after the current item…'))

    def destroy(self):
        # A destroyed modal can remain in a callback/exception cycle until the
        # next worker triggers GC. Release our sole Tk variable on its UI thread
        # while the interpreter is alive, not during that later collection.
        self.target_var=None
        super().destroy()

    def poll(self):
        self._poll_job=None
        deadline=time.monotonic()+.01
        while time.monotonic()<deadline:
            try:item=self.messages.get_nowait()
            except queue.Empty:break
            if item[0]=='conflict':
                _,source,target,reply=item
                reply.put(resolve_progress_conflict(self,source,target));self.grab_set()
            elif item[0]=='progress':self.done_count,self.current_name=item[1:]
            elif item[0]=='done':
                self.result=merge_progress_conflicts(item[1],self.conflict_failures);self._finished=True;self.activity.stop()
                self.grab_release();self.destroy()
                try:
                    if self.previous_grab is not None and self.previous_grab.winfo_exists():self.previous_grab.grab_set()
                    if self.previous_focus is not None and self.previous_focus.winfo_exists():self.previous_focus.focus_set()
                except tk.TclError:pass
                return
        self.status.configure(text=tr('{completed} / {total} items · {seconds}s elapsed',
            completed=self.done_count,total=len(self.items),seconds=int(time.monotonic()-self.started)))
        self.item_label.configure(text=self.current_name)
        self._poll_job=self.after(30,self.poll)
