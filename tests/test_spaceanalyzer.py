import tempfile
import unittest
import queue
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from tkinter import TclError

from pycommander.app import admin_launch_spec
from pycommander.spaceanalyzer import (
    SpaceAnalyzerWindow, SpaceNode, partition_rectangles, scan_space)


class SpaceAnalyzerTests(unittest.TestCase):
    def poll_owner(self):
        token=threading.Event()
        return SimpleNamespace(_poll_job=None,_cancel_event=token,_messages=queue.Queue(),
            winfo_exists=Mock(return_value=True),after=Mock(return_value='poll'),
            scan_button=Mock(),stop_button=Mock(),status_var=Mock(),_redraw=Mock(),_poll=Mock(),root_node=None)

    def test_stale_cancel_does_not_finish_a_newer_scan(self):
        window=self.poll_owner();window._messages.put((threading.Event(),'cancelled',None))
        SpaceAnalyzerWindow._poll(window)
        window.scan_button.state.assert_not_called();window.status_var.set.assert_not_called()
        window.after.assert_called_once();self.assertEqual(window._poll_job,'poll')

    def test_newest_result_survives_older_success_and_failure(self):
        window=self.poll_owner();node=SpaceNode(Path('new'),10,True)
        window._messages.put((threading.Event(),'done',SpaceNode(Path('old'),1,True)))
        window._messages.put((threading.Event(),'error',OSError('old scan failed')))
        window._messages.put((window._cancel_event,'done',node))
        SpaceAnalyzerWindow._poll(window)
        self.assertIs(window.root_node,node);window._redraw.assert_called_once_with()
        window.scan_button.state.assert_called_once_with(['!disabled'])

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

    def test_cancel_inside_last_child_is_not_swallowed_as_unreadable(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);child=root/'last';child.mkdir()
            cancel=threading.Event();original=scan_space
            def interrupted(path,event):
                if path==child:
                    event.set()
                    raise InterruptedError
                return original(path,event)
            with patch('pycommander.spaceanalyzer.scan_space',interrupted):
                with self.assertRaises(InterruptedError):original(root,cancel)

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
        pending=object()
        window = SimpleNamespace(_click_job=pending, on_locate=locate,after_cancel=Mock())
        with patch("pycommander.spaceanalyzer.messagebox.askyesno",
                   side_effect=[False, True]):
            SpaceAnalyzerWindow._confirm_go_to(window, node)
            locate.assert_not_called()
            SpaceAnalyzerWindow._confirm_go_to(window, node)
        locate.assert_called_once_with(node.path)
        window.after_cancel.assert_called_once_with(pending)
        self.assertIsNone(window._click_job)

    def test_synchronous_redraw_consumes_pending_resize(self):
        window=SimpleNamespace(_resize_job='pending',after_cancel=Mock(),
                               canvas=Mock(),_rectangles=[],root_node=None)
        SpaceAnalyzerWindow._redraw(window)
        window.after_cancel.assert_called_once_with('pending')
        self.assertIsNone(window._resize_job)
        window.canvas.delete.assert_called_once_with('all')

    def test_expired_click_timer_does_not_prevent_confirmation(self):
        node=SpaceNode(Path('fixture.txt'),10,False)
        window=SimpleNamespace(_click_job='expired',after_cancel=Mock(side_effect=TclError()),on_locate=Mock())
        with patch('pycommander.spaceanalyzer.messagebox.askyesno',return_value=True):
            SpaceAnalyzerWindow._confirm_go_to(window,node)
        self.assertIsNone(window._click_job)
        window.on_locate.assert_called_once_with(node.path)

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
