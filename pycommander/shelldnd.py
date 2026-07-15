from __future__ import annotations

import ctypes
import os
from pathlib import Path


DROPEFFECT_NONE = 0
DROPEFFECT_COPY = 1
DROPEFFECT_MOVE = 2
WM_DROPFILES = 0x0233
GWL_WNDPROC = -4
UINT_MAX = 0xFFFFFFFF
VK_SHIFT = 0x10


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


IID_IDATAOBJECT = _GUID(
    0x0000010E, 0x0000, 0x0000,
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


class ShellFileDropTarget:
    """Legacy Explorer file-drop target attached to a Tk widget HWND."""

    def __init__(self, widget, callback) -> None:
        self.widget = widget
        self.callback = callback
        self.hwnd = 0
        self.old_proc = 0
        self._window_proc = None
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
        self.widget.bind("<Destroy>", lambda _event: self.close(), add="+")

    def _dispatch(self, hwnd, message, wparam, lparam):
        if message == WM_DROPFILES:
            try:
                paths, x_root, y_root, move = self._read_drop(wparam)
                self.widget.after_idle(
                    lambda values=paths, x=x_root, y=y_root, shift=move:
                    self.callback(values, x, y, shift))
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
        shell32.DragAcceptFiles(ctypes.c_void_p(self.hwnd), False)
        user32.IsWindow.argtypes = [ctypes.c_void_p]
        if user32.IsWindow(ctypes.c_void_p(self.hwnd)):
            user32.SetWindowLongPtrW(ctypes.c_void_p(self.hwnd), GWL_WNDPROC,
                                     ctypes.c_void_p(self.old_proc))
        self.hwnd = 0
        self.old_proc = 0
        self._window_proc = None
