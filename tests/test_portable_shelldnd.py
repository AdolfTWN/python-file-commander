import ctypes
import os
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == "nt", "Windows single-file Shell integration test")
class PortableShellDragTests(unittest.TestCase):
    def test_drag_guid_type_is_not_replaced_by_shell_menu_guid(self):
        import pfc

        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "portable.txt"
            path.write_text("portable", encoding="utf-8")
            with pfc.ShellDataObject([path]) as data:
                request = pfc._FORMATETC(pfc.CF_HDROP, None, pfc.DVASPECT_CONTENT,
                                         -1, pfc.TYMED_HGLOBAL)
                query = pfc._vtable_method(data.pointer, 5, ctypes.c_long,
                                           ctypes.POINTER(pfc._FORMATETC))
                self.assertEqual(query(data.pointer, ctypes.byref(request)), 0)


if __name__ == "__main__":
    unittest.main()
