"""Local-only common-folder discovery, preferences, matching and small icons."""
from __future__ import annotations

import json
import configparser
import os
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from functools import lru_cache
import math
from tkinter import ttk, filedialog, messagebox
from .i18n import tr
from .icons import _rgba_png_downsample, _hex_rgba, _distance_to_segment


PREFIX_ICONS = {"home": "User folder", "cloud": "OneDrive", "download": "Downloads",
                "code": "Code", "documents": "Documents", "photos": "Photos"}
CUSTOM_ICONS = ("code", "documents", "photos")


def load_custom_prefixes(config):
    try:
        saved = json.loads(config.get("home_prefixes", "custom", fallback="[]"))
    except (ValueError, TypeError, configparser.Error):
        saved = []
    if not isinstance(saved, list):
        saved = []
    result = []
    for index, default in enumerate(CUSTOM_ICONS):
        item = saved[index] if index < len(saved) and isinstance(saved[index], dict) else {}
        icon = item.get("icon", default)
        path = item.get("path", "")
        result.append({"icon": icon if isinstance(icon, str) and icon in PREFIX_ICONS else default,
                       "path": path if isinstance(path, str) else ""})
    return result


def save_custom_prefixes(config, items):
    if not config.has_section("home_prefixes"):
        config.add_section("home_prefixes")
    # ConfigParser uses % interpolation; preserve literal percent in folder names.
    config.set("home_prefixes", "custom", json.dumps(items, ensure_ascii=False).replace("%", "%%"))


def discover_home_prefixes():
    home = Path.home()
    downloads = home / "Downloads"
    clouds = [os.environ.get(key, "") for key in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")]
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
                value, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
                downloads = Path(os.path.expandvars(value))
        except OSError:
            pass
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\OneDrive\Accounts") as accounts:
                for index in range(winreg.QueryInfoKey(accounts)[0]):
                    try:
                        with winreg.OpenKey(accounts, winreg.EnumKey(accounts, index)) as account:
                            clouds.append(winreg.QueryValueEx(account, "UserFolder")[0])
                    except OSError:
                        continue
        except OSError:
            pass
    elif (home / "OneDrive").is_dir():
        clouds.append(str(home / "OneDrive"))
    result = [(home, "home"), (downloads, "download")]
    for value in clouds:
        if isinstance(value, str) and value:
            path = Path(os.path.normpath(os.path.expandvars(value))).expanduser()
            if path.is_absolute() and (path, "cloud") not in result:
                result.append((path, "cloud"))
    return result


def match_home_prefix(path, automatic, custom):
    """Path-component match; deepest wins, a custom slot wins equal depth."""
    candidates = list(automatic)
    for item in reversed(custom):
        if item["path"]:
            # Use the same path flavour, also allowing pure Windows-path tests.
            prefix = type(path)(os.path.normpath(item["path"]))
            if prefix.is_absolute():
                candidates.append((prefix, item["icon"]))
    match = None
    for prefix, icon in candidates:
        try:
            path.relative_to(prefix)
        except ValueError:
            continue
        if match is None or len(prefix.parts) >= len(match[0].parts):
            match = (prefix, icon)
    return match


def prefix_icon_size(widget):
    """One physical-pixel size for toolbar, popup and preferences at any DPI."""
    return max(12, tkfont.nametofont("TkDefaultFont", root=widget).metrics("linespace"))


@lru_cache(maxsize=128)
def prefix_icon_png(kind, size, foreground="#34465a"):
    """Rasterize vector geometry at 4x, then alpha-aware downsample to native size."""
    supersample = 4
    extent = size * supersample
    pixels = bytearray(extent * extent * 4)
    unit = extent / 32
    # Distinct, saturated hues identify the hidden prefix at a glance. Root is
    # deliberately neutral and has a different silhouette from every prefix.
    colors = {"home": "#ef9000", "cloud": "#0085f5", "download": "#00a653",
              "code": "#8836ef", "documents": "#009fac", "photos": "#ed297e"}
    face = _hex_rgba(colors.get(kind, colors["home"]))
    white = (255, 255, 255, 255)
    def paint(bounds, inside, color):
        x1, y1, x2, y2 = bounds
        for y in range(max(0, math.floor(y1*unit)), min(extent, math.ceil(y2*unit))):
            py = (y+.5)/unit
            for x in range(max(0, math.floor(x1*unit)), min(extent, math.ceil(x2*unit))):
                px = (x+.5)/unit
                if inside(px, py):
                    index = (y*extent+x)*4
                    pixels[index:index+4] = bytes(color(px, py) if callable(color) else color)
    def rounded(x1, y1, x2, y2, radius, color):
        def inside(x, y):
            cx = max(x1+radius, min(x, x2-radius))
            cy = max(y1+radius, min(y, y2-radius))
            return (x-cx)**2 + (y-cy)**2 <= radius**2
        paint((x1,y1,x2,y2), inside, color)
    def circle(x, y, radius, color=white):
        paint((x-radius,y-radius,x+radius,y+radius), lambda px,py: (px-x)**2+(py-y)**2 <= radius**2, color)
    def line(x1,y1,x2,y2,width=1.8,color=white):
        r = width/2
        paint((min(x1,x2)-r,min(y1,y2)-r,max(x1,x2)+r,max(y1,y2)+r),
              lambda x,y: _distance_to_segment(x,y,x1,y1,x2,y2) <= r, color)
    if kind == "parent":
        ink = _hex_rgba(foreground)
        line(16,27,16,5,2.4,ink); line(7,14,16,5,2.4,ink); line(16,5,25,14,2.4,ink)
        return _rgba_png_downsample(pixels, size, supersample)
    if kind == "root":
        rounded(2,3,30,29,3,_hex_rgba("#52687e"))
        rounded(3,4,29,21,2,_hex_rgba("#71879c"))
        # A directory-tree badge on a drive, rather than the user-folder badge.
        rounded(13,7,19,11,1,white)
        line(16,11,16,14,1.4); line(9,14,23,14,1.4)
        for x in (9,23):
            line(x,14,x,16,1.4); rounded(x-3,16,x+3,19,1,white)
        line(7,25,20,25,1.6); circle(25,25,1.2)
        return _rgba_png_downsample(pixels, size, supersample)
    rear = tuple(round(c*.79) for c in face[:3]) + (255,)
    rounded(2,3,14,12,2,rear); rounded(2,6,30,29,2.5,rear)
    # A restrained highlight separates the front flap from the rear tab.
    def gradient(x,y):
        light = max(0, .19*(28-y)/19)
        return tuple(round(c+(255-c)*light) for c in face[:3])+(255,)
    rounded(2,9,30,29,2.5,gradient)
    line(5,10,27,10,.65,tuple(round(c+(255-c)*.28) for c in face[:3])+(255,))
    if kind == "home":
        circle(16,15,3.1); rounded(10,19.5,22,25.5,3,white)
    elif kind == "cloud":
        circle(11,21,3.3); circle(16,18.2,4.3); circle(21.5,21,3.1)
        rounded(10,20,23,24.1,1.7,white)
    elif kind == "download":
        line(16,13,16,22,2.1); line(12,18.5,16,22,2.1); line(20,18.5,16,22,2.1)
        line(10,25,22,25,1.8)
    elif kind == "code":
        line(11,14,7,19); line(7,19,11,24)
        line(21,14,25,19); line(25,19,21,24); line(18,13,14,25)
    elif kind == "documents":
        rounded(10,12,22,26,1.4,white)
        for y in (16,19,22): line(13,y,19,y,1.2,face)
    else:
        rounded(7,12,25,26,1.5,white); rounded(8.5,13.5,23.5,24.5,.5,face)
        circle(12,17,1.6); line(9.5,23,15,18.5,1.5); line(15,18.5,19,23,1.5)
        line(18,22,21,19.5,1.5); line(21,19.5,23,22,1.5)
    return _rgba_png_downsample(pixels, size, supersample)


def prefix_icon(master, kind, size=None, foreground="#34465a"):
    size = prefix_icon_size(master) if size is None else size
    return tk.PhotoImage(master=master, data=prefix_icon_png(kind, size, foreground), format="png")


class PrefixPreferences(tk.Toplevel):
    def __init__(self, owner, items, save):
        super().__init__(owner)
        self.title(tr("Custom folder prefixes"))
        self.transient(owner)
        self.resizable(True, False)
        self.columnconfigure(2, weight=1)
        self.rows = []
        self.previews = []
        self.images = {key: prefix_icon(self, key) for key in PREFIX_ICONS}
        self.keys = list(PREFIX_ICONS)
        ttk.Label(self, text=tr("Choose up to three prefixes. Empty paths disable a slot.")).grid(
            row=0, column=0, columnspan=4, padx=12, pady=10, sticky="w")
        for index, item in enumerate(items):
            preview = ttk.Label(self, image=self.images[item["icon"]])
            preview.grid(row=index+1, column=0, padx=(12, 4))
            self.previews.append(preview)
            icon = ttk.Combobox(self, state="readonly", width=14,
                               values=[tr(PREFIX_ICONS[key]) for key in self.keys])
            icon.current(self.keys.index(item["icon"]))
            icon.grid(row=index+1, column=1, padx=4, pady=6)
            icon.bind("<<ComboboxSelected>>", lambda _e, c=icon, p=preview:
                      p.configure(image=self.images[self.keys[c.current()]]))
            path = tk.StringVar(value=item["path"])
            ttk.Entry(self, width=48, textvariable=path).grid(row=index+1, column=2, padx=4, sticky="ew")
            def browse(variable=path):
                chosen = filedialog.askdirectory(parent=self)
                if chosen: variable.set(chosen)
            ttk.Button(self, text="…", width=3, command=browse).grid(row=index+1, column=3, padx=(4, 12))
            self.rows.append((icon, path))
        def commit():
            result = []
            for icon, variable in self.rows:
                value = variable.get().strip().strip('"')
                if value:
                    path = Path(os.path.normpath(os.path.expandvars(value))).expanduser()
                    if not path.is_absolute():
                        messagebox.showerror(tr("Custom folder prefixes"), tr("Enter an absolute folder path."), parent=self)
                        return
                    value = str(path)
                result.append({"icon": self.keys[icon.current()], "path": value})
            save(result)
            self.destroy()
        self.save_button = ttk.Button(self, text=tr("Save"), command=commit)
        self.save_button.grid(row=4, column=2, sticky="e", padx=4, pady=10)
        ttk.Button(self, text=tr("Cancel"), command=self.destroy).grid(row=4, column=3, padx=12, pady=10)
        self.bind("<Escape>", lambda _e: self.destroy())

    def apply_scale(self):
        self.images = {key: prefix_icon(self, key) for key in PREFIX_ICONS}
        for preview, (combo, _path) in zip(self.previews, self.rows):
            preview.configure(image=self.images[self.keys[combo.current()]])
