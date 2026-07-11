from __future__ import annotations

import base64
import binascii
import ctypes
import os
import struct
import zlib
from pathlib import Path
from tkinter import PhotoImage


class _SHFILEINFO(ctypes.Structure):
    _fields_ = [("hIcon", ctypes.c_void_p), ("iIcon", ctypes.c_int),
                ("dwAttributes", ctypes.c_uint32), ("szDisplayName", ctypes.c_wchar * 260),
                ("szTypeName", ctypes.c_wchar * 80)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", ctypes.c_ushort),
                ("biBitCount", ctypes.c_ushort), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)


def _png_from_bgra(raw: bytes, size: int) -> bytes:
    rgba = bytearray()
    has_alpha = any(raw[index + 3] for index in range(0, len(raw), 4))
    for row in range(size):
        rgba.append(0)
        for column in range(size):
            index = (row * size + column) * 4
            blue, green, red, alpha = raw[index:index + 4]
            if not has_alpha:
                alpha = 255 if red or green or blue else 0
            rgba.extend((red, green, blue, alpha))
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(bytes(rgba), 9)) + _chunk(b"IEND", b"")


class ShellIconProvider:
    """Caches native Windows Shell icons as Tk images."""

    def __init__(self, size: int = 16, text_gap: int | None = None) -> None:
        self.size = size
        self.text_gap = max(4, round(size * 0.3)) if text_gap is None else text_gap
        self.cache: dict[str, PhotoImage] = {}
        self.blank = PhotoImage(width=size + self.text_gap, height=size)

    def get(self, path: Path, is_dir: bool) -> PhotoImage:
        if os.name != "nt":
            return self.blank
        suffix = path.suffix.casefold()
        key = "<folder>" if is_dir else (str(path) if suffix in {".exe", ".lnk", ".ico"} else suffix or "<file>")
        if key not in self.cache:
            icon = self._load(path)
            self.cache[key] = self._with_text_gap(icon) if icon is not None else self.blank
        return self.cache[key]

    def _with_text_gap(self, icon: PhotoImage) -> PhotoImage:
        padded = PhotoImage(width=self.size + self.text_gap, height=self.size)
        padded.tk.call(str(padded), "copy", str(icon), "-to", 0, 0)
        return padded

    def _load(self, path: Path) -> PhotoImage | None:
        shell32, user32, gdi32 = ctypes.windll.shell32, ctypes.windll.user32, ctypes.windll.gdi32
        shell32.SHGetFileInfoW.restype = ctypes.c_size_t
        shell32.SHGetFileInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.POINTER(_SHFILEINFO), ctypes.c_uint, ctypes.c_uint]
        user32.GetDC.restype = ctypes.c_void_p
        user32.GetDC.argtypes = [ctypes.c_void_p]
        user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        user32.DestroyIcon.argtypes = [ctypes.c_void_p]
        user32.DrawIconEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                                      ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
        gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
        gdi32.CreateDIBSection.restype = ctypes.c_void_p
        gdi32.CreateDIBSection.argtypes = [ctypes.c_void_p, ctypes.POINTER(_BITMAPINFO), ctypes.c_uint,
                                           ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_uint]
        gdi32.SelectObject.restype = ctypes.c_void_p
        gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
        gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
        info = _SHFILEINFO()
        # The small Shell handle reliably contains alpha on all supported Windows
        # versions. DrawIconEx scales it to the selected UI profile; some large
        # handles render fully transparent when converted through a 32-bit DIB.
        flags = 0x1 | 0x100
        if not shell32.SHGetFileInfoW(str(path), 0, ctypes.byref(info), ctypes.sizeof(info), flags):
            return None
        screen = user32.GetDC(None)
        memory = gdi32.CreateCompatibleDC(screen)
        bitmap_info = _BITMAPINFO()
        bitmap_info.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bitmap_info.bmiHeader.biWidth = self.size
        bitmap_info.bmiHeader.biHeight = -self.size
        bitmap_info.bmiHeader.biPlanes = 1
        bitmap_info.bmiHeader.biBitCount = 32
        bitmap_info.bmiHeader.biCompression = 0
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(memory, ctypes.byref(bitmap_info), 0, ctypes.byref(bits), None, 0)
        old = gdi32.SelectObject(memory, bitmap)
        ctypes.memset(bits.value, 0, self.size * self.size * 4)
        user32.DrawIconEx(memory, 0, 0, info.hIcon, self.size, self.size, 0, None, 0x3)
        raw = ctypes.string_at(bits.value, self.size * self.size * 4)
        gdi32.SelectObject(memory, old)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(None, screen)
        user32.DestroyIcon(info.hIcon)
        try:
            encoded = base64.b64encode(_png_from_bgra(raw, self.size)).decode("ascii")
            return PhotoImage(data=encoded, format="png")
        except Exception:
            return None
