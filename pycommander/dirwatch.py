"""Event-driven directory change notifications with a portable fallback boundary."""

from __future__ import annotations

import ctypes
import os
import queue
import threading
import time
from ctypes import wintypes
from pathlib import Path


def directory_key(path: Path) -> str:
    """Return a stable key for matching Windows paths across panes and events."""
    return os.path.normcase(os.path.abspath(str(path)))


def is_local_watch_path(path: Path) -> bool:
    """Native change notifications are reserved for local filesystem paths."""
    return os.name == "nt" and not str(path).startswith("\\\\")


class _WindowsDirectoryWatcher:
    _FILE_LIST_DIRECTORY = 0x0001
    _SHARE_ALL = 0x00000001 | 0x00000002 | 0x00000004
    _OPEN_EXISTING = 3
    _BACKUP_SEMANTICS = 0x02000000
    _NOTIFY_FILTER = (0x00000001 | 0x00000002 | 0x00000004 |
                      0x00000008 | 0x00000010 | 0x00000020)

    def __init__(self, path: Path, events: queue.Queue) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32 = kernel32
        kernel32.CreateFileW.argtypes = (
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        )
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.ReadDirectoryChangesW.argtypes = (
            wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, wintypes.BOOL,
            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
            wintypes.LPVOID,
        )
        kernel32.ReadDirectoryChangesW.restype = wintypes.BOOL
        kernel32.CancelIoEx.argtypes = (wintypes.HANDLE, wintypes.LPVOID)
        kernel32.CancelIoEx.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        self.path = Path(path)
        self._events = events
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        handle = kernel32.CreateFileW(
            str(self.path), self._FILE_LIST_DIRECTORY, self._SHARE_ALL, None,
            self._OPEN_EXISTING, self._BACKUP_SEMANTICS, None,
        )
        if handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        self._handle = handle
        self._thread = threading.Thread(
            target=self._run, name=f"PFC-Watch-{self.path.name}", daemon=True)

    @property
    def alive(self) -> bool:
        return self._thread.is_alive() and not self._stopping.is_set()

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        buffer = ctypes.create_string_buffer(64 * 1024)
        returned = wintypes.DWORD()
        while not self._stopping.is_set():
            with self._lock:
                handle = self._handle
            if handle is None:
                break
            ok = self._kernel32.ReadDirectoryChangesW(
                handle, buffer, len(buffer), False, self._NOTIFY_FILTER,
                ctypes.byref(returned), None, None,
            )
            if not ok:
                break
            if returned.value:
                self._events.put(self.path)

    def stop(self) -> None:
        self._stopping.set()
        with self._lock:
            handle, self._handle = self._handle, None
        if handle is not None:
            self._kernel32.CancelIoEx(handle, None)
            self._kernel32.CloseHandle(handle)
        if self._thread.is_alive():
            self._thread.join(timeout=.2)


class DirectoryWatchManager:
    """Keep one native watcher per unique visible directory."""

    def __init__(self, watcher_factory=None, supported: bool | None = None) -> None:
        self.events: queue.Queue = queue.Queue()
        self.supported = os.name == "nt" if supported is None else supported
        self._factory = watcher_factory or _WindowsDirectoryWatcher
        self._watchers = {}
        self._retry_after = {}

    def sync(self, paths) -> set[str]:
        desired = {directory_key(path): Path(path) for path in paths}
        for key in list(self._watchers):
            watcher = self._watchers[key]
            if key not in desired or not watcher.alive:
                watcher.stop()
                del self._watchers[key]
                if key in desired:
                    self._retry_after[key] = time.monotonic() + 5.0
        if self.supported:
            now = time.monotonic()
            for key, path in desired.items():
                if key in self._watchers or now < self._retry_after.get(key, 0):
                    continue
                try:
                    watcher = self._factory(path, self.events)
                    watcher.start()
                    self._watchers[key] = watcher
                    self._retry_after.pop(key, None)
                except OSError:
                    self._retry_after[key] = now + 5.0
        return set(self._watchers)

    def drain(self) -> set[str]:
        changed = set()
        try:
            while True:
                changed.add(directory_key(self.events.get_nowait()))
        except queue.Empty:
            return changed

    def close(self) -> None:
        for watcher in list(self._watchers.values()):
            watcher.stop()
        self._watchers.clear()

