from __future__ import annotations

import ctypes
import os
import shutil
import struct
import time
from dataclasses import dataclass
from pathlib import Path


CF_HDROP = 15
GMEM_MOVEABLE_ZEROINIT = 0x0042
DROPEFFECT_COPY = 1
DROPEFFECT_MOVE = 2
TYMED_HGLOBAL = 1
TYMED_FILE = 2
TYMED_ISTREAM = 4
DVASPECT_CONTENT = 1


@dataclass(frozen=True)
class VirtualFileDescriptor:
    name: str
    size: int


class _FORMATETC(ctypes.Structure):
    _fields_ = [("cfFormat", ctypes.c_ushort), ("ptd", ctypes.c_void_p),
                ("dwAspect", ctypes.c_uint32), ("lindex", ctypes.c_long),
                ("tymed", ctypes.c_uint32)]


class _STGMEDIUM(ctypes.Structure):
    _fields_ = [("tymed", ctypes.c_uint32), ("data", ctypes.c_void_p),
                ("pUnkForRelease", ctypes.c_void_p)]


class _FILEDESCRIPTORW(ctypes.Structure):
    _fields_ = [("dwFlags", ctypes.c_uint32), ("clsid", ctypes.c_byte * 16),
                ("sizel", ctypes.c_long * 2), ("pointl", ctypes.c_long * 2),
                ("dwFileAttributes", ctypes.c_uint32), ("ftCreationTime", ctypes.c_uint32 * 2),
                ("ftLastAccessTime", ctypes.c_uint32 * 2), ("ftLastWriteTime", ctypes.c_uint32 * 2),
                ("nFileSizeHigh", ctypes.c_uint32), ("nFileSizeLow", ctypes.c_uint32),
                ("cFileName", ctypes.c_wchar * 260)]


def _register_clipboard_format(name: str) -> int:
    user32 = ctypes.windll.user32
    user32.RegisterClipboardFormatW.argtypes = [ctypes.c_wchar_p]
    user32.RegisterClipboardFormatW.restype = ctypes.c_uint
    return user32.RegisterClipboardFormatW(name)


def _safe_virtual_name(value: str) -> str:
    name = value.replace("\\", "/").split("/")[-1].strip().rstrip(". ")
    if not name or name in {".", ".."}:
        raise OSError("Outlook supplied an invalid attachment name.")
    return name


def parse_file_group_descriptor(data: bytes) -> list[VirtualFileDescriptor]:
    if len(data) < 4:
        raise OSError("The virtual-file descriptor is incomplete.")
    count = struct.unpack_from("<I", data)[0]
    descriptor_size = ctypes.sizeof(_FILEDESCRIPTORW)
    if count > 10000 or len(data) < 4 + count * descriptor_size:
        raise OSError("The virtual-file descriptor has an invalid item count.")
    result = []
    for index in range(count):
        descriptor = _FILEDESCRIPTORW.from_buffer_copy(data, 4 + index * descriptor_size)
        result.append(VirtualFileDescriptor(_safe_virtual_name(descriptor.cFileName),
                                            (descriptor.nFileSizeHigh << 32) | descriptor.nFileSizeLow))
    return result


def _vtable_method(pointer: int, index: int, result_type, *argument_types):
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *argument_types)(table[index])


def _release_interface(pointer: int) -> None:
    if pointer:
        _vtable_method(pointer, 2, ctypes.c_ulong)(pointer)


def _get_ole_clipboard():
    ole32 = ctypes.windll.ole32
    ole32.OleInitialize.argtypes = [ctypes.c_void_p]; ole32.OleInitialize.restype = ctypes.c_long
    initialized = ole32.OleInitialize(None)
    if initialized < 0:
        raise OSError(f"Cannot initialize OLE clipboard access (0x{initialized & 0xFFFFFFFF:08X}).")
    pointer = ctypes.c_void_p()
    ole32.OleGetClipboard.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    ole32.OleGetClipboard.restype = ctypes.c_long
    status = ole32.OleGetClipboard(ctypes.byref(pointer))
    if status < 0 or not pointer.value:
        ole32.OleUninitialize()
        raise OSError("The Windows clipboard does not expose an OLE data object.")
    return pointer.value, initialized in (0, 1)


def _get_medium(data_object: int, format_id: int, index: int, tymed: int) -> _STGMEDIUM:
    request = _FORMATETC(format_id, None, DVASPECT_CONTENT, index, tymed)
    medium = _STGMEDIUM()
    get_data = _vtable_method(data_object, 3, ctypes.c_long,
                              ctypes.POINTER(_FORMATETC), ctypes.POINTER(_STGMEDIUM))
    status = get_data(data_object, ctypes.byref(request), ctypes.byref(medium))
    if status < 0:
        raise OSError(f"Outlook could not render attachment data (0x{status & 0xFFFFFFFF:08X}).")
    return medium


def _release_medium(medium: _STGMEDIUM) -> None:
    ctypes.windll.ole32.ReleaseStgMedium(ctypes.byref(medium))


def _global_bytes(handle: int) -> bytes:
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]; kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalSize.argtypes = [ctypes.c_void_p]; kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    pointer, size = kernel32.GlobalLock(handle), kernel32.GlobalSize(handle)
    if not pointer:
        raise OSError("Cannot read virtual-file clipboard memory.")
    try: return ctypes.string_at(pointer, size)
    finally: kernel32.GlobalUnlock(handle)


def _virtual_descriptors_from_object(data_object: int) -> list[VirtualFileDescriptor]:
    format_id = _register_clipboard_format("FileGroupDescriptorW")
    medium = _get_medium(data_object, format_id, -1, TYMED_HGLOBAL)
    try:
        if medium.tymed != TYMED_HGLOBAL or not medium.data:
            raise OSError("Outlook returned an unsupported attachment descriptor medium.")
        return parse_file_group_descriptor(_global_bytes(medium.data))
    finally:
        _release_medium(medium)


def data_object_has_format(data_object: int, format_id: int, index: int = -1,
                           tymed: int = TYMED_HGLOBAL) -> bool:
    """Return whether an OLE IDataObject can render the requested format."""
    request = _FORMATETC(format_id, None, DVASPECT_CONTENT, index, tymed)
    query = _vtable_method(data_object, 5, ctypes.c_long, ctypes.POINTER(_FORMATETC))
    return query(data_object, ctypes.byref(request)) >= 0


def virtual_file_format_id() -> int:
    return _register_clipboard_format("FileGroupDescriptorW")


def get_virtual_file_descriptors() -> list[VirtualFileDescriptor]:
    if os.name != "nt":
        return []
    data_object = None; uninitialize = False
    try:
        data_object, uninitialize = _get_ole_clipboard()
        return _virtual_descriptors_from_object(data_object)
    except OSError:
        return []
    finally:
        if data_object: _release_interface(data_object)
        if uninitialize: ctypes.windll.ole32.OleUninitialize()


def _write_stream(stream_pointer: int, target: Path) -> None:
    seek = _vtable_method(stream_pointer, 5, ctypes.c_long, ctypes.c_longlong,
                          ctypes.c_uint32, ctypes.POINTER(ctypes.c_ulonglong))
    position = ctypes.c_ulonglong()
    seek(stream_pointer, 0, 0, ctypes.byref(position))
    read = _vtable_method(stream_pointer, 3, ctypes.c_long, ctypes.c_void_p,
                          ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong))
    buffer = ctypes.create_string_buffer(1024 * 1024)
    with target.open("wb") as output:
        while True:
            count = ctypes.c_ulong()
            status = read(stream_pointer, buffer, len(buffer), ctypes.byref(count))
            if status < 0:
                raise OSError(f"Cannot read Outlook attachment stream (0x{status & 0xFFFFFFFF:08X}).")
            if count.value:
                output.write(buffer.raw[:count.value])
            if count.value == 0 or status == 1:
                break


def _write_virtual_medium(medium: _STGMEDIUM, target: Path, expected_size: int) -> None:
    if medium.tymed == TYMED_ISTREAM and medium.data:
        _write_stream(medium.data, target)
    elif medium.tymed == TYMED_HGLOBAL and medium.data:
        data = _global_bytes(medium.data)
        target.write_bytes(data[:expected_size] if expected_size else data)
    elif medium.tymed == TYMED_FILE and medium.data:
        shutil.copy2(ctypes.wstring_at(medium.data), target)
    else:
        raise OSError(f"Unsupported Outlook attachment medium: {medium.tymed}")


def extract_virtual_files_from_data_object(
        data_object: int, destination: Path) -> tuple[list[Path], list[tuple[str, str]]]:
    """Materialize Outlook/Teams virtual files while IDataObject is still valid."""
    extracted, failures = [], []
    destination.mkdir(parents=True, exist_ok=True)
    descriptors = _virtual_descriptors_from_object(data_object)
    content_format = _register_clipboard_format("FileContents")
    for index, descriptor in enumerate(descriptors):
        target = destination / descriptor.name
        if target.exists():
            target = target.with_name(f"{target.stem} ({index + 2}){target.suffix}")
        medium = None
        try:
            medium = _get_medium(data_object, content_format, index,
                                 TYMED_ISTREAM | TYMED_HGLOBAL | TYMED_FILE)
            _write_virtual_medium(medium, target, descriptor.size)
            extracted.append(target)
        except OSError as exc:
            failures.append((descriptor.name, str(exc)))
            try: target.unlink(missing_ok=True)
            except OSError: pass
        finally:
            if medium is not None: _release_medium(medium)
    return extracted, failures


def extract_virtual_files(destination: Path) -> tuple[list[Path], list[tuple[str, str]]]:
    if os.name != "nt":
        return [], []
    data_object = None; uninitialize = False
    try:
        data_object, uninitialize = _get_ole_clipboard()
        return extract_virtual_files_from_data_object(data_object, destination)
    finally:
        if data_object: _release_interface(data_object)
        if uninitialize: ctypes.windll.ole32.OleUninitialize()


def _open_clipboard() -> None:
    user32 = ctypes.windll.user32
    for _ in range(10):
        if user32.OpenClipboard(None):
            return
        time.sleep(0.02)
    raise OSError("The Windows clipboard is busy.")


def _global_data(payload: bytes) -> int:
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE_ZEROINIT, len(payload))
    if not handle:
        raise MemoryError("Cannot allocate clipboard memory.")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        raise MemoryError("Cannot lock clipboard memory.")
    ctypes.memmove(pointer, payload, len(payload))
    kernel32.GlobalUnlock(handle)
    return handle


def set_file_clipboard(paths: list[Path], cut: bool = False) -> None:
    """Publish files in the same clipboard formats used by File Explorer."""
    if os.name != "nt":
        raise OSError("File clipboard integration requires Windows.")
    resolved = [str(path.resolve()) for path in paths]
    if not resolved:
        return
    dropfiles = struct.pack("<IiiII", 20, 0, 0, 0, 1)
    dropfiles += ("\0".join(resolved) + "\0\0").encode("utf-16le")
    drop_handle = _global_data(dropfiles)
    effect_handle = _global_data(struct.pack("<I", DROPEFFECT_MOVE if cut else DROPEFFECT_COPY))
    user32 = ctypes.windll.user32
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    effect_format = _register_clipboard_format("Preferred DropEffect")
    _open_clipboard()
    try:
        if not user32.EmptyClipboard():
            raise OSError("Cannot clear the Windows clipboard.")
        if not user32.SetClipboardData(CF_HDROP, drop_handle):
            raise OSError("Cannot place files on the Windows clipboard.")
        drop_handle = None  # Windows owns successful clipboard handles.
        if not user32.SetClipboardData(effect_format, effect_handle):
            raise OSError("Cannot set the clipboard copy/cut mode.")
        effect_handle = None
    finally:
        user32.CloseClipboard()
        if drop_handle:
            ctypes.windll.kernel32.GlobalFree(drop_handle)
        if effect_handle:
            ctypes.windll.kernel32.GlobalFree(effect_handle)


def get_file_clipboard() -> tuple[list[Path], bool]:
    """Read files copied or cut by PFC or Windows File Explorer."""
    if os.name != "nt":
        return [], False
    user32, shell32, kernel32 = ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
    effect_format = _register_clipboard_format("Preferred DropEffect")
    _open_clipboard()
    try:
        drop_handle = user32.GetClipboardData(CF_HDROP)
        if not drop_handle:
            return [], False
        count = shell32.DragQueryFileW(drop_handle, 0xFFFFFFFF, None, 0)
        paths = []
        for index in range(count):
            length = shell32.DragQueryFileW(drop_handle, index, None, 0)
            buffer = ctypes.create_unicode_buffer(length + 1)
            shell32.DragQueryFileW(drop_handle, index, buffer, length + 1)
            paths.append(Path(buffer.value))
        cut = False
        effect_handle = user32.GetClipboardData(effect_format)
        if effect_handle:
            pointer = kernel32.GlobalLock(effect_handle)
            if pointer:
                cut = ctypes.c_uint32.from_address(pointer).value == DROPEFFECT_MOVE
                kernel32.GlobalUnlock(effect_handle)
        return paths, cut
    finally:
        user32.CloseClipboard()


def clear_file_clipboard() -> None:
    if os.name != "nt":
        return
    _open_clipboard()
    try:
        ctypes.windll.user32.EmptyClipboard()
    finally:
        ctypes.windll.user32.CloseClipboard()
