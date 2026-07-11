import tempfile
import unittest
from pathlib import Path

from pycommander.compare import aligned_text, detect_compare_type, file_hash, folder_rows


class CompareTests(unittest.TestCase):
    def test_text_alignment_marks_changed_line(self):
        rows, differences = aligned_text("same\nold\n", "same\nnew\n")
        self.assertEqual(rows, [("same", "same"), ("old", "new")])
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
            statuses = {(status, path) for status, path, _, _ in folder_rows(left, right)}
            self.assertIn(("Identical", "same.txt"), statuses)
            self.assertIn(("Left only", "only.txt"), statuses)


if __name__ == "__main__":
    unittest.main()
