import tempfile
import unittest
import zipfile
from pathlib import Path

from pycommander.compare import (FolderCompare, aligned_text, compare_row_height,
                                 detect_compare_type, extract_compare_archive, file_hash,
                                 folder_rows, is_compare_archive, nested_source_label)


class CompareTests(unittest.TestCase):
    def test_compare_row_height_scales_without_clipping(self):
        self.assertEqual(compare_row_height(16, 1.0), 24)
        self.assertGreater(compare_row_height(32, 2.0), 32)
        self.assertGreater(compare_row_height(48, 3.0), compare_row_height(32, 2.0))

    def test_text_alignment_marks_changed_line(self):
        rows, differences = aligned_text("same\nold\n", "same\nnew\n")
        self.assertEqual(rows, [(1, "same", 1, "same"), (2, "old", 2, "new")])
        self.assertEqual(differences, [2])

    def test_inserted_line_has_no_left_line_number(self):
        rows, differences = aligned_text("one\nthree\n", "one\ntwo\nthree\n")
        self.assertEqual(rows, [(1, "one", 1, "one"), (None, "", 2, "two"), (2, "three", 3, "three")])
        self.assertEqual(differences, [2])

    def test_type_detection_and_hash(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            left, right = root / "a.txt", root / "b.txt"
            left.write_text("hello", encoding="utf-8"); right.write_text("hello", encoding="utf-8")
            self.assertEqual(detect_compare_type(left, right), "Text")
            self.assertEqual(file_hash(left), file_hash(right))

    def test_folder_statuses(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); left, right = root / "left", root / "right"
            left.mkdir(); right.mkdir()
            (left / "same.txt").write_text("same", encoding="utf-8")
            (right / "same.txt").write_text("same", encoding="utf-8")
            (left / "only.txt").write_text("left", encoding="utf-8")
            statuses = {(status, path) for status, path, _, _ in folder_rows(left, right, by_content=True)}
            self.assertIn(("Identical", "same.txt"), statuses)
            self.assertIn(("Left only", "only.txt"), statuses)

    def test_folder_compare_skips_git_and_svn_metadata(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); left, right = root / "left", root / "right"
            left.mkdir(); right.mkdir(); (left / ".git").mkdir(); (right / ".svn").mkdir()
            (left / ".git" / "index").write_bytes(b"internal")
            (right / ".svn" / "wc.db").write_bytes(b"internal")
            (left / "visible.txt").write_text("same", encoding="utf-8")
            (right / "visible.txt").write_text("same", encoding="utf-8")
            rows = list(folder_rows(left, right, by_content=True))
            names = {relative for _status, relative, *_rest in rows}
            self.assertIn("visible.txt", names)
            self.assertFalse(any(".git" in name or ".svn" in name for name in names))

    def test_zip_is_a_folder_compare_source(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); folder = root / "folder"; folder.mkdir()
            (folder / "same.txt").write_text("same", encoding="utf-8")
            archive_path = root / "folder.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.write(folder / "same.txt", "same.txt")
            self.assertTrue(is_compare_archive(archive_path))
            self.assertEqual(detect_compare_type(folder, archive_path), "Folder")
            workspace, extracted = extract_compare_archive(archive_path)
            try:
                rows = list(folder_rows(folder, extracted, by_content=True))
                self.assertIn(("Identical", "same.txt"), {(status, path) for status, path, *_ in rows})
            finally:
                workspace.cleanup()

    def test_nested_compare_uses_logical_folder_and_archive_paths(self):
        relative = str(Path("logs") / "today.txt")
        self.assertEqual(nested_source_label(Path(r"C:\work\left"), relative),
                         str(Path(r"C:\work\left") / relative))
        self.assertEqual(nested_source_label(Path(r"C:\work\right.zip"), relative),
                         rf"C:\work\right.zip :: {relative}")

    def test_archive_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            archive_path = Path(raw) / "unsafe.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../outside.txt", "unsafe")
            with self.assertRaises(OSError):
                extract_compare_archive(archive_path)

    def test_diff_presets_cover_beyond_compare_workflows(self):
        self.assertIn("Identical", FolderCompare.DIFF_FILTERS["no_orphans"])
        self.assertNotIn("Left only", FolderCompare.DIFF_FILTERS["differences_no_orphans"])
        self.assertEqual(FolderCompare.DIFF_FILTERS["left_newer_orphans"],
                         {"Left newer", "Left only"})

    def test_folder_compare_filters_depth_and_newer_status(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); left, right = root / "left", root / "right"
            left.mkdir(); right.mkdir(); (left / "nested").mkdir(); (right / "nested").mkdir()
            old, new = left / "report.txt", right / "report.txt"
            old.write_text("same size", encoding="utf-8"); new.write_text("different", encoding="utf-8")
            old.touch(); new.touch()
            old_stat = old.stat(); new_time = old_stat.st_mtime + 10
            import os
            os.utime(new, (new_time, new_time))
            (left / "nested" / "inside.log").write_text("log", encoding="utf-8")
            rows = list(folder_rows(left, right, recursive=False, masks="*.txt"))
            self.assertIn(("Right newer", "report.txt"), {(status, path) for status, path, *_ in rows})
            self.assertNotIn("nested\\inside.log", {path for _status, path, *_ in rows})
            recursive = list(folder_rows(left, right, recursive=True, masks="*.log"))
            self.assertIn(str(Path("nested") / "inside.log"), {path for _status, path, *_ in recursive})


if __name__ == "__main__":
    unittest.main()
