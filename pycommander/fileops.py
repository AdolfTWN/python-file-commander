from __future__ import annotations

import os
import shutil
import ctypes
from pathlib import Path


def copy_items(items: list[Path], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for source in items:
        target = destination / source.name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)


def move_items(items: list[Path], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for source in items:
        shutil.move(str(source), str(destination / source.name))


def delete_items(items: list[Path]) -> None:
    for item in items:
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return str(size)


def roots() -> list[Path]:
    if os.name != "nt":
        return [Path("/")]
    return [Path(f"{letter}:\\") for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{letter}:\\").exists()]


def is_system(path: Path) -> bool:
    """Return whether Windows marks a path with the SYSTEM attribute."""
    if os.name != "nt":
        return False
    attributes = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    return attributes != 0xFFFFFFFF and bool(attributes & 0x4)
