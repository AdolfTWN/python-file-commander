from datetime import datetime
import unittest
from pathlib import Path
from unittest.mock import patch
from pycommander.columnsettings import modified_text
from pycommander.fileops import is_hidden


class ColumnSettingsTests(unittest.TestCase):
    def test_hidden_dot_names_and_windows_attribute(self):
        self.assertTrue(is_hidden(Path('.env')))
        path = Path('ordinary.txt')
        with patch('pycommander.fileops.os.name','nt'), patch('pycommander.fileops.ctypes.windll', create=True) as dll:
            for value, expected in ((2,True),(0x80,False),(-1,False),(0xffffffff,False)):
                dll.kernel32.GetFileAttributesW.return_value=value
                self.assertEqual(is_hidden(path),expected)
    def test_dates_and_clocks(self):
        for hour, minute, label in ((11,36,'1136a'),(17,15,'0515p'),(0,1,'1201a'),(12,0,'1200p')):
            stamp = datetime(2026,9,19,hour,minute).timestamp()
            self.assertEqual(modified_text(stamp,'ymd','12'), '2026/09/19 '+label)
            self.assertEqual(modified_text(stamp,'mdy','24'), f'09/19/2026 {hour:02}:{minute:02}')
            self.assertEqual(modified_text(stamp,'ymd','none'), '2026/09/19')
