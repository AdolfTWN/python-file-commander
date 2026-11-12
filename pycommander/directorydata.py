"""Per-listing metadata snapshots: one stat per item, no persistent disk cache."""
from dataclasses import dataclass
from pathlib import Path
import stat as statlib
from collections import OrderedDict
import threading
import os

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


def _listing_stat(path, entry=None):
    # A Windows DirEntry reuses FindFirst/NextFile metadata for ordinary
    # entries. Reparse points use Path.stat explicitly below. Never retain
    # DirEntry objects across listings: the next audit must enumerate anew.
    return path.stat() if entry is None else entry.stat()


def listing_items(paths, *, latency=None, cancelled=None):
    rows=[]
    measure = latency.measure if latency is not None else None
    for path in paths:
        if cancelled is not None and cancelled.is_set():
            raise DirectoryReadCancelled()
        try:
            metadata = _listing_stat(path) if measure is None else measure('Read file metadata', _listing_stat, path, item=path)
        except OSError:metadata=None
        rows.append(DirectoryItem(path,metadata))
    return tuple(rows)


def directory_items(folder,show_hidden=False,show_system=False,reveal=None, *, latency=None, cancelled=None):
    if os.name == 'nt':
        return _windows_directory_items(folder, show_hidden, show_system, reveal,
                                        latency=latency, cancelled=cancelled)
    def visible(path):
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


def _windows_directory_items(folder, hidden, system, reveal, *, latency=None, cancelled=None):
    rows=[]
    def measured(label, callback, *args, **kwargs):
        return (callback(*args) if latency is None else
                latency.measure(label, callback, *args, **kwargs))
    # Enumeration already carries link attributes and ordinary-file metadata.
    # Avoid reopening every file twice (GetFileAttributesW + Path.stat).
    with os.scandir(folder) as entries:
        while True:
            if cancelled is not None and cancelled.is_set():
                raise DirectoryReadCancelled()
            try:entry=measured('Enumerate directory',next,entries)
            except StopIteration:break
            path=folder/entry.name
            if path != reveal and not hidden and entry.name.startswith('.'):
                continue
            try:
                info=measured('Read enumerated attributes',lambda:entry.stat(follow_symlinks=False),item=path)
                attrs=info.st_file_attributes
            except OSError:
                # Unknown attributes retain visibility and use a path query.
                attrs=None
            if path != reveal and attrs is not None:
                if (not hidden and attrs & 2) or (not system and attrs & 4):
                    continue
            # Native Windows validation found junction timestamp differences
            # in DirEntry.stat. Preserve the original target/path semantics for
            # ALL reparse tags, including cloud placeholders and junctions.
            cached=entry if attrs is not None and not attrs & 0x400 else None
            try:metadata=measured('Read file metadata',_listing_stat,path,cached,item=path)
            except OSError:metadata=None
            rows.append(DirectoryItem(path,metadata))
    return tuple(rows)


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
