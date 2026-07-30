import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pycommander.app import admin_launch_spec
from pycommander.spaceanalyzer import (
    SpaceAnalyzerWindow, SpaceNode, partition_rectangles, scan_space)


class SpaceAnalyzerTests(unittest.TestCase):
    def test_scan_space_totals_nested_files(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "a.bin").write_bytes(b"a" * 40)
            folder = root / "folder"
            folder.mkdir()
            (folder / "b.bin").write_bytes(b"b" * 60)
            result = scan_space(root)
            self.assertEqual(result.size, 100)
            self.assertEqual({node.path.name for node in result.children},
                             {"a.bin", "folder"})

    def test_rectangle_area_tracks_node_size(self):
        small = SpaceNode(Path("small"), 25, False)
        large = SpaceNode(Path("large"), 75, False)
        boxes = partition_rectangles([large, small], 0, 0, 100, 100)
        areas = {
            node.path.name: (box[2] - box[0]) * (box[3] - box[1])
            for node, box in boxes
        }
        self.assertAlmostEqual(areas["large"] / areas["small"], 3.0, places=3)

    def test_admin_launch_specs_quote_paths(self):
        executable, parameters = admin_launch_spec(
            Path("C:/Program Files/tool.py"), python_executable="python.exe")
        self.assertEqual(executable, "python.exe")
        self.assertIn('"', parameters)
        executable, parameters = admin_launch_spec(Path("C:/Temp/setup.msi"))
        self.assertEqual(executable, "msiexec.exe")
        self.assertTrue(parameters.startswith("/i "))

    def test_go_to_only_runs_after_confirmation(self):
        node = SpaceNode(Path("C:/Temp/example.txt"), 10, False)
        locate = Mock()
        window = SimpleNamespace(_click_job=object(), on_locate=locate)
        with patch("pycommander.spaceanalyzer.messagebox.askyesno",
                   side_effect=[False, True]):
            SpaceAnalyzerWindow._confirm_go_to(window, node)
            locate.assert_not_called()
            SpaceAnalyzerWindow._confirm_go_to(window, node)
        locate.assert_called_once_with(node.path)

    def test_remove_choice_passes_explicit_recycle_or_permanent_action(self):
        node = SpaceNode(Path("C:/Temp/example.txt"), 10, False)
        remove = Mock(return_value=True)
        scan = Mock()
        window = SimpleNamespace(
            on_remove=remove, scan=scan,
            path_var=SimpleNamespace(get=lambda: "C:/Temp"))
        with patch("pycommander.spaceanalyzer.messagebox.askyesno",
                   return_value=True):
            SpaceAnalyzerWindow._confirm_remove(window, node, permanent=False)
            SpaceAnalyzerWindow._confirm_remove(window, node, permanent=True)
        self.assertEqual(
            remove.call_args_list[0].args, (node.path, False))
        self.assertEqual(
            remove.call_args_list[1].args, (node.path, True))
        self.assertEqual(scan.call_count, 2)


if __name__ == "__main__":
    unittest.main()
