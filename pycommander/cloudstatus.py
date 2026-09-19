"""Non-hydrating, best-effort Windows OneDrive metadata and bounded async cache.

Only registered OneDrive roots are queried. FASTPROPERTIESONLY deliberately
omits slow provider values; missing metadata is unknown, never 'synced'.
"""
import ctypes
import os
from pathlib import Path
import queue
import threading
import time
import uuid


CLOUD_LABELS = {'online': 'Online only', 'available': 'Locally available',
                'pinned': 'Always available offline', 'syncing': 'Syncing / pending',
                'error': 'Sync error', 'paused': 'Sync paused', 'warning': 'Sync warning'}
CLOUD_DETAILS = {
    'online': 'Blue cloud: opening requires a download and network access.',
    'available': 'Outlined check: usable offline now; storage cleanup may remove the local copy.',
    'pinned': 'Filled check: marked to stay on this device for offline use.',
    'syncing': 'Pending changes are not yet confirmed synchronized.',
    'error': 'Check OneDrive for the error and recovery actions.',
    'paused': 'Check OneDrive to resume synchronization.',
    'warning': 'Check OneDrive for more information.',
}


def cloud_state(attributes, transfer=None, placeholder=None):
    if attributes is None or attributes == 0xffffffff:
        return None
    if transfer is not None:
        if transfer & 0x10:
            return 'error'
        if transfer & 8:
            return 'paused'
        if transfer & (0x80 | 0x100 | 0x200):
            return 'warning'
        if transfer & (1 | 2 | 4 | 0x20 | 0x40):
            return 'syncing'
    if attributes & (0x1000 | 0x40000 | 0x400000):
        return 'online'
    # PINNED is intent; require a complete local primary stream as evidence.
    if placeholder is not None and placeholder & 8 and placeholder & 2:
        return 'pinned' if attributes & 0x80000 else 'available'
    return None


class _CloudGUID(ctypes.Structure):
    _fields_ = [('data', ctypes.c_ubyte * 16)]

    @classmethod
    def parse(cls, text):
        return cls((ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(text).bytes_le))


class _CloudPropertyKey(ctypes.Structure):
    _fields_ = [('fmtid', _CloudGUID), ('pid', ctypes.c_uint32)]


class _CloudVariant(ctypes.Structure):
    # PROPVARIANT header followed by the largest pointer-sized union (16B x64).
    _fields_ = [('vt', ctypes.c_uint16), ('reserved', ctypes.c_uint16 * 3),
                ('value', ctypes.c_uint64 * 2)]


def read_cloud_status(path):
    """Called only by the metadata worker; never opens file contents."""
    if os.name != 'nt':
        return None
    kernel = ctypes.windll.kernel32
    kernel.GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
    kernel.GetFileAttributesW.restype = ctypes.c_uint32
    attributes = kernel.GetFileAttributesW(str(path))
    if attributes == 0xffffffff:
        return None
    store = ctypes.c_void_p()
    shell = ctypes.windll.shell32
    shell.SHGetPropertyStoreFromParsingName.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.POINTER(_CloudGUID), ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetPropertyStoreFromParsingName.restype = ctypes.c_long
    iid = _CloudGUID.parse('886d8eeb-8cf2-4446-8d02-cdba1dbdcf99')
    hr = shell.SHGetPropertyStoreFromParsingName(str(path), None, 0x48, ctypes.byref(iid), ctypes.byref(store))
    values = [None, None]
    if hr >= 0 and store:
        vtable = ctypes.cast(store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        get_value = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
            ctypes.POINTER(_CloudPropertyKey), ctypes.POINTER(_CloudVariant))(vtable[5])
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])
        clear = ctypes.windll.ole32.PropVariantClear
        clear.argtypes = [ctypes.POINTER(_CloudVariant)]
        try:
            for index, (guid, pid) in enumerate((
                ('fceff153-e839-4cf3-a9e7-ea22832094b8', 103),
                ('b2f9b9d6-fec4-4dd5-94d7-8957488c807b', 2))):
                key = _CloudPropertyKey(_CloudGUID.parse(guid), pid)
                value = _CloudVariant()
                try:
                    if get_value(store, ctypes.byref(key), ctypes.byref(value)) >= 0 and value.vt == 19:
                        values[index] = int(value.value[0] & 0xffffffff)
                finally:
                    clear(ctypes.byref(value))
        finally:
            release(store)
    return cloud_state(attributes, *values)


class CloudStatusCache:
    """One daemon worker, at most 128 visible items/batch; no Tk calls off-thread."""
    def __init__(self, roots, reader=read_cloud_status):
        self.roots = tuple(Path(p) for p in roots)
        self.reader = reader
        self.values = {}
        self.results = queue.Queue(maxsize=1)
        self.busy = False
        self.due = 0
        self.cursor = 0

    def eligible(self, path):
        path = Path(path)
        return any(path == root or root in path.parents for root in self.roots)

    def get(self, path):
        return self.values.get(str(path))

    def poll(self, paths):
        changed = False
        try:
            updates = self.results.get_nowait()
            self.busy = False
            changed = any(self.values.get(key) != value for key, value in updates.items())
            if len(self.values) > 512:
                self.values.clear()
                changed = True
            self.values.update(updates)
        except queue.Empty:
            pass
        now = time.monotonic()
        if self.busy or now < self.due:
            return changed
        candidates = list(dict.fromkeys(str(p) for p in paths if self.eligible(p)))
        start = self.cursor % len(candidates) if candidates else 0
        selected = (candidates[start:] + candidates[:start])[:128]
        self.cursor = start+len(selected)
        self.due = now+2
        if not selected:
            return changed
        self.busy = True
        def work():
            initialized = False
            updates = {}
            try:
                if os.name == 'nt':
                    initialized = ctypes.windll.ole32.CoInitializeEx(None, 2) >= 0
                for path in selected:
                    try:
                        updates[path] = self.reader(path)
                    except (OSError, ValueError, AttributeError):
                        updates[path] = None
            finally:
                if initialized:
                    ctypes.windll.ole32.CoUninitialize()
                self.results.put(updates)
        threading.Thread(target=work, name='PFC-OneDrive-metadata', daemon=True).start()
        return changed
