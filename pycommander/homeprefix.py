"""Local-only common-folder discovery, preferences, matching and small icons."""
from __future__ import annotations

import json
import configparser
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .i18n import tr


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


def prefix_icon(master, kind, size=24):
    """Draw recognizable folder badges without platform-dependent emoji fonts."""
    image = tk.PhotoImage(master=master, width=size, height=size)
    scale = size / 24
    colors = {"home": "#d99613", "cloud": "#2475c7", "download": "#23826a",
              "code": "#7157b5", "documents": "#3976a1", "photos": "#a95d82"}
    def rect(x1, y1, x2, y2, color):
        image.put(color, to=(round(x1*scale), round(y1*scale), max(round(x1*scale)+1, round(x2*scale)),
                             max(round(y1*scale)+1, round(y2*scale))))
    def line(x1, y1, x2, y2, color="#ffffff"):
        steps = max(abs(x2-x1), abs(y2-y1), 1)
        for step in range(steps + 1):
            x, y = x1+(x2-x1)*step/steps, y1+(y2-y1)*step/steps
            rect(x, y, x+1, y+1, color)
    color = colors.get(kind, colors["home"])
    rect(1, 3, 10, 7, color); rect(1, 6, 23, 22, color)
    if kind == "home":
        rect(10, 8, 15, 12, "#ffffff"); rect(8, 14, 17, 19, "#ffffff")
    elif kind == "cloud":
        rect(6, 13, 19, 17, "#ffffff"); rect(9, 10, 15, 16, "#ffffff")
    elif kind == "download":
        line(12, 8, 12, 16); line(8, 12, 12, 16); line(16, 12, 12, 16); line(7, 19, 17, 19)
    elif kind == "code":
        line(9, 10, 5, 14); line(5, 14, 9, 18); line(16, 10, 20, 14); line(20, 14, 16, 18); line(14, 9, 11, 19)
    elif kind == "documents":
        rect(7, 8, 18, 20, "#ffffff")
        for y in (11, 14, 17): line(9, y, 15, y, color)
    else:
        rect(5, 8, 20, 20, "#ffffff"); rect(7, 10, 10, 12, color)
        line(6, 18, 11, 13, color); line(11, 13, 16, 18, color); line(15, 16, 18, 13, color)
    return image


class PrefixPreferences(tk.Toplevel):
    def __init__(self, owner, items, save):
        super().__init__(owner)
        self.title(tr("Custom folder prefixes"))
        self.transient(owner)
        self.resizable(True, False)
        self.columnconfigure(2, weight=1)
        self.rows = []
        self.images = {key: prefix_icon(self, key) for key in PREFIX_ICONS}
        self.keys = list(PREFIX_ICONS)
        ttk.Label(self, text=tr("Choose up to three prefixes. Empty paths disable a slot.")).grid(
            row=0, column=0, columnspan=4, padx=12, pady=10, sticky="w")
        for index, item in enumerate(items):
            preview = ttk.Label(self, image=self.images[item["icon"]])
            preview.grid(row=index+1, column=0, padx=(12, 4))
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
