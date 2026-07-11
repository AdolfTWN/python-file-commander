from __future__ import annotations

import ctypes
import os
import struct
import time
from pathlib import Path


CF_HDROP = 15
GMEM_MOVEABLE_ZEROINIT = 0x0042
DROPEFFECT_COPY = 1
DROPEFFECT_MOVE = 2


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
    effect_format = user32.RegisterClipboardFormatW("Preferred DropEffect")
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
    effect_format = user32.RegisterClipboardFormatW("Preferred DropEffect")
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
