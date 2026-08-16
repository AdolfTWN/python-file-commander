"""Small dependency-free bridge to the native Windows Shell context menu."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path


S_OK = 0
COINIT_APARTMENTTHREADED = 0x2
CMF_NORMAL = 0
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
SW_SHOWNORMAL = 1


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]


class _CMINVOKECOMMANDINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("fMask", ctypes.c_uint32),
                ("hwnd", ctypes.c_void_p), ("lpVerb", ctypes.c_void_p),
                ("lpParameters", ctypes.c_char_p), ("lpDirectory", ctypes.c_char_p),
                ("nShow", ctypes.c_int), ("dwHotKey", ctypes.c_uint32),
                ("hIcon", ctypes.c_void_p)]


IID_ISHELLFOLDER = _GUID(
    0x000214E6, 0x0000, 0x0000,
    (ctypes.c_ubyte * 8)(0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))
IID_ICONTEXTMENU = _GUID(
    0x000214E4, 0x0000, 0x0000,
    (ctypes.c_ubyte * 8)(0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))


def context_menu_paths(paths) -> list[Path]:
    """Validate that selected local items can share one Shell context menu."""
    items = [Path(path).resolve() for path in paths]
    if not items:
        raise OSError("Select one or more local files or folders first.")
    if any(not path.exists() for path in items):
        raise OSError("A selected file or folder no longer exists.")
    parents = {os.path.normcase(str(path.parent)) for path in items}
    if len(parents) != 1:
        raise OSError("Windows Shell context menus require items from one folder.")
    return items


def _failed(status: int) -> bool:
    return status < 0


def _method(pointer: int, index: int, *argtypes):
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(table[index])


def _release(pointer: int) -> None:
    if pointer:
        _method(pointer, 2)(pointer)


def show_shell_context_menu(hwnd: int, paths, x_root: int, y_root: int) -> bool:
    """Display the actual Explorer context menu and invoke its chosen command."""
    if os.name != "nt":
        raise OSError("Windows Shell context menus are available only on Windows.")
    items = context_menu_paths(paths)
    ole32, shell32, user32 = ctypes.windll.ole32, ctypes.windll.shell32, ctypes.windll.user32
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ole32.CoInitializeEx.restype = ctypes.c_long
    initialized = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    if _failed(initialized):
        raise OSError("Windows could not initialize the Shell context menu.")
    pidls: list[int] = []
    parent = context = 0
    menu = 0
    try:
        shell32.ILCreateFromPathW.argtypes = [ctypes.c_wchar_p]
        shell32.ILCreateFromPathW.restype = ctypes.c_void_p
        shell32.SHBindToParent.argtypes = [ctypes.c_void_p, ctypes.POINTER(_GUID),
                                           ctypes.POINTER(ctypes.c_void_p),
                                           ctypes.POINTER(ctypes.c_void_p)]
        shell32.SHBindToParent.restype = ctypes.c_long
        absolute = shell32.ILCreateFromPathW(str(items[0]))
        if not absolute:
            raise OSError("Windows could not identify the selected item.")
        pidls.append(absolute)
        child = ctypes.c_void_p()
        parent_ptr = ctypes.c_void_p()
        status = shell32.SHBindToParent(ctypes.c_void_p(absolute), ctypes.byref(IID_ISHELLFOLDER),
                                        ctypes.byref(parent_ptr), ctypes.byref(child))
        if _failed(status) or not parent_ptr.value or not child.value:
            raise OSError("Windows could not open the selected folder menu.")
        parent = parent_ptr.value
        children = [child.value]
        for path in items[1:]:
            absolute = shell32.ILCreateFromPathW(str(path))
            if not absolute:
                raise OSError("Windows could not identify a selected item.")
            pidls.append(absolute)
            other_parent, other_child = ctypes.c_void_p(), ctypes.c_void_p()
            status = shell32.SHBindToParent(ctypes.c_void_p(absolute), ctypes.byref(IID_ISHELLFOLDER),
                                            ctypes.byref(other_parent), ctypes.byref(other_child))
            if _failed(status) or not other_child.value:
                raise OSError("Windows could not open a selected item menu.")
            _release(other_parent.value)
            children.append(other_child.value)
        child_array = (ctypes.c_void_p * len(children))(*children)
        context_ptr = ctypes.c_void_p()
        get_ui_object = _method(parent, 10, ctypes.c_void_p, ctypes.c_uint,
                                ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(_GUID),
                                ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
        status = get_ui_object(parent, ctypes.c_void_p(hwnd), len(children), child_array,
                               ctypes.byref(IID_ICONTEXTMENU), None, ctypes.byref(context_ptr))
        if _failed(status) or not context_ptr.value:
            raise OSError("Windows could not create the Explorer context menu.")
        context = context_ptr.value
        menu = user32.CreatePopupMenu()
        if not menu:
            raise OSError("Windows could not create the Explorer context menu.")
        query_menu = _method(context, 3, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                             ctypes.c_uint, ctypes.c_uint)
        status = query_menu(context, ctypes.c_void_p(menu), 0, 1, 0x7FFF, CMF_NORMAL)
        if _failed(status):
            raise OSError("Windows could populate the Explorer context menu.")
        user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
        command = user32.TrackPopupMenu(ctypes.c_void_p(menu), TPM_RIGHTBUTTON | TPM_RETURNCMD,
                                        int(x_root), int(y_root), 0, ctypes.c_void_p(hwnd), None)
        if command:
            invoke = _method(context, 4, ctypes.POINTER(_CMINVOKECOMMANDINFO))
            info = _CMINVOKECOMMANDINFO(
                ctypes.sizeof(_CMINVOKECOMMANDINFO), 0, ctypes.c_void_p(hwnd),
                ctypes.c_void_p(command - 1), None, None, SW_SHOWNORMAL, 0, None)
            status = invoke(context, ctypes.byref(info))
            if _failed(status):
                raise OSError("Windows could run the selected Explorer command.")
        return bool(command)
    finally:
        if menu:
            user32.DestroyMenu(ctypes.c_void_p(menu))
        _release(context)
        _release(parent)
        for pidl in pidls:
            ole32.CoTaskMemFree(ctypes.c_void_p(pidl))
        ole32.CoUninitialize()
