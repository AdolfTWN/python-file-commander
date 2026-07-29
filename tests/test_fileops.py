import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pycommander.fileops as fileops
from pycommander.fileops import copy_items, delete_items, format_size, move_items, recycle_items


class FileOpsTests(unittest.TestCase):
    def test_copy_move_delete(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source, target, moved = root / "source", root / "target", root / "moved"
            source.mkdir(); target.mkdir(); moved.mkdir()
            item = source / "report.txt"; item.write_text("office", encoding="utf-8")
            copy_items([item], target)
            self.assertEqual((target / item.name).read_text(encoding="utf-8"), "office")
            move_items([target / item.name], moved)
            self.assertFalse((target / item.name).exists())
            delete_items([moved / item.name])
            self.assertFalse((moved / item.name).exists())

    def test_conflict_keep_both_and_skip(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source = root / "source"; target = root / "target"
            source.mkdir(); target.mkdir()
            item = source / "報告.txt"; item.write_text("new", encoding="utf-8")
            (target / item.name).write_text("old", encoding="utf-8")
            result = copy_items([item], target, lambda _source, _target: "keep_both")
            self.assertEqual(result.completed, [item])
            self.assertEqual((target / "報告.txt").read_text(encoding="utf-8"), "old")
            self.assertEqual((target / "報告 (2).txt").read_text(encoding="utf-8"), "new")
            result = copy_items([item], target, lambda _source, _target: "skip")
            self.assertEqual(result.skipped, [item])

    def test_partial_failure_continues_and_reports_exact_path(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source = root / "source"; target = root / "target"
            source.mkdir(); target.mkdir()
            missing = source / "missing.txt"
            valid = source / "valid.txt"; valid.write_text("ok", encoding="utf-8")
            result = copy_items([missing, valid], target)
            self.assertEqual(result.completed, [valid])
            self.assertEqual(result.failures[0].source, missing)
            self.assertTrue((target / "valid.txt").exists())

    def test_stop_after_error_marks_remaining_items_skipped(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source = root / "source"; target = root / "target"
            source.mkdir(); target.mkdir()
            missing = source / "missing.txt"
            waiting = source / "waiting.txt"; waiting.write_text("later", encoding="utf-8")
            result = copy_items([missing, waiting], target, continue_on_error=False)
            self.assertEqual(result.skipped, [waiting])
            self.assertFalse((target / "waiting.txt").exists())

    def test_copy_to_same_folder_never_deletes_source(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); item = root / "keep.txt"; item.write_text("safe", encoding="utf-8")
            result = copy_items([item], root)
            self.assertTrue(result.failures)
            self.assertEqual(item.read_text(encoding="utf-8"), "safe")

    def test_failed_replace_restores_original_target(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source = root / "source"; target = root / "target"
            source.mkdir(); target.mkdir()
            item = source / "report.txt"; item.write_text("new", encoding="utf-8")
            existing = target / item.name; existing.write_text("old", encoding="utf-8")
            with mock.patch.object(fileops, "_copy_or_move", side_effect=OSError("simulated failure")):
                result = copy_items([item], target, lambda _source, _target: "replace")
            self.assertTrue(result.failures)
            self.assertEqual(existing.read_text(encoding="utf-8"), "old")

    def test_long_non_ascii_path_copy(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); deep = root
            for number in range(10): deep /= f"segment{number:02d}" + "x" * 20
            deep.mkdir(parents=True)
            item = deep / "年度報告.txt"; item.write_text("office", encoding="utf-8")
            target = root / "target"; target.mkdir()
            result = copy_items([item], target)
            self.assertTrue(result.successful)
            self.assertEqual((target / item.name).read_text(encoding="utf-8"), "office")

    def test_ubuntu_recycle_uses_freedesktop_trash(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home = root / "home"
            home.mkdir()
            item = root / "report.txt"
            item.write_text("safe", encoding="utf-8")
            with mock.patch.object(fileops.os, "name", "posix"), \
                    mock.patch.object(Path, "home", return_value=home):
                result = recycle_items([item])
            self.assertTrue(result.successful)
            self.assertFalse(item.exists())
            self.assertEqual((home / ".local/share/Trash/files/report.txt").read_text(), "safe")
            info = (home / ".local/share/Trash/info/report.txt.trashinfo").read_text()
            self.assertIn("[Trash Info]", info)
            self.assertIn("DeletionDate=", info)

    def test_unc_path_is_not_treated_as_safely_recyclable(self):
        path = Path(r"\\pfc-invalid-server\missing\report.txt")
        result = recycle_items([path])
        self.assertTrue(result.failures)

    def test_format_size(self):
        self.assertEqual(format_size(1024), "1.0 KB")


if __name__ == "__main__":
    unittest.main()
