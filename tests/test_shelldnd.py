import ctypes
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pycommander.clipboard import (CF_HDROP, DVASPECT_CONTENT, TYMED_HGLOBAL,
                                   _FORMATETC, _vtable_method)
from pycommander.shelldnd import (DROPEFFECT_COPY, DROPEFFECT_MOVE, MK_SHIFT,
                                  ShellDataObject, ShellFileDropTarget,
                                  _OleDropTarget, _drop_effect)


class DropEffectTests(unittest.TestCase):
    def test_virtual_attachments_are_always_copied(self):
        self.assertEqual(_drop_effect("virtual", MK_SHIFT,
                                      DROPEFFECT_COPY | DROPEFFECT_MOVE), DROPEFFECT_COPY)

    def test_shell_paths_use_shift_for_move(self):
        allowed = DROPEFFECT_COPY | DROPEFFECT_MOVE
        self.assertEqual(_drop_effect("files", 0, allowed), DROPEFFECT_COPY)
        self.assertEqual(_drop_effect("files", MK_SHIFT, allowed), DROPEFFECT_MOVE)

    def test_virtual_drop_starts_background_extraction(self):
        target = ShellFileDropTarget.__new__(ShellFileDropTarget)
        target.widget = SimpleNamespace(after=Mock(return_value="poll-job"))
        target.virtual_callback = Mock()
        target._virtual_results = __import__("queue").Queue()
        target._virtual_workers = 0
        target._virtual_poll_job = None
        thread = Mock()
        with tempfile.TemporaryDirectory() as raw, \
                patch("pycommander.shelldnd.tempfile.mkdtemp", return_value=raw), \
                patch("pycommander.shelldnd._marshal_data_object", return_value=123), \
                patch("pycommander.shelldnd.threading.Thread", return_value=thread):
            target._queue_virtual_drop(456, 10, 20)
        thread.start.assert_called_once_with()
        target.virtual_callback.assert_not_called()
        self.assertEqual(target._virtual_workers, 1)


@unittest.skipUnless(os.name == "nt", "Windows Shell integration test")
class ShellDragDropTests(unittest.TestCase):
    def test_shell_data_object_exposes_file_drop_format(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first = root / "one.txt"; first.write_text("1", encoding="utf-8")
            second = root / "two.txt"; second.write_text("2", encoding="utf-8")
            with ShellDataObject([first, second]) as data:
                request = _FORMATETC(CF_HDROP, None, DVASPECT_CONTENT, -1, TYMED_HGLOBAL)
                query = _vtable_method(data.pointer, 5, ctypes.c_long,
                                       ctypes.POINTER(_FORMATETC))
                self.assertEqual(query(data.pointer, ctypes.byref(request)), 0)

    def test_ole_drop_target_recognizes_explorer_file_data(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "one.txt"; path.write_text("1", encoding="utf-8")
            owner = SimpleNamespace(virtual_callback=lambda *_args: None)
            target = _OleDropTarget(owner)
            with ShellDataObject([path]) as data:
                self.assertEqual(target._detect_kind(data.pointer), "files")

    def test_shell_data_object_rejects_mixed_parent_folders(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); (root / "a").mkdir(); (root / "b").mkdir()
            first = root / "a" / "one.txt"; first.write_text("1", encoding="utf-8")
            second = root / "b" / "two.txt"; second.write_text("2", encoding="utf-8")
            with self.assertRaisesRegex(OSError, "same folder"):
                ShellDataObject([first, second])


if __name__ == "__main__":
    unittest.main()
