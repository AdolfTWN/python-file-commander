import tempfile
import unittest
import zipfile
import subprocess
from pathlib import Path

from pycommander.archivefs import ArchiveSession, _seven_zip_executable, is_browsable_archive


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
