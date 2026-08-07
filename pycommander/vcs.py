from __future__ import annotations

import os
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path


_CACHE: dict[str, tuple[float, dict[str, str]]] = {}
_CACHE_SECONDS = 3.0
_PRIORITY = {"conflict": 5, "modified": 4, "added": 3, "untracked": 2,
             "deleted": 1, "clean": 0}


def _merge(statuses: dict[str, str], path: Path, status: str, root: Path) -> None:
    try:
        current = path.resolve()
    except OSError:
        current = Path(os.path.abspath(path))
    while current == root or root in current.parents:
        key = os.path.normcase(str(current))
        if key not in statuses or _PRIORITY.get(status, 0) > _PRIORITY.get(statuses[key], 0):
            statuses[key] = status
        if current == root:
            break
        current = current.parent


def _find_root(folder: Path, marker: str) -> Path | None:
    current = folder.resolve()
    for candidate in (current, *current.parents):
        if (candidate / marker).exists():
            return candidate
    return None


def is_metadata_path(folder: Path) -> bool:
    """VCS internals are data, not a working-tree location to status-scan."""
    try:
        parts = folder.resolve().parts
    except OSError:
        parts = Path(os.path.abspath(folder)).parts
    return any(part.casefold() in {".git", ".svn"} for part in parts)


def _git_status(folder: Path) -> dict[str, str] | None:
    root = _find_root(folder, ".git")
    if root is None:
        return None
    relative = os.path.relpath(folder, root)
    command = ["git", "-C", str(root), "status", "--porcelain=v1", "-z",
               "--untracked-files=all", "--", relative]
    result = subprocess.run(command, capture_output=True, timeout=4)
    if result.returncode:
        return {}
    statuses: dict[str, str] = {}
    tracked = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", relative],
                             capture_output=True, timeout=4)
    if tracked.returncode == 0:
        for raw_path in tracked.stdout.split(b"\0"):
            if raw_path:
                _merge(statuses, root / raw_path.decode("utf-8", "surrogateescape"),
                       "clean", root)
    records = result.stdout.split(b"\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if len(record) < 4:
            continue
        code = record[:2].decode("ascii", "replace")
        raw_path = record[3:].decode("utf-8", "surrogateescape")
        if "R" in code or "C" in code:
            index += 1  # porcelain -z adds the source name after the destination.
        status = ("conflict" if "U" in code or code in {"AA", "DD"} else
                  "untracked" if code == "??" else
                  "added" if "A" in code else
                  "deleted" if "D" in code else "modified")
        _merge(statuses, root / raw_path, status, root)
    return statuses


def _svn_status(folder: Path) -> dict[str, str] | None:
    root = _find_root(folder, ".svn")
    if root is None:
        return None
    try:
        result = subprocess.run(["svn", "status", "-v", "--xml", str(folder)],
                                capture_output=True, text=True, errors="replace", timeout=4)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode:
        return {}
    mapping = {"conflicted": "conflict", "added": "added", "unversioned": "untracked",
               "missing": "deleted", "deleted": "deleted", "modified": "modified",
               "replaced": "modified", "normal": "clean"}
    statuses: dict[str, str] = {}
    try:
        document = ET.fromstring(result.stdout)
    except ET.ParseError:
        return statuses
    for entry in document.findall(".//entry"):
        wc = entry.find("wc-status")
        if wc is None:
            continue
        status = mapping.get(wc.get("item", ""))
        if status:
            _merge(statuses, Path(entry.get("path", "")), status, root)
    return statuses


def folder_statuses(folder: Path) -> dict[str, str]:
    """Return Git/SVN overlay states keyed by normalized absolute path."""
    if is_metadata_path(folder):
        return {}
    key = os.path.normcase(str(folder.resolve()))
    cached = _CACHE.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < _CACHE_SECONDS:
        return cached[1]
    try:
        statuses = _git_status(folder)
        if statuses is None:
            statuses = _svn_status(folder)
        value = statuses or {}
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        value = {}
    _CACHE[key] = (now, value)
    return value


def status_for(statuses: dict[str, str], path: Path) -> str | None:
    try:
        key = os.path.normcase(str(path.resolve()))
    except OSError:
        key = os.path.normcase(os.path.abspath(path))
    return statuses.get(key)
