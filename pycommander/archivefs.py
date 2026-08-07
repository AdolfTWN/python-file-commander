from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable


ARCHIVE_SUFFIXES = {".zip", ".7z"}
ProgressCallback = Callable[[int, int, str], None]


class ArchiveCancelled(OSError):
    pass


def filesystem_path(path: Path) -> str:
    """Return a Windows extended-length path without changing its logical value."""
    raw = str(Path(path).absolute())
    if os.name != "nt" or raw.startswith("\\\\?\\"):
        return raw
    if raw.startswith("\\\\"):
        return "\\\\?\\UNC\\" + raw[2:]
    return "\\\\?\\" + raw


def _mkdir(path: Path) -> None:
    os.makedirs(filesystem_path(path), exist_ok=True)


def is_browsable_archive(path: Path) -> bool:
    return path.is_file() and path.suffix.casefold() in ARCHIVE_SUFFIXES


def create_zip_archive(items, target: Path,
                       progress: ProgressCallback | None = None) -> Path:
    """Create a ZIP containing each selected item under its own display name."""
    paths = [Path(item) for item in items]
    if not paths:
        raise OSError("No items are selected for compression.")
    target.parent.mkdir(parents=True, exist_ok=True)
    files = [child for item in paths for child in
             ([item] if item.is_file() else [p for p in item.rglob("*") if p.is_file()])]
    total = max(1, sum(path.stat().st_size for path in files))
    completed = 0
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in paths:
            if item.is_dir():
                descendants = sorted(item.rglob("*"))
                if not descendants:
                    archive.writestr(item.name.rstrip("/") + "/", b"")
                for child in descendants:
                    relative = Path(item.name) / child.relative_to(item)
                    if child.is_dir():
                        if not any(child.iterdir()):
                            archive.writestr(relative.as_posix().rstrip("/") + "/", b"")
                    else:
                        archive.write(child, relative.as_posix())
                        completed += child.stat().st_size
                        if progress:
                            progress(completed, total, child.name)
            else:
                archive.write(item, item.name)
                completed += item.stat().st_size
                if progress:
                    progress(completed, total, item.name)
    if progress:
        progress(total, total, target.name)
    return target


def extract_archive_to(archive_path: Path, destination: Path,
                       progress: ProgressCallback | None = None) -> Path:
    """Safely extract ZIP/7z directly, avoiding long temporary copy paths."""
    archive_path = archive_path.expanduser().resolve()
    _mkdir(destination)
    if archive_path.suffix.casefold() == ".zip":
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            total = max(1, sum(info.file_size for info in members if not info.is_dir()))
            completed = 0
            for info in members:
                target = _safe_destination(destination.resolve(), info.filename)
                if info.is_dir():
                    _mkdir(target)
                    continue
                _mkdir(target.parent)
                with archive.open(info) as source, open(filesystem_path(target), "wb") as output:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        completed += len(chunk)
                        if progress:
                            progress(completed, total, Path(info.filename).name)
        if progress:
            progress(total, total, archive_path.name)
        return destination
    executable = _seven_zip_executable()
    if executable is None:
        raise OSError("7z extraction requires the 7-Zip command-line tool (7z or 7zz).")
    listing = subprocess.run([executable, "l", "-slt", str(archive_path)],
                             capture_output=True, text=True, errors="replace")
    if listing.returncode:
        raise OSError(listing.stderr.strip() or listing.stdout.strip() or "Unable to read 7z archive.")
    members = [line[7:] for line in listing.stdout.splitlines() if line.startswith("Path = ")][1:]
    for member in members:
        _safe_destination(destination.resolve(), member)
    process = subprocess.Popen(
        [executable, "x", "-y", "-bso0", "-bse1", "-bsp1",
         f"-o{filesystem_path(destination)}", str(archive_path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")
    output = ""
    assert process.stdout is not None
    while True:
        character = process.stdout.read(1)
        if not character:
            break
        output = (output + character)[-200:]
        if character in {"%", "\r", "\n"}:
            import re
            matches = re.findall(r"(\d{1,3})%", output)
            if matches and progress:
                percent = min(100, int(matches[-1]))
                progress(percent, 100, archive_path.name)
    _stdout, stderr = process.communicate()
    if process.returncode:
        raise OSError(stderr.strip() or output.strip() or "7z extraction failed.")
    if progress:
        progress(100, 100, archive_path.name)
    return destination


def _seven_zip_executable() -> str | None:
    candidates = ("7z", "7zz", "7za")
    for name in candidates:
        executable = shutil.which(name)
        if executable:
            return executable
    if os.name == "nt":
        for raw in (r"C:\Program Files\7-Zip\7z.exe",
                    r"C:\Program Files (x86)\7-Zip\7z.exe"):
            if Path(raw).is_file():
                return raw
    return None


def _safe_destination(root: Path, member_name: str) -> Path:
    member = PurePosixPath(member_name.replace("\\", "/"))
    if member.is_absolute() or ".." in member.parts:
        raise OSError(f"Unsafe archive item: {member_name}")
    destination = root.joinpath(*member.parts).resolve()
    if destination != root and root not in destination.parents:
        raise OSError(f"Unsafe archive item: {member_name}")
    return destination


class ArchiveSession:
    """Editable extracted workspace backed by one ZIP or 7z file."""

    def __init__(self, archive_path: Path,
                 cancel_event: threading.Event | None = None,
                 progress: ProgressCallback | None = None) -> None:
        self.archive_path = archive_path.expanduser().resolve()
        self.cancel_event = cancel_event
        self.progress = progress
        if not is_browsable_archive(self.archive_path):
            raise OSError(f"Unsupported archive: {self.archive_path.name}")
        self._temporary = tempfile.TemporaryDirectory(prefix="pfc-archive-")
        self.root = Path(self._temporary.name).resolve()
        try:
            self._extract()
        except Exception:
            self._temporary.cleanup()
            raise

    @property
    def kind(self) -> str:
        return self.archive_path.suffix.casefold()

    def contains(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = Path(os.path.abspath(path))
        return resolved == self.root or self.root in resolved.parents

    def relative_path(self, path: Path) -> Path:
        return path.resolve().relative_to(self.root)

    def display_path(self, path: Path) -> str:
        relative = self.relative_path(path)
        return str(self.archive_path) if not relative.parts else f"{self.archive_path}{os.sep}{relative}"

    def _extract(self) -> None:
        if self.kind == ".zip":
            with zipfile.ZipFile(self.archive_path) as archive:
                members = archive.infolist()
                total = max(1, sum(info.file_size for info in members if not info.is_dir()))
                completed = 0
                for info in members:
                    self._check_cancelled()
                    destination = _safe_destination(self.root, info.filename)
                    if info.is_dir():
                        _mkdir(destination)
                        continue
                    _mkdir(destination.parent)
                    with archive.open(info) as source, open(filesystem_path(destination), "wb") as target:
                        while True:
                            self._check_cancelled()
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            target.write(chunk)
                            completed += len(chunk)
                            if self.progress:
                                self.progress(completed, total, Path(info.filename).name)
            if self.progress:
                self.progress(total, total, self.archive_path.name)
            return
        executable = _seven_zip_executable()
        if executable is None:
            raise OSError("7z browsing requires the 7-Zip command-line tool (7z or 7zz).")
        process = subprocess.Popen(
            [executable, "x", "-y", "-bso0", "-bsp0", "-bse1",
             f"-o{filesystem_path(self.root)}", str(self.archive_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")
        started = __import__("time").monotonic()
        last_percent = 0
        if self.progress:
            self.progress(1, 100, self.archive_path.name)
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.15)
                break
            except subprocess.TimeoutExpired:
                if self.progress:
                    elapsed = __import__("time").monotonic() - started
                    percent = min(90, 1 + int(elapsed * 2))
                    if percent > last_percent:
                        last_percent = percent
                        self.progress(percent, 100, self.archive_path.name)
                if self.cancel_event is not None and self.cancel_event.is_set():
                    process.terminate()
                    try:
                        process.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.communicate()
                    raise ArchiveCancelled("Archive opening cancelled.")
        if process.returncode:
            raise OSError(stderr.strip() or stdout.strip() or "7z extraction failed.")
        if self.progress:
            self.progress(100, 100, self.archive_path.name)

    def _check_cancelled(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise ArchiveCancelled("Archive opening cancelled.")

    def commit(self) -> None:
        suffix = self.archive_path.suffix
        descriptor, raw_temporary = tempfile.mkstemp(
            prefix=f".{self.archive_path.stem}.pfc-", suffix=suffix,
            dir=self.archive_path.parent)
        os.close(descriptor)
        temporary = Path(raw_temporary)
        temporary.unlink(missing_ok=True)
        try:
            if self.kind == ".zip":
                with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for path in sorted(self.root.rglob("*")):
                        relative = path.relative_to(self.root).as_posix()
                        if path.is_dir():
                            if not any(path.iterdir()):
                                archive.writestr(relative.rstrip("/") + "/", b"")
                        else:
                            archive.write(path, relative)
            else:
                executable = _seven_zip_executable()
                if executable is None:
                    raise OSError("7z writing requires the 7-Zip command-line tool (7z or 7zz).")
                result = subprocess.run(
                    [executable, "a", "-t7z", "-mx=5", str(temporary), "."],
                    cwd=self.root, capture_output=True, text=True, errors="replace")
                if result.returncode:
                    raise OSError(result.stderr.strip() or result.stdout.strip() or "7z update failed.")
            os.replace(temporary, self.archive_path)
        finally:
            temporary.unlink(missing_ok=True)

    def close(self) -> None:
        self._temporary.cleanup()
