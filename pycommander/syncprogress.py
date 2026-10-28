"""File-only comparison copy plans, with UI-thread conflicts and worker I/O."""
import queue
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from .fileops import OperationFailure, OperationResult, copy_items
from .workflowdata import compare_path_blocked
from .workflows import style_workflow_controls
from .i18n import tr
from .transferprogress import resolve_progress_conflict, merge_progress_conflicts


class SyncProgress(tk.Toplevel):
    def __init__(self, master, plans, resolver, continue_errors):
        super().__init__(master)
        self.title(tr('Safe Sync')); self.transient(master); self.resizable(False, False)
        self.cancelled = threading.Event(); self.messages = queue.Queue(); self.result = OperationResult()
        self.plans = list(plans); self.resolver = resolver;self.conflict_failures=[]
        self.protocol('WM_DELETE_WINDOW', self.cancel)
        self.bind('<Escape>', lambda e: self.cancel()); self.bind('<KeyPress>', lambda e: 'break')
        area = ttk.Frame(self,padding=12);area.pack(fill='both',expand=True)
        self.label = ttk.Label(area,text=tr('Preparing…'),width=46,wraplength=460)
        self.label.pack(fill='x')
        self.progress = ttk.Progressbar(area, maximum=max(1,len(plans)), length=460)
        self.progress.pack(fill='x',pady=10)
        self.detail = ttk.Label(area,text=tr('Cancel stops after the current file.'),wraplength=460)
        self.detail.pack(fill='x')
        self.cancel_button = ttk.Button(area,text=tr('Cancel'),command=self.cancel)
        self.cancel_button.pack(anchor='e',pady=(10,0))
        style_workflow_controls(self)
        self.update_idletasks()
        self.geometry(f'+{max(0,master.winfo_rootx()+80)}+{max(0,master.winfo_rooty()+90)}')
        self.grab_set()

        plans,cancelled,messages=self.plans,self.cancelled,self.messages
        def conflict(source, target):
            reply = queue.Queue(maxsize=1)
            messages.put(('conflict',source,target,reply))
            while True:
                try: return reply.get(timeout=.1)
                except queue.Empty:
                    if cancelled.is_set(): return 'cancel'

        def worker():
            result = OperationResult()
            try:
                for index,(source,target) in enumerate(plans):
                    if cancelled.is_set():
                        result.skipped.extend(p for p,_ in plans[index:]);break
                    messages.put(('progress',index,source.name))
                    try:
                        # Never execute an out-of-date plan as a recursive copy
                        # or traverse a replacement link in its destination.
                        if compare_path_blocked(source) or not source.is_file():
                            raise OSError('The scanned source is no longer an ordinary file.')
                        if source.name != target.name:
                            raise OSError('Source and target spelling differ. Rename explicitly before copying.')
                        for parent in [target]+list(target.parents):
                            if (parent.exists() or parent.is_symlink()) and compare_path_blocked(parent):
                                raise OSError('Linked/cloud destinations are not supported by this copy plan.')
                        partial = copy_items([source],target.parent,conflict,continue_errors)
                    except (OSError, ValueError) as exc:
                        partial = OperationResult(failures=[OperationFailure(source,target,str(exc))])
                    result.completed.extend(partial.completed); result.skipped.extend(partial.skipped)
                    result.failures.extend(partial.failures)
                    messages.put(('progress',index+1,source.name))
                    if partial.failures and not continue_errors:
                        result.skipped.extend(p for p,_ in plans[index+1:]);break
            except Exception as exc:
                result.failures.append(OperationFailure(Path('.'),None,str(exc)))
            messages.put(('done',result))
        self.worker = threading.Thread(target=worker,daemon=True,name='PFC-Compare-Copy')
        self.worker.start();self.after(40,self.poll)

    def cancel(self):
        self.cancelled.set();self.cancel_button.state(['disabled'])
        self.detail.configure(text=tr('Stopping after the current file…'))

    def poll(self):
        deadline=time.monotonic()+.01
        while time.monotonic()<deadline:
            try: item=self.messages.get_nowait()
            except queue.Empty: break
            if item[0]=='conflict':
                _,source,target,reply=item
                reply.put(resolve_progress_conflict(self,source,target))
                self.grab_set()
            elif item[0]=='progress':
                self.progress.configure(value=item[1])
                self.label.configure(text=f'{item[1]} / {len(self.plans)} · {item[2][:70]}')
            elif item[0]=='done':
                self.result=merge_progress_conflicts(item[1],self.conflict_failures);self.grab_release();self.destroy();return
        self.after(40,self.poll)
