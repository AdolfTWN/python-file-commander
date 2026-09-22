"""One isolated, persistent Markdown worker; no Tk calls in its reader thread."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time


def limit_markdown_worker_memory():
    """Apply a 512 MiB OS limit to this private worker, never the GUI process.

    If the platform/policy cannot enforce it, the caller uses bounded plain
    source instead of the richer renderer. Not a general-purpose OS sandbox.
    """
    limit=512*1024*1024
    try:
        if os.name!='nt':
            import resource
            resource.setrlimit(resource.RLIMIT_AS,(limit,limit))
            return True
        import ctypes
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_=[('ProcessTime',ctypes.c_int64),('JobTime',ctypes.c_int64),
                ('Flags',wintypes.DWORD),('MinWorking',ctypes.c_size_t),('MaxWorking',ctypes.c_size_t),
                ('Active',wintypes.DWORD),('Affinity',ctypes.c_size_t),
                ('Priority',wintypes.DWORD),('Scheduling',wintypes.DWORD)]
        class Extended(ctypes.Structure):
            _fields_=[('Basic',Basic),('IO',ctypes.c_uint64*6),('ProcessMemory',ctypes.c_size_t),
                ('JobMemory',ctypes.c_size_t),('PeakProcess',ctypes.c_size_t),('PeakJob',ctypes.c_size_t)]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype=wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
        kernel.GetCurrentProcess.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        job=kernel.CreateJobObjectW(None,None)
        if not job:return False
        info=Extended();info.Basic.Flags=0x100;info.ProcessMemory=limit
        if not kernel.SetInformationJobObject(job,9,ctypes.byref(info),ctypes.sizeof(info)) or not kernel.AssignProcessToJobObject(job,kernel.GetCurrentProcess()):
            kernel.CloseHandle(job);return False
        # Retain the job handle until worker exit, when Windows closes it.
        return True
    except (OSError,ValueError,ImportError):
        return False


class MarkdownJobs:
    def __init__(self, module_file, packaged):
        self.module_file=module_file;self.packaged=packaged
        self.process=None;self.results=queue.Queue();self.pending=None
        self.serial=0;self.started=0;self.retiring=[]
        self.outgoing=None

    def _start(self):
        if self.packaged:
            code='from pycommander.preview import markdown_worker_main; markdown_worker_main()'
            cwd=str(Path(self.module_file).parent.parent)
            args=[sys.executable,'-c',code]
        else:
            code="import runpy,sys; n=runpy.run_path(sys.argv[1],run_name='pfc_md_worker'); n['markdown_worker_main']()"
            cwd=str(Path(self.module_file).parent)
            args=[sys.executable,'-c',code,str(self.module_file)]
        self.process=subprocess.Popen(args,cwd=cwd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,creationflags=0x08000000 if os.name=='nt' else 0)
        process=self.process;results=self.results
        outgoing=queue.Queue(maxsize=1);self.outgoing=outgoing
        def send():
            try:
                while True:
                    request=outgoing.get()
                    if request is None or process.poll() is not None: break
                    process.stdin.write((json.dumps(request)+'\n').encode('utf-8'))
                    process.stdin.flush()
            except (OSError,ValueError):
                results.put((process,{'error':'Preview worker could not accept the request'}))
            finally:
                try:
                    process.stdin.close()
                except (OSError, ValueError):
                    # A cancelled/crashed worker may close its pipe before the
                    # buffered writer flushes. Cleanup must not raise in a thread.
                    pass
        def receive():
            try:
                while True:
                    raw=process.stdout.readline(64*1024*1024)
                    if not raw: break
                    if not raw.endswith(b'\n'): raise ValueError('Worker result too large')
                    results.put((process,json.loads(raw)))
            except (OSError,ValueError): pass
            finally:
                results.put((process,{'error':'Preview worker stopped'}))
                process.stdout.close()
                if process.poll() is None: process.kill()
                try: outgoing.put_nowait(None)
                except queue.Full: pass
                process.wait()
        threading.Thread(target=send,name='PFC-Markdown-requests',daemon=True).start()
        threading.Thread(target=receive,name='PFC-Markdown-results',daemon=True).start()

    def submit(self, request):
        self.reap()
        if self.pending or self.retiring: return False
        if self.process is None or self.process.poll() is not None: self._start()
        self.serial+=1;self.pending=self.serial;self.started=time.monotonic()
        request=dict(request,id=self.serial)
        self.outgoing.put_nowait(request)
        return True

    def poll(self):
        self.reap()
        while True:
            try: process,result=self.results.get_nowait()
            except queue.Empty: return None
            if process is self.process and self.pending and result.get('id',self.pending)==self.pending:
                self.pending=None
                return result

    def cancel(self):
        self.pending=None
        if self.process is not None:
            process=self.process;self.process=None
            if process.poll() is None: process.kill()
            try: self.outgoing.put_nowait(None)
            except queue.Full: pass
            self.retiring.append(process)
        self.reap()

    def reap(self):
        self.retiring[:]=[p for p in self.retiring if p.poll() is None]

    def close(self):
        self.cancel()
