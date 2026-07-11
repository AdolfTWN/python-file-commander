import os
import unittest

from pycommander.app import hide_private_console


class ConsoleTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "Non-Windows behavior test")
    def test_non_windows_does_nothing(self):
        self.assertFalse(hide_private_console())


if __name__ == "__main__":
    unittest.main()
