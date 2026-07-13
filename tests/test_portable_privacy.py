import unittest
from pathlib import Path


class PortablePrivacyTests(unittest.TestCase):
    def test_single_file_has_no_repository_or_local_user_identity(self):
        portable = (Path(__file__).resolve().parents[1] / "pfc.py").read_text(encoding="utf-8").casefold()
        forbidden = ("github.com/", "git@", "c:\\users\\", "c:/users/")
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, portable)


if __name__ == "__main__":
    unittest.main()
