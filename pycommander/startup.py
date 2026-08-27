from __future__ import annotations

import ctypes
import os
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path, PureWindowsPath


AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE = "Python File Commander"


def startup_command(executable: Path | str | None = None,
                    script: Path | str | None = None,
                    *, frozen: bool | None = None,
                    pythonw_exists=None) -> str:
    """Return the per-user Windows startup command for this PFC edition."""
    def resolved(value):
        raw = os.fspath(value)
        windows_path = PureWindowsPath(raw)
        return windows_path if windows_path.drive else Path(raw).resolve()

    executable = resolved(executable or sys.executable)
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if frozen:
        arguments = [str(executable), "--startup"]
    else:
        candidate = executable.with_name("pythonw.exe")
        exists = Path(candidate).is_file() if pythonw_exists is None else pythonw_exists(candidate)
        launcher = candidate if exists else executable
        script = resolved(script or sys.argv[0])
        arguments = [str(launcher), str(script), "--startup"]
    return subprocess.list2cmdline(arguments)


def set_windows_autostart(enabled: bool, command: str | None = None,
                          registry=None) -> bool:
    """Synchronize PFC's HKCU Run value. Return False off Windows."""
    if registry is None:
        if os.name != "nt":
            return False
        import winreg as registry
    if enabled:
        with registry.CreateKey(registry.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
            registry.SetValueEx(key, AUTOSTART_VALUE, 0, registry.REG_SZ,
                                command or startup_command())
    else:
        try:
            with registry.OpenKey(registry.HKEY_CURRENT_USER, AUTOSTART_KEY, 0,
                                  registry.KEY_SET_VALUE) as key:
                registry.DeleteValue(key, AUTOSTART_VALUE)
        except FileNotFoundError:
            pass
    return True


class WindowsTrayIcon:
    """Small native notification-area host that sends actions to Tk via a queue."""

    def __init__(self, actions: queue.Queue, icon_bytes: bytes, *,
                 open_label: str, auto_start_label: str, exit_label: str,
                 auto_start_enabled: bool) -> None:
        self.actions = actions
        self.icon_bytes = icon_bytes
        self.open_label = open_label
        self.auto_start_label = auto_start_label
        self.exit_label = exit_label
        self.auto_start_enabled = auto_start_enabled
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._hwnd = 0
        self._stop_requested = threading.Event()
        self.error: Exception | None = None

    def start(self) -> bool:
        if os.name != "nt" or self._thread is not None:
            return False
        self._thread = threading.Thread(target=self._run, name="PFC-Tray", daemon=True)
        self._thread.start()
        return True

    def update(self, *, auto_start_enabled: bool | None = None,
               open_label: str | None = None, auto_start_label: str | None = None,
               exit_label: str | None = None) -> None:
        if auto_start_enabled is not None:
            self.auto_start_enabled = auto_start_enabled
        if open_label is not None:
            self.open_label = open_label
        if auto_start_label is not None:
            self.auto_start_label = auto_start_label
        if exit_label is not None:
            self.exit_label = exit_label

    def stop(self) -> None:
        self._stop_requested.set()
        if os.name == "nt" and self._hwnd:
            ctypes.windll.user32.PostMessageW(self._hwnd, 0x0010, 0, 0)  # WM_CLOSE

    def _run(self) -> None:
        from ctypes import wintypes

        WM_APP, WM_CLOSE, WM_DESTROY = 0x8000, 0x0010, 0x0002
        WM_LBUTTONUP, WM_LBUTTONDBLCLK, WM_RBUTTONUP = 0x0202, 0x0203, 0x0205
        WM_NULL, NIM_ADD, NIM_DELETE, NIM_SETVERSION = 0x0000, 0, 2, 4
        NIF_MESSAGE, NIF_ICON, NIF_TIP, NOTIFYICON_VERSION_4 = 1, 2, 4, 4
        MF_STRING, MF_SEPARATOR, MF_CHECKED = 0, 0x0800, 0x0008
        TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x0002, 0x0100
        IMAGE_ICON, LR_LOADFROMFILE = 1, 0x0010
        CALLBACK_MESSAGE = WM_APP + 23
        OPEN_COMMAND, AUTOSTART_COMMAND, EXIT_COMMAND = 1001, 1002, 1003

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                        ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                        ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                        ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
                        ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
                        ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
                        ("dwInfoFlags", wintypes.DWORD), ("guidItem", GUID),
                        ("hBalloonIcon", wintypes.HICON)]

        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(
            LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

        user32, shell32, kernel32 = (
            ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32)
        user32.DefWindowProcW.restype = LRESULT
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                          wintypes.WPARAM, wintypes.LPARAM]
        user32.RegisterClassW.restype = wintypes.ATOM
        user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
            wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                        wintypes.WPARAM, wintypes.LPARAM]
        user32.CreatePopupMenu.restype = wintypes.HMENU
        user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT,
                                       ctypes.c_size_t, wintypes.LPCWSTR]
        user32.TrackPopupMenu.restype = wintypes.UINT
        user32.TrackPopupMenu.argtypes = [
            wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, ctypes.c_void_p]
        user32.DestroyMenu.argtypes = [wintypes.HMENU]
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                       wintypes.UINT, wintypes.UINT]
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR,
                                      wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                      wintypes.UINT]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD,
                                              ctypes.POINTER(NOTIFYICONDATAW)]
        icon_path = Path(tempfile.gettempdir()) / "pfc-notification.ico"
        notify = None
        icon = 0

        def add_icon() -> None:
            if notify is None:
                return
            notify.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            notify.uVersion = 0
            shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(notify))
            notify.uVersion = NOTIFYICON_VERSION_4
            shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(notify))

        def show_menu(hwnd) -> None:
            menu = user32.CreatePopupMenu()
            if not menu:
                return
            user32.AppendMenuW(menu, MF_STRING, OPEN_COMMAND, self.open_label)
            flags = MF_STRING | (MF_CHECKED if self.auto_start_enabled else 0)
            user32.AppendMenuW(menu, flags, AUTOSTART_COMMAND, self.auto_start_label)
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, EXIT_COMMAND, self.exit_label)
            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            user32.SetForegroundWindow(hwnd)
            command = user32.TrackPopupMenu(
                menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, point.x, point.y, 0, hwnd, None)
            user32.DestroyMenu(menu)
            user32.PostMessageW(hwnd, WM_NULL, 0, 0)
            if command == OPEN_COMMAND:
                self.actions.put("show")
            elif command == AUTOSTART_COMMAND:
                self.actions.put("toggle_autostart")
            elif command == EXIT_COMMAND:
                self.actions.put("exit")

        taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")

        @WNDPROC
        def window_proc(hwnd, message, wparam, lparam):
            if message == CALLBACK_MESSAGE:
                event = int(lparam) & 0xFFFF
                if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    self.actions.put("show")
                elif event == WM_RBUTTONUP:
                    show_menu(hwnd)
                return 0
            if message == taskbar_created:
                add_icon()
                return 0
            if message == WM_CLOSE:
                if notify is not None:
                    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(notify))
                user32.DestroyWindow(hwnd)
                return 0
            if message == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, message, wparam, lparam)

        try:
            icon_path.write_bytes(self.icon_bytes)
            instance = kernel32.GetModuleHandleW(None)
            class_name = f"PFCTrayWindow_{id(self)}"
            window_class = WNDCLASSW()
            window_class.lpfnWndProc = window_proc
            window_class.hInstance = instance
            window_class.lpszClassName = class_name
            if not user32.RegisterClassW(ctypes.byref(window_class)):
                raise ctypes.WinError()
            hwnd = user32.CreateWindowExW(
                0, class_name, "PFC Tray", 0, 0, 0, 0, 0, 0, 0, instance, None)
            if not hwnd:
                raise ctypes.WinError()
            self._hwnd = hwnd
            self._thread_id = kernel32.GetCurrentThreadId()
            icon = user32.LoadImageW(None, str(icon_path), IMAGE_ICON, 32, 32,
                                     LR_LOADFROMFILE)
            if not icon:
                raise ctypes.WinError()
            notify = NOTIFYICONDATAW()
            notify.cbSize = ctypes.sizeof(notify)
            notify.hWnd = hwnd
            notify.uID = 1
            notify.uCallbackMessage = CALLBACK_MESSAGE
            notify.hIcon = icon
            notify.szTip = "PFC — Python File Commander"
            add_icon()
            if self._stop_requested.is_set():
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except Exception as exc:
            self.error = exc
        finally:
            if notify is not None:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(notify))
            if icon:
                user32.DestroyIcon(icon)
            try:
                icon_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._hwnd = 0
