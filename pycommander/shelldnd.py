from __future__ import annotations

import ctypes
import os
import queue
import shutil
import tempfile
import threading
from pathlib import Path

from .clipboard import CF_HDROP, TYMED_HGLOBAL, data_object_has_format, extract_virtual_files_from_data_object, virtual_file_format_id, _get_medium, _release_medium


DROPEFFECT_NONE = 0
DROPEFFECT_COPY = 1
DROPEFFECT_MOVE = 2
WM_DROPFILES = 0x0233
GWL_WNDPROC = -4
UINT_MAX = 0xFFFFFFFF
VK_SHIFT = 0x10
MK_SHIFT = 0x0004
S_OK = 0
E_NOINTERFACE = -2147467262
COINIT_APARTMENTTHREADED = 0x2


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


IID_IDATAOBJECT = _GUID(
    0x0000010E, 0x0000, 0x0000,
    (ctypes.c_ubyte * 8)(0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46),
)
IID_IUNKNOWN = _GUID(
    0x00000000, 0x0000, 0x0000,
    (ctypes.c_ubyte * 8)(0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46),
)
IID_IDROPTARGET = _GUID(
    0x00000122, 0x0000, 0x0000,
    (ctypes.c_ubyte * 8)(0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46),
)


def _failed(status: int) -> bool:
    return status < 0


def _status_text(status: int) -> str:
    return f"0x{status & 0xFFFFFFFF:08X}"


def _release_interface(pointer: int) -> None:
    if not pointer:
        return
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[2])
    release(pointer)


def _marshal_data_object(data_object: int) -> int:
    """Marshal IDataObject so Office attachment download can leave the UI thread."""
    ole32 = ctypes.windll.ole32
    ole32.CoMarshalInterThreadInterfaceInStream.argtypes = [
        ctypes.POINTER(_GUID), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    ole32.CoMarshalInterThreadInterfaceInStream.restype = ctypes.c_long
    stream = ctypes.c_void_p()
    status = ole32.CoMarshalInterThreadInterfaceInStream(
        ctypes.byref(IID_IDATAOBJECT), ctypes.c_void_p(data_object), ctypes.byref(stream))
    if _failed(status) or not stream.value:
        raise OSError(f"Cannot prepare Office attachment transfer ({_status_text(status)}).")
    return stream.value


def _unmarshal_data_object(stream: int) -> int:
    ole32 = ctypes.windll.ole32
    ole32.CoGetInterfaceAndReleaseStream.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
    ole32.CoGetInterfaceAndReleaseStream.restype = ctypes.c_long
    data_object = ctypes.c_void_p()
    status = ole32.CoGetInterfaceAndReleaseStream(
        ctypes.c_void_p(stream), ctypes.byref(IID_IDATAOBJECT), ctypes.byref(data_object))
    if _failed(status) or not data_object.value:
        raise OSError(f"Cannot open Office attachment transfer ({_status_text(status)}).")
    return data_object.value


class ShellDataObject:
    """Shell IDataObject for direct children selected in one PFC panel."""

    def __init__(self, paths) -> None:
        if os.name != "nt":
            raise OSError("Windows Shell drag-and-drop is available only on Windows.")
        self.paths = [Path(value).resolve() for value in paths]
        if not self.paths:
            raise OSError("No files are selected for dragging.")
        parents = {os.path.normcase(str(path.parent)) for path in self.paths}
        if len(parents) != 1:
            raise OSError("Shell drag items must come from the same folder.")
        if any(not path.exists() for path in self.paths):
            raise OSError("A selected drag item no longer exists.")
        self.pointer = 0
        self._pidls: list[int] = []
        self._ole_initialized = False
        self._create()

    def _create(self) -> None:
        ole32, shell32 = ctypes.windll.ole32, ctypes.windll.shell32
        ole32.OleInitialize.argtypes = [ctypes.c_void_p]
        ole32.OleInitialize.restype = ctypes.c_long
        initialized = ole32.OleInitialize(None)
        if _failed(initialized):
            raise OSError(f"Cannot initialize Windows drag-and-drop ({_status_text(initialized)}).")
        self._ole_initialized = True
        shell32.SHParseDisplayName.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p,
                                               ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint32,
                                               ctypes.POINTER(ctypes.c_uint32)]
        shell32.SHParseDisplayName.restype = ctypes.c_long
        shell32.ILFindLastID.argtypes = [ctypes.c_void_p]
        shell32.ILFindLastID.restype = ctypes.c_void_p
        shell32.SHCreateDataObject.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                               ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
                                               ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
        shell32.SHCreateDataObject.restype = ctypes.c_long
        try:
            parent = self._parse(str(self.paths[0].parent))
            self._pidls.append(parent)
            children = []
            for path in self.paths:
                absolute = self._parse(str(path))
                self._pidls.append(absolute)
                children.append(shell32.ILFindLastID(absolute))
            child_array = (ctypes.c_void_p * len(children))(*children)
            result = ctypes.c_void_p()
            status = shell32.SHCreateDataObject(parent, len(children), child_array, None,
                                                ctypes.byref(IID_IDATAOBJECT), ctypes.byref(result))
            if _failed(status) or not result.value:
                raise OSError(f"Windows could not create drag data ({_status_text(status)}).")
            self.pointer = result.value
        except Exception:
            self.close()
            raise

    def _parse(self, path: str) -> int:
        pointer, attributes = ctypes.c_void_p(), ctypes.c_uint32()
        status = ctypes.windll.shell32.SHParseDisplayName(
            path, None, ctypes.byref(pointer), 0, ctypes.byref(attributes))
        if _failed(status) or not pointer.value:
            raise OSError(f"Windows could not identify drag item: {path} ({_status_text(status)}).")
        return pointer.value

    def close(self) -> None:
        if os.name != "nt":
            return
        if self.pointer:
            _release_interface(self.pointer)
            self.pointer = 0
        for pidl in self._pidls:
            ctypes.windll.ole32.CoTaskMemFree(ctypes.c_void_p(pidl))
        self._pidls.clear()
        if self._ole_initialized:
            ctypes.windll.ole32.OleUninitialize()
            self._ole_initialized = False

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        self.close()


def start_shell_drag(hwnd: int, paths) -> int:
    """Run the native Shell drag loop and return its DROPEFFECT value."""
    if os.name != "nt":
        raise OSError("Windows Shell drag-and-drop is available only on Windows.")
    shell32 = ctypes.windll.shell32
    shell32.SHDoDragDrop.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                     ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
    shell32.SHDoDragDrop.restype = ctypes.c_long
    effect = ctypes.c_uint32(DROPEFFECT_NONE)
    with ShellDataObject(paths) as data:
        status = shell32.SHDoDragDrop(ctypes.c_void_p(hwnd), ctypes.c_void_p(data.pointer), None,
                                     DROPEFFECT_COPY | DROPEFFECT_MOVE, ctypes.byref(effect))
        if _failed(status):
            raise OSError(f"Windows drag-and-drop failed ({_status_text(status)}).")
    return effect.value


def point_belongs_to_process(x: int, y: int, process_id: int | None = None) -> bool:
    """Return whether the top window under a screen point belongs to this process."""
    if os.name != "nt":
        return True
    user32 = ctypes.windll.user32
    user32.WindowFromPoint.argtypes = [_POINT]
    user32.WindowFromPoint.restype = ctypes.c_void_p
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    user32.GetWindowThreadProcessId.restype = ctypes.c_uint32
    hwnd = user32.WindowFromPoint(_POINT(int(x), int(y)))
    if not hwnd:
        return False
    owner = ctypes.c_uint32()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
    return owner.value == (process_id or os.getpid())


if os.name == "nt":
    _WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint,
                                  ctypes.c_size_t, ctypes.c_ssize_t)
else:
    _WNDPROC = None


def _guid_equal(first, second: _GUID) -> bool:
    return bool(first) and ctypes.string_at(first, ctypes.sizeof(_GUID)) == bytes(second)


def _drop_effect(kind: str | None, key_state: int, allowed: int) -> int:
    if kind == "virtual":
        return DROPEFFECT_COPY if allowed & DROPEFFECT_COPY else DROPEFFECT_NONE
    if kind == "files":
        preferred = DROPEFFECT_MOVE if key_state & MK_SHIFT else DROPEFFECT_COPY
        if allowed & preferred:
            return preferred
        fallback = DROPEFFECT_COPY if preferred == DROPEFFECT_MOVE else DROPEFFECT_MOVE
        return fallback if allowed & fallback else DROPEFFECT_NONE
    return DROPEFFECT_NONE


def _hdrop_paths_from_data_object(data_object: int) -> list[Path]:
    medium = _get_medium(data_object, CF_HDROP, -1, TYMED_HGLOBAL)
    try:
        shell32 = ctypes.windll.shell32
        shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                           ctypes.c_wchar_p, ctypes.c_uint]
        shell32.DragQueryFileW.restype = ctypes.c_uint
        count = shell32.DragQueryFileW(medium.data, UINT_MAX, None, 0)
        paths = []
        for index in range(count):
            length = shell32.DragQueryFileW(medium.data, index, None, 0)
            buffer = ctypes.create_unicode_buffer(length + 1)
            shell32.DragQueryFileW(medium.data, index, buffer, len(buffer))
            paths.append(Path(buffer.value))
        return paths
    finally:
        _release_medium(medium)


if os.name == "nt":
    _QUERY_INTERFACE = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                                          ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))
    _ADD_REF = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
    _RELEASE = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
    _DRAG_ENTER = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
                                     ctypes.c_uint32, _POINT, ctypes.POINTER(ctypes.c_uint32))
    _DRAG_OVER = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_uint32,
                                    _POINT, ctypes.POINTER(ctypes.c_uint32))
    _DRAG_LEAVE = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)
    _DROP = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
                               ctypes.c_uint32, _POINT, ctypes.POINTER(ctypes.c_uint32))

    class _IDropTargetVTable(ctypes.Structure):
        _fields_ = [("QueryInterface", _QUERY_INTERFACE), ("AddRef", _ADD_REF),
                    ("Release", _RELEASE), ("DragEnter", _DRAG_ENTER),
                    ("DragOver", _DRAG_OVER), ("DragLeave", _DRAG_LEAVE), ("Drop", _DROP)]

    class _IDropTargetInstance(ctypes.Structure):
        _fields_ = [("lpVtbl", ctypes.POINTER(_IDropTargetVTable))]


class _OleDropTarget:
    """Small COM IDropTarget that accepts Shell paths and Office virtual files."""

    def __init__(self, owner) -> None:
        self.owner = owner
        self.references = 1
        self.kind = None
        self.callbacks = (
            _QUERY_INTERFACE(self._query_interface), _ADD_REF(self._add_ref),
            _RELEASE(self._release), _DRAG_ENTER(self._drag_enter),
            _DRAG_OVER(self._drag_over), _DRAG_LEAVE(self._drag_leave), _DROP(self._drop),
        )
        self.vtable = _IDropTargetVTable(*self.callbacks)
        self.instance = _IDropTargetInstance(ctypes.pointer(self.vtable))
        self.pointer = ctypes.addressof(self.instance)

    def _query_interface(self, this, iid, result):
        if _guid_equal(iid, IID_IUNKNOWN) or _guid_equal(iid, IID_IDROPTARGET):
            result[0] = this
            self._add_ref(this)
            return S_OK
        result[0] = None
        return E_NOINTERFACE

    def _add_ref(self, _this):
        self.references += 1
        return self.references

    def _release(self, _this):
        self.references = max(0, self.references - 1)
        return self.references

    def _detect_kind(self, data_object: int) -> str | None:
        try:
            # Explorer may advertise virtual formats too; prefer durable paths
            # so its normal copy/Shift-move behavior remains intact.
            if data_object_has_format(data_object, CF_HDROP, -1, TYMED_HGLOBAL):
                return "files"
            if self.owner.virtual_callback and data_object_has_format(
                    data_object, virtual_file_format_id(), -1, TYMED_HGLOBAL):
                return "virtual"
        except (OSError, ValueError):
            pass
        return None

    def _drag_enter(self, _this, data_object, key_state, _point, effect):
        self.kind = self._detect_kind(data_object)
        effect[0] = _drop_effect(self.kind, key_state, effect[0])
        return S_OK

    def _drag_over(self, _this, key_state, _point, effect):
        effect[0] = _drop_effect(self.kind, key_state, effect[0])
        return S_OK

    def _drag_leave(self, _this):
        self.kind = None
        return S_OK

    def _drop(self, _this, data_object, key_state, point, effect):
        kind = self.kind or self._detect_kind(data_object)
        accepted = _drop_effect(kind, key_state, effect[0])
        try:
            if kind == "files":
                paths = _hdrop_paths_from_data_object(data_object)
                self.owner._queue_file_drop(paths, point.x, point.y,
                                            accepted == DROPEFFECT_MOVE)
            elif kind == "virtual":
                self.owner._queue_virtual_drop(data_object, point.x, point.y)
            else:
                accepted = DROPEFFECT_NONE
        except (OSError, MemoryError):
            accepted = DROPEFFECT_NONE
        self.kind = None
        effect[0] = accepted
        return S_OK


class ShellFileDropTarget:
    """Explorer and Office virtual-file drop target attached to a Tk widget HWND."""

    def __init__(self, widget, callback, virtual_callback=None) -> None:
        self.widget = widget
        self.callback = callback
        self.virtual_callback = virtual_callback
        self.hwnd = 0
        self.old_proc = 0
        self._window_proc = None
        self._ole_target = None
        self._ole_initialized = False
        self._ole_registered = False
        self._virtual_results = queue.Queue()
        self._virtual_workers = 0
        self._virtual_poll_job = None
        if os.name == "nt":
            self.install()

    @property
    def active(self) -> bool:
        return bool(self.hwnd and self.old_proc and self._window_proc)

    def install(self) -> None:
        if self.active or os.name != "nt":
            return
        user32, shell32 = ctypes.windll.user32, ctypes.windll.shell32
        self.hwnd = int(self.widget.winfo_id())
        self._window_proc = _WNDPROC(self._dispatch)
        user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        ctypes.set_last_error(0)
        previous = user32.SetWindowLongPtrW(
            ctypes.c_void_p(self.hwnd), GWL_WNDPROC,
            ctypes.cast(self._window_proc, ctypes.c_void_p))
        if not previous:
            error = ctypes.get_last_error()
            self._window_proc = None
            self.hwnd = 0
            raise OSError(error, "Cannot enable Windows Explorer file drop.")
        self.old_proc = int(previous)
        shell32.DragAcceptFiles.argtypes = [ctypes.c_void_p, ctypes.c_int]
        shell32.DragAcceptFiles(ctypes.c_void_p(self.hwnd), True)
        self._install_ole_target()
        self.widget.bind("<Destroy>", lambda _event: self.close(), add="+")

    def _install_ole_target(self) -> None:
        ole32 = ctypes.windll.ole32
        ole32.OleInitialize.argtypes = [ctypes.c_void_p]
        ole32.OleInitialize.restype = ctypes.c_long
        status = ole32.OleInitialize(None)
        if _failed(status):
            return
        self._ole_initialized = True
        self._ole_target = _OleDropTarget(self)
        ole32.RegisterDragDrop.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        ole32.RegisterDragDrop.restype = ctypes.c_long
        status = ole32.RegisterDragDrop(ctypes.c_void_p(self.hwnd),
                                        ctypes.c_void_p(self._ole_target.pointer))
        if _failed(status):
            self._ole_target = None
            ole32.OleUninitialize()
            self._ole_initialized = False
            return
        self._ole_registered = True

    def _queue_file_drop(self, paths, x_root: int, y_root: int, move: bool) -> None:
        self.widget.after_idle(lambda: self.callback(list(paths), x_root, y_root, move))

    def _queue_virtual_drop(self, data_object: int, x_root: int, y_root: int) -> None:
        raw = tempfile.mkdtemp(prefix="pfc-office-drop-")
        try:
            stream = _marshal_data_object(data_object)
        except Exception:
            shutil.rmtree(raw, ignore_errors=True)
            raise

        self._virtual_workers += 1
        if self._virtual_poll_job is None:
            self._virtual_poll_job = self.widget.after(40, self._poll_virtual_results)

        def extract():
            initialized = False; marshalled = None
            try:
                ole32 = ctypes.windll.ole32
                status = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
                initialized = not _failed(status)
                marshalled = _unmarshal_data_object(stream)
                items, failures = extract_virtual_files_from_data_object(
                    marshalled, Path(raw))
                self._virtual_results.put((raw, items, failures, x_root, y_root))
            except Exception as exc:
                self._virtual_results.put((raw, [], [("Office attachment", str(exc))],
                                           x_root, y_root))
            finally:
                if marshalled: _release_interface(marshalled)
                if initialized: ctypes.windll.ole32.CoUninitialize()
        threading.Thread(target=extract, daemon=True,
                         name="PFC-Office-Drop").start()

    def _poll_virtual_results(self) -> None:
        self._virtual_poll_job = None
        while True:
            try:
                raw, items, failures, x_root, y_root = self._virtual_results.get_nowait()
            except queue.Empty:
                break
            self._virtual_workers = max(0, self._virtual_workers - 1)
            try:
                self.virtual_callback(items, failures, x_root, y_root)
            finally:
                shutil.rmtree(raw, ignore_errors=True)
        if self._virtual_workers:
            self._virtual_poll_job = self.widget.after(40, self._poll_virtual_results)

    def _dispatch(self, hwnd, message, wparam, lparam):
        if message == WM_DROPFILES:
            try:
                paths, x_root, y_root, move = self._read_drop(wparam)
                self._queue_file_drop(paths, x_root, y_root, move)
            except Exception:
                pass
            return 0
        user32 = ctypes.windll.user32
        user32.CallWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
                                           ctypes.c_size_t, ctypes.c_ssize_t]
        user32.CallWindowProcW.restype = ctypes.c_ssize_t
        return user32.CallWindowProcW(ctypes.c_void_p(self.old_proc), hwnd, message, wparam, lparam)

    def _read_drop(self, handle: int):
        shell32, user32 = ctypes.windll.shell32, ctypes.windll.user32
        shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                           ctypes.c_wchar_p, ctypes.c_uint]
        shell32.DragQueryFileW.restype = ctypes.c_uint
        shell32.DragQueryPoint.argtypes = [ctypes.c_void_p, ctypes.POINTER(_POINT)]
        shell32.DragQueryPoint.restype = ctypes.c_int
        shell32.DragFinish.argtypes = [ctypes.c_void_p]
        try:
            count = shell32.DragQueryFileW(ctypes.c_void_p(handle), UINT_MAX, None, 0)
            paths = []
            for index in range(count):
                length = shell32.DragQueryFileW(ctypes.c_void_p(handle), index, None, 0)
                buffer = ctypes.create_unicode_buffer(length + 1)
                shell32.DragQueryFileW(ctypes.c_void_p(handle), index, buffer, len(buffer))
                paths.append(Path(buffer.value))
            point = _POINT()
            shell32.DragQueryPoint(ctypes.c_void_p(handle), ctypes.byref(point))
            user32.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.POINTER(_POINT)]
            user32.ClientToScreen(ctypes.c_void_p(self.hwnd), ctypes.byref(point))
            user32.GetKeyState.argtypes = [ctypes.c_int]
            move = bool(user32.GetKeyState(VK_SHIFT) & 0x8000)
            return paths, point.x, point.y, move
        finally:
            shell32.DragFinish(ctypes.c_void_p(handle))

    def close(self) -> None:
        if not self.active or os.name != "nt":
            return
        user32, shell32 = ctypes.windll.user32, ctypes.windll.shell32
        if self._ole_registered:
            ctypes.windll.ole32.RevokeDragDrop(ctypes.c_void_p(self.hwnd))
            self._ole_registered = False
        if self._virtual_poll_job is not None:
            try: self.widget.after_cancel(self._virtual_poll_job)
            except Exception: pass
            self._virtual_poll_job = None
        self._ole_target = None
        if self._ole_initialized:
            ctypes.windll.ole32.OleUninitialize()
            self._ole_initialized = False
        shell32.DragAcceptFiles(ctypes.c_void_p(self.hwnd), False)
        user32.IsWindow.argtypes = [ctypes.c_void_p]
        if user32.IsWindow(ctypes.c_void_p(self.hwnd)):
            user32.SetWindowLongPtrW(ctypes.c_void_p(self.hwnd), GWL_WNDPROC,
                                     ctypes.c_void_p(self.old_proc))
        self.hwnd = 0
        self.old_proc = 0
        self._window_proc = None
