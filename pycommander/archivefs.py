from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import zipfile
import hashlib
import stat
from pathlib import Path, PurePosixPath
from typing import Callable
from .fileops import filesystem_path


ARCHIVE_SUFFIXES = {".zip", ".7z"}
ProgressCallback = Callable[[int, int, str], None]


class ArchiveCancelled(OSError):
    pass


def _mkdir(path: Path) -> None:
    os.makedirs(filesystem_path(path), exist_ok=True)


def is_browsable_archive(path: Path) -> bool:
    return path.is_file() and path.suffix.casefold() in ARCHIVE_SUFFIXES


def archive_item_counts(path: Path) -> tuple[int, int]:
    """Return root-level folder/file counts without extracting.

    This describes the extraction layout rather than every item in the
    archive.  ``release/docs/readme.md`` therefore has one root folder
    (``release``), not several loose folders/files.
    """
    path = Path(path).expanduser().resolve()
    roots: dict[str, bool] = {}

    def add_member(raw_name: str, is_folder: bool) -> None:
        member = PurePosixPath(raw_name.replace("\\", "/"))
        parts = [part for part in member.parts if part not in {"", "."}]
        if not parts:
            return
        # When no explicit folder entry exists, a nested member still proves
        # that its first component is a root folder.
        key = parts[0].casefold()
        roots[key] = roots.get(key, False) or is_folder or len(parts) > 1

    def result() -> tuple[int, int]:
        folders = sum(1 for is_folder in roots.values() if is_folder)
        return folders, len(roots) - folders

    if path.suffix.casefold() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                add_member(info.filename, info.is_dir())
        return result()

    executable = _seven_zip_executable()
    if executable is None:
        raise OSError("7z listing requires the 7-Zip command-line tool (7z or 7zz).")
    listing = subprocess.run([executable, "l", "-slt", "--", str(path)], capture_output=True,
                             stdin=subprocess.DEVNULL, timeout=30,
                             text=True, errors="replace", **_hidden_process_options())
    if listing.returncode:
        raise OSError(listing.stderr.strip() or listing.stdout.strip() or
                      "Unable to read 7z archive.")
    blocks = listing.stdout.replace("\r\n", "\n").split("\n\n")[1:]
    for block in blocks:
        fields = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
        name = fields.get("Path")
        if name:
            add_member(name, fields.get("Folder") == "+" or "D" in fields.get("Attributes", ""))
    return result()


def _hidden_process_options() -> dict:
    return ({"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
            if os.name == "nt" else {})


def _zip_input_manifest(paths):
    """Snapshot metadata once per operation, retaining selected-root order.

    The manifest is not a cross-operation cache. ZipFile.write still stats and
    reads each file freshly; content is never cached. Directory emptiness is
    inferred from enumeration where possible, with a fallback for directory
    links that rglob does not descend into.
    """
    records, writable, total = [], [], 0
    for item in paths:
        info = item.stat()
        is_folder = stat.S_ISDIR(info.st_mode)
        descendants = sorted(item.rglob("*")) if is_folder else []
        parents = {child.parent for child in descendants}
        entries = [(item, item.name, info)]
        entries.extend((child, (Path(item.name) / child.relative_to(item)).as_posix(), child.stat())
                       for child in descendants)
        for path, name, metadata in entries:
            folder = stat.S_ISDIR(metadata.st_mode)
            records.append((name, 0, folder, 0))
            if stat.S_ISREG(metadata.st_mode):
                total += metadata.st_size
            if not folder or (path not in parents and not any(path.iterdir())):
                writable.append((path, name, folder))
    return records, writable, max(1, total)


def create_zip_archive(items, target: Path,
                       progress: ProgressCallback | None = None) -> Path:
    """Create a ZIP containing each selected item under its own display name."""
    paths = [Path(item) for item in items]
    if not paths:
        raise OSError("No items are selected for compression.")
    target = Path(target).absolute()
    for item in paths:
        if not item.exists():
            raise OSError("A selected compression item no longer exists.")
        if (target.resolve() == item.resolve() or
                (item.is_dir() and item.resolve() in target.resolve().parents) or
                (target.exists() and item.is_file() and os.path.samefile(item, target))):
            raise OSError("The output archive cannot replace or be inside a selected input.")
    expected = _archive_destination_state(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    records, writable, total = _zip_input_manifest(paths)
    _validate_archive_records(records)
    completed = 0
    fd, raw = tempfile.mkstemp(prefix=".pfc-zip-", dir=target.parent)
    os.close(fd)
    staging = Path(raw)
    try:
        with zipfile.ZipFile(staging, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, name, is_folder in writable:
                if is_folder:
                    archive.writestr(name.rstrip("/") + "/", b"")
                else:
                    archive.write(path, name)
                    completed += archive.getinfo(name).file_size
                    if progress:
                        progress(completed, total, path.name)
        with staging.open("rb+") as stream:
            os.fsync(stream.fileno())
        if _archive_destination_state(target) != expected:
            raise OSError("The output archive changed during compression; it was not overwritten.")
        os.replace(staging, target)
    finally:
        staging.unlink(missing_ok=True)
    if progress:
        progress(total, total, target.name)
    return target


def _archive_destination_state(path: Path):
    if not os.path.lexists(path):
        return None
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
        raise OSError("An archive output must be a regular, unlinked file.")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _archive_fingerprint(path: Path):
    state = _archive_destination_state(path)
    if state is None:
        raise OSError("The original archive no longer exists.")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if _archive_destination_state(path) != state:
        raise OSError("The archive changed while it was being read.")
    return state, digest.digest()


def extract_archive_to(archive_path: Path, destination: Path,
                       progress: ProgressCallback | None = None) -> Path:
    """Safely extract ZIP/7z directly, avoiding long temporary copy paths."""
    archive_path = archive_path.expanduser().resolve()
    _mkdir(destination)
    if archive_path.suffix.casefold() == ".zip":
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            _validate_archive_records([(i.filename, i.file_size, i.is_dir(), i.external_attr >> 16)
                                       for i in members])
            targets = [_safe_destination(destination.resolve(), info.filename) for info in members]
            if any(target == archive_path for target in targets):
                raise OSError("Extraction cannot replace the archive being read.")
            total = max(1, sum(info.file_size for info in members if not info.is_dir()))
            completed = 0
            for info, target in zip(members, targets):
                if info.is_dir():
                    _mkdir(target)
                    continue
                _mkdir(target.parent)
                fd, raw = tempfile.mkstemp(prefix=".pfc-extract-", dir=filesystem_path(target.parent))
                staging = Path(raw)
                try:
                    with os.fdopen(fd, "wb") as output, archive.open(info) as source:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            output.write(chunk)
                            completed += len(chunk)
                            if progress:
                                progress(completed, total, Path(info.filename).name)
                        output.flush()
                        os.fsync(output.fileno())
                    os.replace(staging, filesystem_path(target))
                finally:
                    staging.unlink(missing_ok=True)
        if progress:
            progress(total, total, archive_path.name)
        return destination
    # External extractors operate only inside an owned workspace. Publication
    # uses the same validated destinations and per-file staging as ZIP.
    session = ArchiveSession(archive_path, progress=progress)
    try:
        children = sorted(session.root.rglob("*"))
        targets = [(source, _safe_destination(destination.resolve(), source.relative_to(session.root).as_posix()))
                   for source in children]
        if any(target == archive_path for _, target in targets):
            raise OSError("Extraction cannot replace the archive being read.")
        for source, target in targets:
            if source.is_dir():
                _mkdir(target)
            else:
                _mkdir(target.parent)
                fd, raw = tempfile.mkstemp(prefix=".pfc-extract-", dir=filesystem_path(target.parent))
                os.close(fd)
                staging = Path(raw)
                try:
                    shutil.copyfile(source, staging)
                    os.replace(staging, filesystem_path(target))
                finally:
                    staging.unlink(missing_ok=True)
        return destination
    finally:
        session.close()


def _seven_zip_executable() -> str | None:
    candidates = ("7z", "7zz", "7za")
    for name in candidates:
        if os.name == "nt":
            executable = next((found for entry in os.environ.get("PATH", "").split(os.pathsep)
                               if entry and Path(entry).is_absolute()
                               for found in [shutil.which(str(Path(entry) / (name + ".exe")))] if found), None)
        else:
            executable = shutil.which(name)
        if executable:
            return executable
    if os.name == "nt":
        for raw in (r"C:\Program Files\7-Zip\7z.exe",
                    r"C:\Program Files (x86)\7-Zip\7z.exe"):
            if Path(raw).is_file():
                return raw
    return None


def _safe_member_parts(member_name: str):
    member = PurePosixPath(member_name.replace("\\", "/"))
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{n}" for p in ("COM", "LPT") for n in "123456789¹²³"}
    if (member.is_absolute() or ".." in member.parts or not member.parts or
            any(part.endswith((".", " ")) or part.split(".")[0].upper() in reserved or
                any(ord(c) < 32 or c in '<>:"|?*' for c in part) for part in member.parts)):
        raise OSError(f"Unsafe archive item: {member_name}")
    return member.parts


def _safe_destination(root: Path, member_name: str) -> Path:
    destination = root.joinpath(*_safe_member_parts(member_name)).resolve()
    if destination != root and root not in destination.parents:
        raise OSError(f"Unsafe archive item: {member_name}")
    return destination


def _validate_archive_records(records) -> None:
    names, files = set(), set()
    for name, size, directory, mode in records:
        _safe_member_parts(name)
        if size < 0 or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise OSError("Archive contains links or special files.")
        key = PurePosixPath(name.replace("\\", "/")).as_posix().rstrip("/").casefold()
        if key in names:
            raise OSError("Duplicate or case-colliding archive member.")
        names.add(key)
        if not directory:
            files.add(key)
    for name in names:
        if any(parent.as_posix().casefold() in files for parent in PurePosixPath(name).parents if str(parent) != "."):
            raise OSError("Archive contains a file/folder path collision.")


def _validated_seven_zip_members(path: Path, executable: str) -> None:
    try:
        listing = subprocess.run([executable, "l", "-slt", "--", str(path)], stdin=subprocess.DEVNULL,
                                 capture_output=True, text=True, errors="replace", timeout=30,
                                 **_hidden_process_options())
    except subprocess.TimeoutExpired as exc:
        raise OSError("Archive listing timed out.") from exc
    if listing.returncode:
        raise OSError("Cannot list this archive; encrypted or unsupported archives cannot be opened.")
    body = listing.stdout.partition("----------")[2]
    if not body:
        raise OSError("Cannot validate the archive member listing.")
    records = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        fields = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
        if "Path" not in fields:
            continue
        if (fields.get("Encrypted") == "+" or fields.get("Symbolic Link") or
                fields.get("Hard Link") or "Reparse" in fields.get("Attributes", "")):
            raise OSError("Archive contains encryption or links.")
        try:
            size = int(fields.get("Size", "0"))
        except ValueError as exc:
            raise OSError("Invalid archive member size.") from exc
        records.append((fields["Path"], size, fields.get("Folder") == "+" or "D" in fields.get("Attributes", ""), 0))
    _validate_archive_records(records)


class ArchiveSession:
    """Editable extracted workspace backed by one ZIP or 7z file."""

    def __init__(self, archive_path: Path,
                 cancel_event: threading.Event | None = None,
                 progress: ProgressCallback | None = None) -> None:
        selected = archive_path.expanduser().absolute()
        if selected.is_symlink():
            raise OSError("Linked archives cannot be edited in place.")
        self.archive_path = selected.resolve()
        self.cancel_event = cancel_event
        self.progress = progress
        if not is_browsable_archive(self.archive_path):
            raise OSError(f"Unsupported archive: {self.archive_path.name}")
        self._temporary = tempfile.TemporaryDirectory(prefix="pfc-archive-")
        self.root = Path(self._temporary.name).resolve()
        try:
            self._original_fingerprint = _archive_fingerprint(self.archive_path)
            self._extract()
            self._check_original()
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
                _validate_archive_records([(i.filename, i.file_size, i.is_dir(), i.external_attr >> 16)
                                           for i in members])
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
        _validated_seven_zip_members(self.archive_path, executable)
        self._check_cancelled()
        process = subprocess.Popen(
            [executable, "x", "-y", "-bso0", "-bsp0", "-bse1",
             f"-o{filesystem_path(self.root)}", str(self.archive_path)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
            **_hidden_process_options())
        started = __import__("time").monotonic()
        try:
            if self.progress:
                self.progress(0, 0, self.archive_path.name)
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=0.15)
                    break
                except subprocess.TimeoutExpired:
                    if ((self.cancel_event is not None and self.cancel_event.is_set()) or
                            __import__("time").monotonic() - started > 180):
                        raise ArchiveCancelled("Archive opening cancelled or timed out.")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
        if process.returncode:
            raise OSError(stderr.strip() or stdout.strip() or "7z extraction failed.")
        if self.progress:
            self.progress(100, 100, self.archive_path.name)

    def _check_cancelled(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise ArchiveCancelled("Archive opening cancelled.")

    def commit(self) -> None:
        self._check_original()
        # A draft is owned temporary storage, never a gateway to external links.
        entries, pending = [], [self.root]
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as children:
                for child in children:
                    info = child.stat(follow_symlinks=False)
                    if (child.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400 or
                            (stat.S_ISREG(info.st_mode) and info.st_nlink > 1) or
                            not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode))):
                        raise OSError("Archive drafts cannot contain links or special files.")
                    path = Path(child.path)
                    entries.append(path)
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(path)
        _validate_archive_records([(path.relative_to(self.root).as_posix(), 0, path.is_dir(), 0) for path in entries])
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
                    for path in sorted(entries):
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
                    cwd=self.root, stdin=subprocess.DEVNULL, timeout=180,
                    capture_output=True, text=True, errors="replace", **_hidden_process_options())
                if result.returncode:
                    raise OSError(result.stderr.strip() or result.stdout.strip() or "7z update failed.")
            self._check_original()
            os.replace(temporary, self.archive_path)
            self._original_fingerprint = _archive_fingerprint(self.archive_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _check_original(self) -> None:
        if _archive_fingerprint(self.archive_path) != self._original_fingerprint:
            raise OSError("The original archive changed outside PFC. The draft was preserved; reopen before saving.")

    def close(self) -> None:
        self._temporary.cleanup()
