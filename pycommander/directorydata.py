"""Per-listing metadata snapshots: one stat per item, no persistent disk cache."""
from dataclasses import dataclass
from pathlib import Path
import stat as statlib
from collections import OrderedDict
import threading
import os
import ctypes

from .fileops import is_hidden, is_system


@dataclass(frozen=True)
class DirectoryItem:
    path: Path
    metadata: object

    @property
    def is_dir(self):
        return self.metadata is not None and statlib.S_ISDIR(self.metadata.st_mode)


class DirectoryReadCancelled(Exception):
    pass


def listing_items(paths, *, latency=None, cancelled=None):
    rows=[]
    measure = latency.measure if latency is not None else None
    for path in paths:
        if cancelled is not None and cancelled.is_set():
            raise DirectoryReadCancelled()
        try:
            metadata = path.stat() if measure is None else measure('Read file metadata', path.stat, item=path)
        except OSError:metadata=None
        rows.append(DirectoryItem(path,metadata))
    return tuple(rows)


def directory_items(folder,show_hidden=False,show_system=False,reveal=None, *, latency=None, cancelled=None):
    # Preserve GetFileAttributesW visibility semantics for Windows links rather
    # than substituting the followed target's stat attributes.
    def visible(path):
        if os.name == 'nt':
            if not show_hidden and path.name.startswith('.'):
                return False
            # Inspect the link itself (not followed stat attributes), once.
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            unknown = attrs in (-1, 0xffffffff)
            return unknown or ((show_hidden or not attrs & 2) and (show_system or not attrs & 4))
        return (show_hidden or not is_hidden(path)) and (show_system or not is_system(path))
    if show_hidden and show_system:
        return listing_items(folder.iterdir(), latency=latency, cancelled=cancelled)
    if latency is not None:
        measure = latency.measure
        def checked(path):
            return measure('Read visibility attributes', visible, path, item=path)
    else:
        checked = visible
    return listing_items((path for path in folder.iterdir() if path==reveal or checked(path)),
                         latency=latency, cancelled=cancelled)


class DirectoryRead:
    def __init__(self, folder, hidden, system, reveal, resolve, monitor):
        self.arguments = (folder, hidden, system, reveal)
        self.resolve, self.monitor = resolve, monitor
        self.cancelled, self.done = threading.Event(), threading.Event()
        self.result = self.error = None
        self.finished = None

    def cancel(self):
        self.cancelled.set()
        self.done.set()


class DirectoryReads:
    """Two bounded, data-only workers; replacing a pending key cancels it.

    OS metadata calls cannot be forcibly interrupted; cancelled calls stop at
    their next boundary. No worker owns a widget, Tk variable or UI callback.
    """
    def __init__(self):
        self._condition = threading.Condition()
        self._pending = OrderedDict()
        self._running = set()
        self._closed = False
        self._threads = []

    def submit(self, key, folder, hidden, system, reveal=None, *, resolve=False, monitor=None):
        job = DirectoryRead(folder, hidden, system, reveal, resolve, monitor)
        with self._condition:
            if self._closed:
                raise DirectoryReadCancelled()
            previous = self._pending.pop(key, None)
            if previous is not None:
                previous.cancel()
            if len(self._pending) >= 64:
                raise OSError('Folder reader queue is busy.')
            self._pending[key] = job
            if not self._threads:
                for _ in range(2):
                    worker = threading.Thread(target=self._work, name='PFC-directory-reader', daemon=True)
                    self._threads.append(worker)
                    worker.start()
            self._condition.notify()
        return job

    def _work(self):
        import time
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or self._pending)
                if self._closed:
                    return
                _, job = self._pending.popitem(last=False)
                self._running.add(job)
            try:
                def read():
                    folder, hidden, system, reveal = job.arguments
                    if job.cancelled.is_set():
                        raise DirectoryReadCancelled()
                    if job.resolve:
                        folder = folder.expanduser().resolve()
                        if not folder.is_dir():
                            raise NotADirectoryError(folder)
                    rows = directory_items(folder, hidden, system, reveal,
                                           latency=job.monitor, cancelled=job.cancelled)
                    if job.monitor is not None:
                        job.monitor.rows(len(rows))
                    return folder, rows, listing_signature(rows)
                result = (read() if job.monitor is None else
                          job.monitor.action('Read folder in background', read))
                if not job.cancelled.is_set():
                    job.result = result
            except DirectoryReadCancelled:
                job.cancelled.set()
            except OSError as exc:
                # Do not transfer worker traceback frames/locals to Tk.
                job.error = exc.with_traceback(None)
            except Exception as exc:
                # An unexpected reader failure must wake its UI consumer too.
                job.error = OSError('Folder reader failed: '+type(exc).__name__)
            finally:
                job.finished = time.monotonic()
                job.done.set()
                with self._condition:
                    self._running.discard(job)

    def close(self):
        with self._condition:
            self._closed = True
            for job in (*self._pending.values(), *self._running):
                job.cancel()
            self._pending.clear()
            self._condition.notify_all()


def listing_signature(rows):
    # Results may span folders and share a basename. Keep their full identity,
    # and never compare unavailable None metadata with another row's numbers.
    records=((str(row.path),row.metadata.st_size,row.metadata.st_mtime_ns,row.metadata.st_mode)
             if row.metadata is not None else (str(row.path),None,None,None) for row in rows)
    return tuple(sorted(records,key=lambda record:record[0]))


def ordered_listing(rows,column='name',reverse=False,mix=True):
    def key(row):
        if column=='name':return row.path.name.lower()
        if column=='ext':return row.path.suffix.lower()
        # Unreadable entries still participate in the signature, but never mix
        # a string key into an otherwise numeric sort.
        value=(row.metadata.st_size if column=='size' else row.metadata.st_mtime) if row.metadata is not None else 0
        return value
    rows=sorted(rows,key=key,reverse=reverse)
    if not mix:rows.sort(key=lambda row:not row.is_dir)
    return rows
