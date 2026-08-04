import tempfile
import threading
import unittest
import zipfile
import subprocess
from pathlib import Path

from pycommander.archivefs import (ArchiveCancelled, ArchiveSession,
                                   _seven_zip_executable, create_zip_archive,
                                   extract_archive_to, is_browsable_archive)


class ArchiveSessionTests(unittest.TestCase):
    def test_zip_is_browsable_and_changes_are_rewritten(self):
        with tempfile.TemporaryDirectory() as raw:
            archive_path = Path(raw) / "sample.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("folder/original.txt", "original")

            self.assertTrue(is_browsable_archive(archive_path))
            session = ArchiveSession(archive_path)
            try:
                original = session.root / "folder" / "original.txt"
                self.assertEqual(original.read_text(), "original")
                original.unlink()
                (session.root / "added.txt").write_text("added", encoding="utf-8")
                session.commit()
            finally:
                session.close()

            with zipfile.ZipFile(archive_path) as archive:
                self.assertEqual(set(archive.namelist()), {"added.txt", "folder/"})
                self.assertEqual(archive.read("added.txt"), b"added")

    def test_zip_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as raw:
            archive_path = Path(raw) / "unsafe.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../outside.txt", "unsafe")
            with self.assertRaises(OSError):
                ArchiveSession(archive_path)
            self.assertFalse((Path(raw) / "outside.txt").exists())

    def test_open_can_be_cancelled_before_extraction(self):
        with tempfile.TemporaryDirectory() as raw:
            archive_path = Path(raw) / "sample.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("file.txt", "content")
            cancelled = threading.Event()
            cancelled.set()
            with self.assertRaises(ArchiveCancelled):
                ArchiveSession(archive_path, cancelled)

    def test_create_and_extract_zip_preserves_selected_roots(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            folder = root / "folder"; folder.mkdir()
            (folder / "nested.txt").write_text("nested", encoding="utf-8")
            file_path = root / "single.txt"; file_path.write_text("single", encoding="utf-8")
            archive_path = root / "bundle.zip"
            create_zip_archive([folder, file_path], archive_path)
            with zipfile.ZipFile(archive_path) as archive:
                self.assertEqual(set(archive.namelist()), {"folder/nested.txt", "single.txt"})
            destination = root / "extracted"
            extract_archive_to(archive_path, destination)
            self.assertEqual((destination / "folder" / "nested.txt").read_text(), "nested")
            self.assertEqual((destination / "single.txt").read_text(), "single")

    @unittest.skipUnless(_seven_zip_executable(), "7-Zip command-line tool is unavailable")
    def test_7z_is_extracted_and_rewritten(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            source.mkdir()
            (source / "original.txt").write_text("original", encoding="utf-8")
            archive_path = root / "sample.7z"
            subprocess.run(
                [_seven_zip_executable(), "a", str(archive_path), "."],
                cwd=source, check=True, capture_output=True)

            session = ArchiveSession(archive_path)
            try:
                (session.root / "original.txt").unlink()
                (session.root / "added.txt").write_text("added", encoding="utf-8")
                session.commit()
            finally:
                session.close()

            verify = ArchiveSession(archive_path)
            try:
                self.assertFalse((verify.root / "original.txt").exists())
                self.assertEqual((verify.root / "added.txt").read_text(), "added")
            finally:
                verify.close()


if __name__ == "__main__":
    unittest.main()
