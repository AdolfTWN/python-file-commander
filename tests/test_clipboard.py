import ctypes
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pycommander.clipboard as clipboard
from pycommander.clipboard import (_FILEDESCRIPTORW, _STGMEDIUM, VirtualFileDescriptor,
                                   extract_virtual_files_from_data_object,
                                   parse_file_group_descriptor)


class ClipboardVirtualFileTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows clipboard integration test")
    def test_zip_copy_publishes_file_drop_and_copy_effect(self):
        with tempfile.TemporaryDirectory() as raw:
            archive = Path(raw) / "teams-upload.zip"
            archive.write_bytes(b"PK\x05\x06" + b"\0" * 18)
            try:
                clipboard.set_file_clipboard([archive], cut=False)
                self.assertEqual(clipboard.get_file_clipboard(), ([archive.resolve()], False))
                effect_format = clipboard._register_clipboard_format("Preferred DropEffect")
                clipboard._open_clipboard()
                try:
                    user32 = ctypes.windll.user32
                    user32.GetClipboardData.restype = ctypes.c_void_p
                    user32.GetClipboardData.argtypes = [ctypes.c_uint]
                    self.assertTrue(user32.GetClipboardData(clipboard.CF_HDROP))
                    effect_handle = user32.GetClipboardData(effect_format)
                    self.assertTrue(effect_handle)
                    self.assertEqual(struct.unpack("<I", clipboard._global_bytes(effect_handle)[:4])[0],
                                     clipboard.DROPEFFECT_COPY)
                finally:
                    ctypes.windll.user32.CloseClipboard()
            finally:
                clipboard.clear_file_clipboard()

    def test_non_windows_in_app_file_clipboard(self):
        with tempfile.TemporaryDirectory() as raw:
            item = Path(raw) / "report.txt"
            item.write_text("portable", encoding="utf-8")
            with patch.object(clipboard.os, "name", "posix"):
                clipboard.set_file_clipboard([item], cut=True)
                self.assertEqual(clipboard.get_file_clipboard(), ([item.resolve()], True))
                clipboard.clear_file_clipboard()
                self.assertEqual(clipboard.get_file_clipboard(), ([], False))

    @unittest.skipUnless(os.name == "nt", "Windows FILEDESCRIPTORW layout")
    def test_outlook_file_group_descriptor_names_and_sizes(self):
        first = _FILEDESCRIPTORW(); first.cFileName = "Quarterly Report.xlsx"; first.nFileSizeLow = 1234
        second = _FILEDESCRIPTORW(); second.cFileName = r"folder\safe.pdf"; second.nFileSizeHigh = 1
        payload = struct.pack("<I", 2) + bytes(first) + bytes(second)
        descriptors = parse_file_group_descriptor(payload)
        self.assertEqual([item.name for item in descriptors], ["Quarterly Report.xlsx", "safe.pdf"])
        self.assertEqual(descriptors[0].size, 1234)
        self.assertEqual(descriptors[1].size, 1 << 32)
        self.assertEqual(ctypes.sizeof(_FILEDESCRIPTORW), 592)

    def test_invalid_virtual_descriptor_is_rejected(self):
        with self.assertRaises(OSError):
            parse_file_group_descriptor(struct.pack("<I", 1))

    def test_data_object_virtual_files_are_materialized_before_drop_returns(self):
        descriptors = [VirtualFileDescriptor("Agenda.docx", 6)]
        medium = _STGMEDIUM()
        with tempfile.TemporaryDirectory() as raw, \
                patch("pycommander.clipboard._virtual_descriptors_from_object",
                      return_value=descriptors), \
                patch("pycommander.clipboard._register_clipboard_format", return_value=99), \
                patch("pycommander.clipboard._get_medium", return_value=medium) as get_medium, \
                patch("pycommander.clipboard._release_medium") as release_medium, \
                patch("pycommander.clipboard._write_virtual_medium",
                      side_effect=lambda _medium, target, _size: target.write_bytes(b"office")):
            files, failures = extract_virtual_files_from_data_object(123, Path(raw))
            self.assertEqual(failures, [])
            self.assertEqual([path.name for path in files], ["Agenda.docx"])
            self.assertEqual(files[0].read_bytes(), b"office")
            get_medium.assert_called_once()
            release_medium.assert_called_once_with(medium)


if __name__ == "__main__":
    unittest.main()
