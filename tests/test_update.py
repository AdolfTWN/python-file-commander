import hashlib
import tempfile
import unittest
from pathlib import Path

from pycommander.app import (downloaded_pfc_version, release_checksum,
                             release_update_assets, replace_portable_script,
                             version_key)


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

    def test_public_release_requires_app_and_checksum_assets(self):
        metadata = {
            "tag_name": "v0.17.5",
            "assets": [
                {"name": "pfc.py", "browser_download_url":
                 "https://github.com/AdolfTWN/pfc-releases/releases/download/v0.17.5/pfc.py"},
                {"name": "pfc.py.sha256",
                 "browser_download_url":
                 "https://github.com/AdolfTWN/pfc-releases/releases/download/v0.17.5/pfc.py.sha256"},
            ],
        }
        self.assertEqual(release_update_assets(metadata),
                         ("0.17.5",
                          "https://github.com/AdolfTWN/pfc-releases/releases/download/v0.17.5/pfc.py",
                          "https://github.com/AdolfTWN/pfc-releases/releases/download/v0.17.5/pfc.py.sha256"))
        metadata["assets"].pop()
        with self.assertRaises(ValueError):
            release_update_assets(metadata)

    def test_public_release_rejects_asset_urls_outside_release_repository(self):
        metadata = {
            "tag_name": "v0.17.5",
            "assets": [
                {"name": "pfc.py", "browser_download_url": "https://example.test/pfc.py"},
                {"name": "pfc.py.sha256", "browser_download_url":
                 "https://github.com/AdolfTWN/pfc-releases/releases/download/v0.17.5/pfc.py.sha256"},
            ],
        }
        with self.assertRaises(ValueError):
            release_update_assets(metadata)

    def test_release_checksum_accepts_only_pfc_sha256_entry(self):
        payload = portable("0.17.5")
        digest = hashlib.sha256(payload).hexdigest()
        self.assertEqual(release_checksum(f"{digest}  pfc.py\n".encode()), digest)
        with self.assertRaises(ValueError):
            release_checksum(f"{digest}  another.py\n".encode())

    def test_replace_is_atomic_and_leaves_no_update_file(self):
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "pfc.py"
            target.write_bytes(portable("0.15.2"))
            replace_portable_script(target, portable("0.16.0"))
            self.assertEqual(downloaded_pfc_version(target.read_bytes()), "0.16.0")
            self.assertFalse((target.parent / ".pfc.py.update").exists())


if __name__ == "__main__":
    unittest.main()
