from __future__ import annotations

import base64
import binascii
import ctypes
import os
import struct
import zlib
from pathlib import Path
from tkinter import PhotoImage


VCS_BADGE_SPECS = {
    "clean": ("#218838", "check", "#ffffff"),
    "modified": ("#e02f2f", "alert", "#ffffff"),
    "added": ("#1266b3", "plus", "#ffffff"),
    "untracked": ("#6f42c1", "question", "#ffffff"),
    "deleted": ("#a80f20", "minus", "#ffffff"),
    "conflict": ("#f2b705", "cross", "#171717"),
}


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


def _inside_polygon(x: float, y: float, points) -> bool:
    inside = False
    previous = points[-1]
    for current in points:
        x1, y1 = previous; x2, y2 = current
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing:
                inside = not inside
        previous = current
    return inside


def _paint_polygon(pixels: bytearray, canvas_size: int, points, color) -> None:
    left = max(0, int(min(x for x, _y in points)))
    right = min(canvas_size - 1, int(max(x for x, _y in points)) + 1)
    top = max(0, int(min(y for _x, y in points)))
    bottom = min(canvas_size - 1, int(max(y for _x, y in points)) + 1)
    for row in range(top, bottom + 1):
        for column in range(left, right + 1):
            if _inside_polygon(column + 0.5, row + 0.5, points):
                index = (row * canvas_size + column) * 4
                pixels[index:index + 4] = bytes(color)


def pfc_icon_png(size: int = 32) -> bytes:
    """Render a red/black interlocking-arrow mark with a light taskbar outline."""
    if size < 8:
        raise ValueError("PFC icon size must be at least 8 pixels")
    supersample = 4
    canvas_size = size * supersample
    factor = canvas_size / 64
    shape = bytearray(canvas_size * canvas_size * 4)
    red, black = (238, 28, 45, 255), (25, 24, 27, 255)
    left_half = ((19, 3), (32, 16), (32, 30), (19, 18))
    right_half = ((45, 3), (32, 16), (32, 30), (45, 18))

    def rotate(points):
        return tuple((64 - y, x) for x, y in points)

    left, right = left_half, right_half
    for index in range(4):
        left_color, right_color = ((black, red) if index % 2 == 0 else
                                   (red, black))
        _paint_polygon(shape, canvas_size,
                       tuple((x * factor, y * factor) for x, y in left),
                       left_color)
        _paint_polygon(shape, canvas_size,
                       tuple((x * factor, y * factor) for x, y in right),
                       right_color)
        left, right = rotate(left), rotate(right)

    # The open center keeps the four inward arrows visually separate.
    center = ((32, 25), (39, 32), (32, 39), (25, 32))
    _paint_polygon(shape, canvas_size,
                   tuple((x * factor, y * factor) for x, y in center),
                   (0, 0, 0, 0))

    # A narrow white silhouette keeps the black vanes visible on dark Aero/taskbars.
    pixels = bytearray(canvas_size * canvas_size * 4)
    radius = max(2, round(1.35 * factor))
    for row in range(canvas_size):
        for column in range(canvas_size):
            index = (row * canvas_size + column) * 4
            if shape[index + 3]:
                continue
            found = False
            for offset_y in range(-radius, radius + 1):
                check_y = row + offset_y
                if not 0 <= check_y < canvas_size:
                    continue
                for offset_x in range(-radius, radius + 1):
                    if offset_x * offset_x + offset_y * offset_y > radius * radius:
                        continue
                    check_x = column + offset_x
                    if not 0 <= check_x < canvas_size:
                        continue
                    check = (check_y * canvas_size + check_x) * 4
                    if shape[check + 3]:
                        found = True; break
                if found:
                    break
            if found:
                pixels[index:index + 4] = bytes((255, 255, 255, 255))
    for index in range(0, len(shape), 4):
        if shape[index + 3]:
            pixels[index:index + 4] = shape[index:index + 4]

    rgba = bytearray()
    for row in range(size):
        rgba.append(0)
        for column in range(size):
            samples = []
            for sub_y in range(supersample):
                for sub_x in range(supersample):
                    index = (((row * supersample + sub_y) * canvas_size +
                              column * supersample + sub_x) * 4)
                    samples.append(pixels[index:index + 4])
            alpha_sum = sum(sample[3] for sample in samples)
            alpha = round(alpha_sum / len(samples))
            if alpha_sum:
                red = round(sum(sample[0] * sample[3] for sample in samples) / alpha_sum)
                green = round(sum(sample[1] * sample[3] for sample in samples) / alpha_sum)
                blue = round(sum(sample[2] * sample[3] for sample in samples) / alpha_sum)
            else:
                red = green = blue = 0
            rgba.extend((red, green, blue, alpha))
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) +
            _chunk(b"IDAT", zlib.compress(bytes(rgba), 9)) + _chunk(b"IEND", b""))


def create_pfc_icon(size: int = 32) -> PhotoImage:
    encoded = base64.b64encode(pfc_icon_png(size)).decode("ascii")
    return PhotoImage(data=encoded, format="png")


def _rgba_png_downsample(pixels: bytearray, output_size: int, supersample: int) -> bytes:
    canvas_size = output_size * supersample
    rgba = bytearray()
    for row in range(output_size):
        rgba.append(0)
        for column in range(output_size):
            samples = []
            for sub_y in range(supersample):
                for sub_x in range(supersample):
                    index = (((row * supersample + sub_y) * canvas_size +
                              column * supersample + sub_x) * 4)
                    samples.append(pixels[index:index + 4])
            alpha_sum = sum(sample[3] for sample in samples)
            alpha = round(alpha_sum / len(samples))
            if alpha_sum:
                colors = [round(sum(sample[channel] * sample[3] for sample in samples) / alpha_sum)
                          for channel in range(3)]
            else:
                colors = [0, 0, 0]
            rgba.extend((*colors, alpha))
    header = struct.pack(">IIBBBBB", output_size, output_size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) +
            _chunk(b"IDAT", zlib.compress(bytes(rgba), 9)) + _chunk(b"IEND", b""))


def _hex_rgba(value: str) -> tuple[int, int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4)) + (255,)


def _distance_to_segment(px, py, x1, y1, x2, y2) -> float:
    dx, dy = x2 - x1, y2 - y1
    if dx == dy == 0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** .5
    position = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) /
                                (dx * dx + dy * dy)))
    nearest_x, nearest_y = x1 + position * dx, y1 + position * dy
    return ((px - nearest_x) ** 2 + (py - nearest_y) ** 2) ** .5


def vcs_badge_png(size: int, status: str) -> bytes:
    """Render one anti-aliased, dual-outline Git/SVN status badge."""
    if size < 8 or status not in VCS_BADGE_SPECS:
        raise ValueError("Unsupported VCS badge")
    fill, glyph, ink = VCS_BADGE_SPECS[status]
    supersample, canvas_size = 4, size * 4
    pixels = bytearray(canvas_size * canvas_size * 4)
    center = (canvas_size - 1) / 2
    outer = canvas_size / 2 - .5
    dark_edge = _hex_rgba("#17212b")
    white_edge = _hex_rgba("#ffffff")
    fill_rgba, ink_rgba = _hex_rgba(fill), _hex_rgba(ink)
    dark_width = max(4, round(canvas_size * .075))
    white_width = max(4, round(canvas_size * .075))
    for y in range(canvas_size):
        for x in range(canvas_size):
            distance = ((x - center) ** 2 + (y - center) ** 2) ** .5
            color = (dark_edge if distance <= outer else None)
            if distance <= outer - dark_width:
                color = white_edge
            if distance <= outer - dark_width - white_width:
                color = fill_rgba
            if color:
                index = (y * canvas_size + x) * 4
                pixels[index:index + 4] = bytes(color)

    def point(x, y):
        return x * (canvas_size - 1), y * (canvas_size - 1)

    segments, dots = [], []
    if glyph == "check":
        segments = [((*point(.20, .52), *point(.42, .73))),
                    ((*point(.42, .73), *point(.79, .27)))]
    elif glyph == "alert":
        segments = [((*point(.50, .22), *point(.50, .59)))]
        dots = [point(.50, .76)]
    elif glyph == "plus":
        segments = [((*point(.50, .23), *point(.50, .77))),
                    ((*point(.23, .50), *point(.77, .50)))]
    elif glyph == "minus":
        segments = [((*point(.22, .50), *point(.78, .50)))]
    elif glyph == "cross":
        segments = [((*point(.25, .25), *point(.75, .75))),
                    ((*point(.75, .25), *point(.25, .75)))]
    elif glyph == "question":
        segments = [((*point(.28, .31), *point(.39, .21))),
                    ((*point(.39, .21), *point(.63, .21))),
                    ((*point(.63, .21), *point(.74, .33))),
                    ((*point(.74, .33), *point(.69, .46))),
                    ((*point(.69, .46), *point(.52, .56))),
                    ((*point(.52, .56), *point(.50, .64)))]
        dots = [point(.50, .78)]
    line_radius = max(2, round(canvas_size * .065))
    dot_radius = max(2, round(canvas_size * .07))
    for y in range(canvas_size):
        for x in range(canvas_size):
            sample_x, sample_y = x + .5, y + .5
            painted = any(_distance_to_segment(sample_x, sample_y, *segment) <= line_radius
                          for segment in segments)
            painted = painted or any(((sample_x - dot_x) ** 2 + (sample_y - dot_y) ** 2) ** .5
                                     <= dot_radius for dot_x, dot_y in dots)
            if painted:
                index = (y * canvas_size + x) * 4
                pixels[index:index + 4] = bytes(ink_rgba)
    return _rgba_png_downsample(pixels, size, supersample)


class ShellIconProvider:
    """Caches native Windows Shell icons as Tk images."""

    def __init__(self, size: int = 16, text_gap: int | None = None) -> None:
        self.size = size
        self.text_gap = max(4, round(size * 0.3)) if text_gap is None else text_gap
        self.cache: dict[str, PhotoImage] = {}
        self.blank = PhotoImage(width=size + self.text_gap, height=size)

    def get(self, path: Path, is_dir: bool, overlay: str | None = None) -> PhotoImage:
        if os.name != "nt":
            return self.blank
        suffix = path.suffix.casefold()
        base_key = "<folder>" if is_dir else (str(path) if suffix in {".exe", ".lnk", ".ico"} else suffix or "<file>")
        key = f"{base_key}|{overlay or ''}"
        if key not in self.cache:
            icon = self._load(path)
            if icon is not None and overlay:
                icon = self._with_overlay(icon, overlay)
            self.cache[key] = self._with_text_gap(icon) if icon is not None else self.blank
        return self.cache[key]

    def _with_overlay(self, icon: PhotoImage, overlay: str) -> PhotoImage:
        result = PhotoImage(width=self.size, height=self.size)
        result.tk.call(str(result), "copy", str(icon), "-to", 0, 0)
        if overlay in VCS_BADGE_SPECS:
            diameter = min(self.size, max(10, round(self.size * .62)))
            encoded = base64.b64encode(vcs_badge_png(diameter, overlay)).decode("ascii")
            badge = PhotoImage(data=encoded, format="png")
            result.tk.call(str(result), "copy", str(badge),
                           "-to", self.size - diameter, self.size - diameter,
                           "-compositingrule", "overlay")
        return result

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
