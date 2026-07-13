from __future__ import annotations

import os
import shutil
import ctypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


ConflictResolver = Callable[[Path, Path], str]


@dataclass
class OperationFailure:
    source: Path
    target: Path | None
    message: str


@dataclass
class OperationResult:
    completed: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    failures: list[OperationFailure] = field(default_factory=list)

    @property
    def successful(self) -> bool:
        return not self.failures and not self.skipped


def unique_target(target: Path) -> Path:
    if not target.exists():
        return target
    for number in range(2, 10000):
        candidate = target.with_name(f"{target.stem} ({number}){target.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Cannot find an available name for {target.name}")


def _remove_existing(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _copy_or_move(source: Path, target: Path, move: bool) -> None:
    if move:
        shutil.move(str(source), str(target))
    elif source.is_dir():
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)


def _replace_transactional(source: Path, target: Path, move: bool) -> None:
    backup = unique_target(target.with_name(f".{target.name}.pfc-backup"))
    target.rename(backup)
    try:
        _copy_or_move(source, target, move)
    except (OSError, shutil.Error):
        try:
            if target.exists(): _remove_existing(target)
            backup.rename(target)
        except OSError:
            pass
        raise
    try:
        _remove_existing(backup)
    except OSError:
        pass  # The new item is valid; preserve the old backup rather than risking either copy.


def transfer_items(items: list[Path], destination: Path, move: bool = False,
                   resolve_conflict: ConflictResolver | None = None,
                   continue_on_error: bool = True) -> OperationResult:
    destination.mkdir(parents=True, exist_ok=True)
    result = OperationResult()
    for index, source in enumerate(items):
        target = destination / source.name
        try:
            source_resolved, target_resolved = source.resolve(), target.resolve()
            replace = False
            if source.is_dir() and source_resolved in target_resolved.parents:
                raise OSError("A folder cannot be copied or moved into itself.")
            if target.exists():
                action = resolve_conflict(source, target) if resolve_conflict else "replace"
                if action == "cancel":
                    result.skipped.extend(items[index:])
                    break
                if action == "skip":
                    result.skipped.append(source)
                    continue
                if action == "keep_both":
                    target = unique_target(target)
                elif action == "replace":
                    if source_resolved == target_resolved:
                        raise OSError("Source and destination are the same item. Choose Keep Both or Skip.")
                    replace = True
                else:
                    raise ValueError(f"Unknown conflict action: {action}")
            if replace:
                _replace_transactional(source, target, move)
            else:
                _copy_or_move(source, target, move)
            result.completed.append(source)
        except (OSError, shutil.Error, ValueError) as exc:
            result.failures.append(OperationFailure(source, target, str(exc)))
            if not continue_on_error:
                result.skipped.extend(items[index + 1:])
                break
    return result


def copy_items(items: list[Path], destination: Path,
               resolve_conflict: ConflictResolver | None = None,
               continue_on_error: bool = True) -> OperationResult:
    return transfer_items(items, destination, move=False, resolve_conflict=resolve_conflict,
                          continue_on_error=continue_on_error)


def move_items(items: list[Path], destination: Path,
               resolve_conflict: ConflictResolver | None = None,
               continue_on_error: bool = True) -> OperationResult:
    return transfer_items(items, destination, move=True, resolve_conflict=resolve_conflict,
                          continue_on_error=continue_on_error)


def delete_items(items: list[Path], continue_on_error: bool = True) -> OperationResult:
    result = OperationResult()
    for item in items:
        try:
            _remove_existing(item)
            result.completed.append(item)
        except OSError as exc:
            result.failures.append(OperationFailure(item, None, str(exc)))
            if not continue_on_error:
                result.skipped.extend(items[len(result.completed) + len(result.failures):])
                break
    return result


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint),
                ("pFrom", ctypes.c_wchar_p), ("pTo", ctypes.c_wchar_p),
                ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", ctypes.c_int),
                ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p)]


def recycle_items(items: list[Path], continue_on_error: bool = True) -> OperationResult:
    result = OperationResult()
    if os.name != "nt":
        return OperationResult(failures=[OperationFailure(item, None, "Recycle Bin requires Windows.")
                                         for item in items])
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32
    kernel32.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
    kernel32.GetDriveTypeW.restype = ctypes.c_uint
    shell32.SHFileOperationW.argtypes = [ctypes.POINTER(_SHFILEOPSTRUCTW)]
    shell32.SHFileOperationW.restype = ctypes.c_int
    for item in items:
        if str(item).startswith("\\\\") or (item.anchor and kernel32.GetDriveTypeW(str(item.anchor)) == 4):
            result.failures.append(OperationFailure(
                item, None, "Network locations do not provide a safe Windows Recycle Bin. Use Shift+Del explicitly."))
            if not continue_on_error:
                result.skipped.extend(items[len(result.completed) + len(result.failures):])
                break
            continue
        operation = _SHFILEOPSTRUCTW(None, 3, str(item.resolve()) + "\0\0", None,
                                     0x40 | 0x10 | 0x04 | 0x400, 0, None, None)
        code = shell32.SHFileOperationW(ctypes.byref(operation))
        if code == 0 and not operation.fAnyOperationsAborted:
            result.completed.append(item)
        else:
            message = "Recycle operation was cancelled." if operation.fAnyOperationsAborted else f"Windows error 0x{code:04X}"
            result.failures.append(OperationFailure(item, None, message))
            if not continue_on_error:
                result.skipped.extend(items[len(result.completed) + len(result.failures):])
                break
    return result


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
