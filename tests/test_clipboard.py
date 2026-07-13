import ctypes
import struct
import unittest

from pycommander.clipboard import _FILEDESCRIPTORW, parse_file_group_descriptor


class ClipboardVirtualFileTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
