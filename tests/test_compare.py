import tempfile
import unittest
from pathlib import Path

from pycommander.compare import aligned_text, detect_compare_type, file_hash, folder_rows


class CompareTests(unittest.TestCase):
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
