import tempfile
import unittest
from pathlib import Path

from pycommander.app import is_noop_drag_drop


class DragDropTests(unittest.TestCase):
    def test_dragging_items_back_to_source_folder_is_noop(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw).resolve()
            first = folder / "first.txt"; first.write_text("1", encoding="utf-8")
            second = folder / "second.txt"; second.write_text("2", encoding="utf-8")
            self.assertTrue(is_noop_drag_drop([first, second], folder))

    def test_dragging_folder_onto_itself_is_noop(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw, "folder"); folder.mkdir()
            self.assertTrue(is_noop_drag_drop([folder], folder))

    def test_dragging_to_another_folder_is_not_noop(self):
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw, "source"); source.mkdir()
            destination = Path(raw, "destination"); destination.mkdir()
            item = source / "item.txt"; item.write_text("x", encoding="utf-8")
            self.assertFalse(is_noop_drag_drop([item], destination))


if __name__ == "__main__":
    unittest.main()
