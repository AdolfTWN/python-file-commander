import tempfile
import unittest
from pathlib import Path

from pycommander.app import folder_history_selection, navigation_destination


class NavigationDestinationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
