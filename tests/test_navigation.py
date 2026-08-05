import os
import tempfile
import unittest
from pathlib import Path

from pycommander.app import (create_shortcut_file, folder_history_selection,
                             navigation_destination, shortcut_path_for,
                             transfer_target_index)


class NavigationDestinationTests(unittest.TestCase):
    def test_transfer_target_uses_right_for_p1_and_left_neighbor_afterward(self):
        self.assertEqual([transfer_target_index(index, 4) for index in range(4)],
                         [1, 0, 1, 2])
        self.assertEqual([transfer_target_index(index, 2) for index in range(2)],
                         [1, 0])

    def test_parent_navigation_selects_folder_just_left(self):
        root = Path("C:/work")
        self.assertEqual(folder_history_selection(root / "1" / "a", root / "1", {}),
                         root / "1" / "a")
        self.assertEqual(folder_history_selection(root / "1", root, {}), root / "1")

    def test_unrelated_navigation_restores_remembered_row(self):
        root = Path("C:/work")
        remembered = {root / "2": root / "2" / "f"}
        self.assertEqual(folder_history_selection(root / "1", root / "2", remembered),
                         root / "2" / "f")

    def test_folder_path_opens_the_folder_without_a_selection(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw).resolve()
            self.assertEqual(navigation_destination(folder), (folder, None))

    def test_file_path_opens_parent_and_selects_the_file(self):
        with tempfile.TemporaryDirectory() as raw:
            file_path = Path(raw, "selected.txt")
            file_path.write_text("content", encoding="utf-8")
            resolved = file_path.resolve()
            self.assertEqual(navigation_destination(file_path), (resolved.parent, resolved))

    def test_missing_path_is_left_for_normal_invalid_path_handling(self):
        with tempfile.TemporaryDirectory() as raw:
            missing = Path(raw, "missing.txt").resolve()
            self.assertEqual(navigation_destination(missing), (missing, None))

    def test_shortcut_name_is_unique_beside_the_source(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            source = folder / "Quarterly Report.txt"
            source.write_text("report", encoding="utf-8")
            first = shortcut_path_for(source, folder)
            first.touch()
            second = shortcut_path_for(source, folder)
            self.assertNotEqual(first, second)
            self.assertIn("Quarterly Report - Shortcut", first.name)
            self.assertIn("(2)", second.name)

    @unittest.skipUnless(os.name == "nt", "Windows shortcut integration")
    def test_native_windows_shortcut_is_created(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            source = folder / "source.txt"
            source.write_text("source", encoding="utf-8")
            shortcut = shortcut_path_for(source, folder)
            self.assertEqual(create_shortcut_file(source, shortcut), shortcut)
            self.assertTrue(shortcut.is_file())


if __name__ == "__main__":
    unittest.main()
