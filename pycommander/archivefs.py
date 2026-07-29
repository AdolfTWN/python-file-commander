from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


ARCHIVE_SUFFIXES = {".zip", ".7z"}


def is_browsable_archive(path: Path) -> bool:
    return path.is_file() and path.suffix.casefold() in ARCHIVE_SUFFIXES


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

    def __init__(self, archive_path: Path) -> None:
        self.archive_path = archive_path.expanduser().resolve()
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
                for info in archive.infolist():
                    destination = _safe_destination(self.root, info.filename)
                    if info.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, destination.open("wb") as target:
                        shutil.copyfileobj(source, target)
            return
        executable = _seven_zip_executable()
        if executable is None:
            raise OSError("7z browsing requires the 7-Zip command-line tool (7z or 7zz).")
        result = subprocess.run(
            [executable, "x", "-y", f"-o{self.root}", str(self.archive_path)],
            capture_output=True, text=True, errors="replace")
        if result.returncode:
            raise OSError(result.stderr.strip() or result.stdout.strip() or "7z extraction failed.")

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
