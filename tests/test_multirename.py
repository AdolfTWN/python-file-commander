import tempfile
import unittest
from pathlib import Path

from pycommander.multirename import execute_rename_pairs, render_rename, validate_rename_plan


class MultiRenameTests(unittest.TestCase):
    def test_mask_counter_find_replace_and_extension(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "Draft Report.txt"
            path.write_text("x", encoding="utf-8")
            name = render_rename(path, "Office_[C]_[N]", "draft", "Final", 3, 3,
                                 case_sensitive=False, keep_extension=True)
            self.assertEqual(name, "Office_003_Final Report.txt")

    def test_validation_detects_duplicates_and_invalid_names(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); one, two = root / "one.txt", root / "two.txt"
            one.write_text("1"); two.write_text("2")
            plan = validate_rename_plan([one, two], ["same.txt", "same.txt"])
            self.assertTrue(all(problem == "Duplicate target" for _source, _target, problem in plan))
            invalid = validate_rename_plan([one], ["bad:name.txt"])
            self.assertEqual(invalid[0][2], "Invalid name")

    def test_batch_swap_and_undo(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); one, two = root / "one.txt", root / "two.txt"
            one.write_text("ONE"); two.write_text("TWO")
            undo = execute_rename_pairs([(one, two), (two, one)])
            self.assertEqual(one.read_text(), "TWO")
            self.assertEqual(two.read_text(), "ONE")
            execute_rename_pairs(undo)
            self.assertEqual(one.read_text(), "ONE")
            self.assertEqual(two.read_text(), "TWO")

    def test_failed_batch_restores_already_staged_source(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source, missing = root / "source.txt", root / "missing.txt"
            target = root / "renamed.txt"; source.write_text("SAFE")
            with self.assertRaises(OSError):
                execute_rename_pairs([(source, target), (missing, root / "other.txt")])
            self.assertTrue(source.exists())
            self.assertEqual(source.read_text(), "SAFE")
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
