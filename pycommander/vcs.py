from __future__ import annotations

import os
import subprocess
import time
import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from .vcsactions import vcs_cli


_CACHE: dict[str, tuple[float, dict[str, str]]] = {}
_CACHE_COVERAGE: set[str] = set()
_VCS_CACHE_LOCK = threading.Lock()
_VCS_CACHE_EPOCH = 0
_CACHE_SECONDS = 3.0
_DISPLAY_CACHE_SECONDS = 30.0
_VCS_CACHE_LIMIT = 128
_PRIORITY = {"conflict": 5, "modified": 4, "added": 3, "untracked": 2,
             "deleted": 1, "clean": 0}


def invalidate_vcs_cache():
    """A client dialog finished; the next overlay request must use fresh metadata."""
    global _VCS_CACHE_EPOCH
    with _VCS_CACHE_LOCK:
        _VCS_CACHE_EPOCH += 1
        _CACHE.clear()
        _CACHE_COVERAGE.clear()


def _run_options() -> dict:
    """Keep background VCS commands invisible in Windows GUI launches."""
    env = os.environ.copy()
    env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0), "env": env}


def _overlay_cli(kind: str) -> str:
    executable = vcs_cli(kind)
    if executable is None:
        raise OSError("Version control command-line tool is unavailable.")
    return executable


def _merge(statuses: dict[str, str], path: Path, status: str, root: Path) -> None:
    # Git reports paths relative to an already resolved worktree. Resolving
    # every tracked file repeats filesystem/reparse-point calls and incorrectly
    # attaches a tracked symlink's overlay to its target instead of the link.
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


def _git_code_status(code: str) -> str:
    return ("conflict" if "U" in code or code in {"AA", "DD"} else
            "untracked" if code == "??" else
            "added" if "A" in code else
            "deleted" if "D" in code else "modified")


def _git_root_summary(root: Path) -> str | None:
    """Return one overlay state for a repository root shown from its parent."""
    try:
        result = subprocess.run(
            [_overlay_cli("git"), "-C", str(root), "status", "--porcelain=v1", "--branch", "-z",
             "--untracked-files=all"], capture_output=True, timeout=4, **_run_options())
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return None
    if result.returncode:
        return None
    summary = "clean"
    records = result.stdout.split(b"\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if record.startswith(b"## "):
            if b"[ahead " in record or b"[behind " in record:
                summary = "modified"
            continue
        if len(record) < 4:
            continue
        code = record[:2].decode("ascii", "replace")
        if "R" in code or "C" in code:
            index += 1
        status = _git_code_status(code)
        if _PRIORITY[status] > _PRIORITY[summary]:
            summary = status
    return summary


def _child_repository_statuses(folder: Path) -> dict[str, str]:
    """Expose direct child repository roots without recursively scanning folders."""
    statuses: dict[str, str] = {}
    deadline = time.monotonic() + 8.0
    try:
        children = tuple(folder.iterdir())
    except OSError:
        return statuses
    for child in children:
        if time.monotonic() >= deadline:
            break  # Unqueried repositories remain unknown, not clean.
        try:
            if not child.is_dir():
                continue
            if (child / ".git").exists():
                status = _git_root_summary(child)
            elif (child / ".svn").exists():
                nested = _svn_status(child)
                status = status_for(nested or {}, child)
            else:
                continue
            if status is not None:
                statuses[os.path.normcase(str(child.resolve()))] = status
        except OSError:
            continue
    return statuses


def _git_status(folder: Path) -> dict[str, str] | None:
    root = _find_root(folder, ".git")
    if root is None:
        return None
    relative = os.path.relpath(folder, root)
    command = [_overlay_cli("git"), "-C", str(root), "status", "--porcelain=v1", "-z",
               "--untracked-files=all", "--", relative]
    result = subprocess.run(command, capture_output=True, timeout=4, **_run_options())
    if result.returncode:
        return {}
    statuses: dict[str, str] = {}
    tracked = subprocess.run([_overlay_cli("git"), "-C", str(root), "ls-files", "-z", "--", relative],
                             capture_output=True, timeout=4, **_run_options())
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
        status = _git_code_status(code)
        _merge(statuses, root / raw_path, status, root)
    return statuses


def _svn_status(folder: Path) -> dict[str, str] | None:
    root = _find_root(folder, ".svn")
    if root is None:
        return None
    try:
        result = subprocess.run([_overlay_cli("svn"), "status", "-v", "--xml", str(folder)],
                                capture_output=True, text=True, errors="replace", timeout=4,
                                **_run_options())
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
    folder = folder.resolve()
    key = os.path.normcase(str(folder))
    with _VCS_CACHE_LOCK:
        epoch = _VCS_CACHE_EPOCH
    inherited = cached_folder_statuses(folder, max_age=_CACHE_SECONDS)
    if inherited is not None:
        return inherited
    try:
        statuses = _git_status(folder)
        if statuses is None:
            statuses = _svn_status(folder)
        covered = statuses is not None
        value = statuses or {}
        # A directly contained repository remains its own status boundary even
        # when the folder being viewed is itself inside another work tree.
        # This also covers nested repositories that are not registered as Git
        # submodules.
        value.update(_child_repository_statuses(folder))
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        value = {}
        covered = False
    with _VCS_CACHE_LOCK:
        if epoch == _VCS_CACHE_EPOCH:
            completed = time.monotonic()
            for old_key, (timestamp, _) in list(_CACHE.items()):
                if completed - timestamp >= _DISPLAY_CACHE_SECONDS:
                    del _CACHE[old_key]
                    _CACHE_COVERAGE.discard(old_key)
            _CACHE[key] = (completed, value)
            _CACHE_COVERAGE.discard(key)
            if covered:
                _CACHE_COVERAGE.add(key)
            while len(_CACHE) > _VCS_CACHE_LIMIT:
                oldest = min(_CACHE, key=lambda item: _CACHE[item][0])
                del _CACHE[oldest]
                _CACHE_COVERAGE.discard(oldest)
    return value


def cached_folder_statuses(folder: Path, *, max_age=_DISPLAY_CACHE_SECONDS) -> dict[str, str] | None:
    """Last-known overlays for immediate paint; no CLI, no fabricated clean state.

    Ancestor status scans cover descendants, but a parent-folder repository
    summary does not. Never inherit across nested worktrees or VCS internals.
    Background queries use the shorter freshness TTL, not the display TTL.
    """
    folder = Path(os.path.abspath(folder))
    if any(part.casefold() in {'.git', '.svn'} for part in folder.parts):
        return None
    now = time.monotonic()
    with _VCS_CACHE_LOCK:
        entries, coverage, epoch = dict(_CACHE), set(_CACHE_COVERAGE), _VCS_CACHE_EPOCH
    if not entries:
        return None
    for candidate in (folder, *folder.parents):
        key = os.path.normcase(str(candidate))
        cached = entries.get(key)
        if cached and now - cached[0] < max_age and (candidate == folder or key in coverage):
            # Only inspect boundaries when a usable ancestor snapshot exists.
            # Unrelated folders must not acquire synchronous marker probes just
            # because some other pane has populated the global cache.
            for boundary in (folder, *folder.parents):
                if boundary == candidate:
                    break
                if (boundary / '.git').exists() or (boundary / '.svn').exists():
                    return None
            with _VCS_CACHE_LOCK:
                return cached[1] if epoch == _VCS_CACHE_EPOCH else None
    return None


def status_for(statuses: dict[str, str], path: Path) -> str | None:
    key = os.path.normcase(os.path.abspath(path))
    return statuses.get(key)
