import os
import unittest

from pycommander.app import hide_private_console, preferred_font_families, relaunch_with_pythonw


class ConsoleTests(unittest.TestCase):
    def test_native_font_preference_and_fallback(self):
        self.assertEqual(preferred_font_families(["Arial", "Segoe UI", "Consolas"]),
                         ("Segoe UI", "Consolas"))
        self.assertEqual(preferred_font_families(["Segoe UI", "Cascadia Mono", "Consolas"]),
                         ("Segoe UI", "Cascadia Mono"))

    @unittest.skipIf(os.name == "nt", "Non-Windows behavior test")
    def test_non_windows_does_nothing(self):
        self.assertFalse(hide_private_console())
        self.assertFalse(relaunch_with_pythonw())


if __name__ == "__main__":
    unittest.main()
