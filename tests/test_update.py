import tempfile
import unittest
from pathlib import Path

from pycommander.app import downloaded_pfc_version, replace_portable_script, version_key


def portable(version: str) -> bytes:
    return (f'"""Python File Commander"""\n\n__version__ = "{version}"\n'
            'def main():\n    return 0\n').encode("utf-8")


class UpdateTests(unittest.TestCase):
    def test_versions_are_compared_numerically(self):
        self.assertGreater(version_key("0.15.10"), version_key("0.15.9"))
        self.assertEqual(version_key("v1.0.0"), (1, 0, 0))
        with self.assertRaises(ValueError):
            version_key("latest")

    def test_download_must_be_valid_pfc_python(self):
        self.assertEqual(downloaded_pfc_version(portable("0.16.0")), "0.16.0")
        with self.assertRaises((ValueError, SyntaxError)):
            downloaded_pfc_version(b'__version__ = "0.16.0"\nnot valid python !')

    def test_replace_is_atomic_and_leaves_no_update_file(self):
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "pfc.py"
            target.write_bytes(portable("0.15.2"))
            replace_portable_script(target, portable("0.16.0"))
            self.assertEqual(downloaded_pfc_version(target.read_bytes()), "0.16.0")
            self.assertFalse((target.parent / ".pfc.py.update").exists())


if __name__ == "__main__":
    unittest.main()
