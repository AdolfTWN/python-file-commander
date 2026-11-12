"""Recover an unreachable main window without disturbing normal monitor placement."""
import ctypes
from ctypes import wintypes
import os
import time
import tkinter as tk


def popup_work_area(owner):
    """Use the owner's monitor work area, excluding native taskbars/docks."""
    root = owner._root()
    guard = getattr(root, '_window_visibility', None)
    backend = getattr(guard, 'backend', None)
    if backend is not None:
        try:
            state = backend.snapshot()
            if state:
                rect, areas, _margin = state
                cx, cy = (rect[0]+rect[2])/2, (rect[1]+rect[3])/2
                return next((a for a in areas if a[0] <= cx < a[2] and a[1] <= cy < a[3]), areas[0])
        except (OSError, tk.TclError, IndexError):
            pass
    return (0, 0, owner.winfo_screenwidth(), owner.winfo_screenheight())


def position_popup_in_work_area(widget, owner, area):
    """Place the complete native frame, not just its client content."""
    widget.update_idletasks()
    backend = WindowsWindowPlacement(widget) if os.name == 'nt' else None
    state = backend.snapshot() if backend is not None else None
    width = state[0][2]-state[0][0] if state else widget.winfo_width()
    height = state[0][3]-state[0][1] if state else widget.winfo_height()
    x = max(area[0]+8, min(owner.winfo_rootx()+30, area[2]-width-8))
    y = max(area[1]+8, min(owner.winfo_rooty()+30, area[3]-height-8))
    if state:
        backend.move((x, y, width, height))
    else:
        widget.geometry(f'{x:+d}{y:+d}')


def visible_window_target(rect, work_areas, frame_margin=8, *, fit=False):
    """Return a safe (x, y, width, height), or None when already reachable.

    Work areas are individual monitors, primary first, not the virtual desktop's
    bounding box (which can contain gaps). Coordinates may be negative.
    With fit=True, keep the complete frame in the work area, not just its title.
    """
    left, top, right, bottom = rect
    width, height = right-left, bottom-top
    if width <= 0 or height <= 0 or not work_areas:
        return None
    for x1, y1, x2, y2 in work_areas:
        overlap = min(right, x2)-max(left, x1)
        # Permit the usual invisible resize border and partially offscreen sides,
        # but require a usable strip of the actual title bar, not just file rows.
        if overlap >= min(160, width) and y1-frame_margin <= top <= y2-40:
            if fit:
                if (x1-frame_margin<=left<=x1 and y1-frame_margin<=top<=y1
                        and x2<=right<=x2+frame_margin and y2<=bottom<=y2+frame_margin):
                    return None  # Keep a valid maximized frame/resize border.
                w,h=min(width,x2-x1),min(height,y2-y1)
                x,y=max(x1,min(left,x2-w)),max(y1,min(top,y2-h))
                if (x,y,w,h)!=(left,top,width,height):return x,y,w,h
            return None
    x1, y1, x2, y2 = work_areas[0]
    width, height = min(width, x2-x1), min(height, y2-y1)
    return (x1+(x2-x1-width)//2, y1+(y2-y1-height)//2, width, height)


class WindowsWindowPlacement:
    """Native frame/work-area coordinates share the process's DPI awareness."""
    def __init__(self, widget):
        self.widget = widget
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
            ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
        class MonitorInfo(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                        ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]
        self.info_type = MonitorInfo
        signatures = {
            'GetAncestor': ([wintypes.HWND, wintypes.UINT], wintypes.HWND),
            'GetWindowRect': ([wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
            'GetMonitorInfoW': ([wintypes.HANDLE, ctypes.POINTER(MonitorInfo)], wintypes.BOOL),
            'EnumDisplayMonitors': ([wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                    self.callback_type, wintypes.LPARAM], wintypes.BOOL),
            'SetWindowPos': ([wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.BOOL),
            'IsIconic': ([wintypes.HWND], wintypes.BOOL),
            'IsZoomed': ([wintypes.HWND], wintypes.BOOL),
            'ShowWindow': ([wintypes.HWND, ctypes.c_int], wintypes.BOOL),
            'GetAsyncKeyState': ([ctypes.c_int], ctypes.c_short),
            'GetDpiForWindow': ([wintypes.HWND], wintypes.UINT),
            'GetSystemMetricsForDpi': ([ctypes.c_int, wintypes.UINT], ctypes.c_int),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.user, name)
            fn.argtypes, fn.restype = args, result

    def handle(self):
        return self.user.GetAncestor(self.widget.winfo_id(), 2)

    def snapshot(self):
        hwnd = self.handle()
        # Never restore a deliberately minimized window or interrupt a mouse drag.
        if not hwnd or self.user.IsIconic(hwnd) or self.user.GetAsyncKeyState(1) & 0x8000:
            return None
        rect = wintypes.RECT()
        if not self.user.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        areas = []
        @self.callback_type
        def collect(monitor, _dc, _rect, _data):
            info = self.info_type()
            info.cbSize = ctypes.sizeof(info)
            if self.user.GetMonitorInfoW(monitor, ctypes.byref(info)):
                r = info.rcWork
                if r.right > r.left and r.bottom > r.top:
                    areas.append((not bool(info.dwFlags & 1), (r.left, r.top, r.right, r.bottom)))
            return True
        if not self.user.EnumDisplayMonitors(None, None, collect, 0):
            return None
        areas.sort(key=lambda item: item[0])
        dpi = self.user.GetDpiForWindow(hwnd) or 96
        border = (self.user.GetSystemMetricsForDpi(33, dpi) +
                  self.user.GetSystemMetricsForDpi(92, dpi))  # CYSIZEFRAME + CXPADDEDBORDER
        return ((rect.left, rect.top, rect.right, rect.bottom),
                tuple(area for _, area in areas), max(8, border))

    def move(self, target):
        hwnd = self.handle()
        if self.user.IsZoomed(hwnd):
            self.user.ShowWindow(hwnd, 9)  # Restore only an unreachable maximized window.
        # Absolute signed coordinates, no activation or z-order change. Tk's '-x'
        # geometry syntax instead means distance from the RIGHT edge of a screen.
        if not self.user.SetWindowPos(hwnd, None, *target, 0x0014):  # NOZORDER | NOACTIVATE
            raise ctypes.WinError(ctypes.get_last_error())


class WindowVisibilityGuard:
    """Lightweight Tk-thread check at startup, after undocking, and after resume."""
    def __init__(self, widget, backend=None, *, fit_to_monitor=False, role='Window'):
        self.widget = widget
        self.backend = backend if backend is not None else (
            WindowsWindowPlacement(widget) if os.name == 'nt' else None)
        self.previous = None
        self.work_areas = None
        self.fit_to_monitor = fit_to_monitor
        self.role = role
        self._last_notice = -float('inf')
        self._failed = False
        self.job = widget.after(250, self._tick)
        widget.bind('<Destroy>', self._destroyed, add='+')

    def _destroyed(self, event):
        if event.widget == self.widget:
            self.close()

    def close(self):
        if self.job is not None:
            self.widget.after_cancel(self.job)
            self.job = None

    def recover(self):
        """Best-effort immediate recovery after an explicit window activation."""
        try:self.check(force=True)
        except (tk.TclError,OSError):
            self.previous=None
            self._failure()

    def _record(self, event, **details):
        log=getattr(self.widget._root(), 'debug_log', None)
        if log is not None:
            log.event(event, severity='WARNING', include_context=False,
                      window=dict(role=self.role, **details))

    def _failure(self):
        if not self._failed:
            self._record('window.placement.unavailable', reason='Display placement API unavailable; will retry')
        self._failed=True

    def check(self, *, force=False):
        if self.widget.state() in ('withdrawn', 'iconic') or not self.widget.winfo_ismapped():
            self.previous = None
            return
        if self.backend is not None:
            snapshot = self.backend.snapshot()
        else:
            x, y = self.widget.winfo_rootx(), self.widget.winfo_rooty()
            snapshot = ((x, y, x+self.widget.winfo_width(), y+self.widget.winfo_height()),
                        ((0, 0, self.widget.winfo_screenwidth(), self.widget.winfo_screenheight()),))
        # Wait for two stable observations, so changing display/DPI configurations
        # and normal window moves can settle before we intervene.
        if snapshot is not None and (force or snapshot == self.previous):
            # Popup size is fitted only on activation/topology change, not
            # after every user drag or intentional partial placement.
            fit=self.fit_to_monitor and (force or snapshot[1]!=self.work_areas)
            target = visible_window_target(*snapshot,fit=fit)
            self.work_areas=snapshot[1]
            if target is not None:
                if self.backend is not None:
                    self.backend.move(target)
                else:
                    x, y, width, height = target
                    self.widget.geometry(f'{width}x{height}+{x}+{y}')
                if time.monotonic()-self._last_notice>=5:
                    self._record('window.placement.recovery', before=list(snapshot[0]),
                                 target=list(target), work_areas=[list(a) for a in snapshot[1][:8]],
                                 reason='Fit current work area' if fit else 'Outside current display')
                    self._last_notice=time.monotonic()
                self._failed=False
                self.previous = None
                return
        self.previous = snapshot

    def _tick(self):
        self.job = None
        try:
            self.check()
        except (tk.TclError, OSError):
            # Display APIs can temporarily fail while Windows switches displays.
            self.previous = None
            self._failure()
        if self.widget.winfo_exists():
            self.job = self.widget.after(1000, self._tick)
