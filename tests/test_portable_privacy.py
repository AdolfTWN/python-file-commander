import unittest
from pathlib import Path


class PortablePrivacyTests(unittest.TestCase):
    def test_single_file_has_no_local_user_identity_or_git_credentials(self):
        portable = (Path(__file__).resolve().parents[1] / "pfc.py").read_text(encoding="utf-8").casefold()
        forbidden = ("git@", "c:\\users\\", "c:/users/")
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, portable)
        self.assertEqual(portable.count("raw.githubusercontent.com/adolftwn/python-file-commander/main/pfc.py"), 1)


if __name__ == "__main__":
    unittest.main()
