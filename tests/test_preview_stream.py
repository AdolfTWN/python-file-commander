import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pycommander.preview import regular_preview_stream


class PreviewStreamTests(unittest.TestCase):
    def test_regular_unicode_file_and_descriptor_cleanup(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'說明.txt';path.write_bytes(b'fixture bytes')
            with regular_preview_stream(path) as (stream,info):
                self.assertEqual(b'fixture bytes',stream.read());self.assertEqual(13,info.st_size)
            self.assertTrue(stream.closed)

    def test_directory_refused_before_any_open(self):
        with tempfile.TemporaryDirectory() as raw,patch('pycommander.preview.os.open') as opened:
            with self.assertRaises(OSError):
                with regular_preview_stream(Path(raw)):pass
            opened.assert_not_called()

    @unittest.skipUnless(hasattr(os,'mkfifo'),'POSIX stream fixture')
    def test_fifo_refused_before_any_open(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'stream.md';os.mkfifo(path)
            with patch('pycommander.preview.os.open') as opened:
                with self.assertRaises(OSError):
                    with regular_preview_stream(path):pass
                opened.assert_not_called()

    @unittest.skipUnless(hasattr(os,'mkfifo'),'POSIX replacement-race fixture')
    def test_regular_to_fifo_replacement_cannot_block_open(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'race.txt';path.write_text('before');original=os.open
            def replace(target,flags):
                path.unlink();os.mkfifo(path);return original(target,flags)
            with patch('pycommander.preview.os.open',side_effect=replace):
                with self.assertRaises(OSError):
                    with regular_preview_stream(path):pass

    def test_ordinary_symlink_remains_readable(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'target.txt';path.write_text('ordinary');link=Path(raw)/'link.txt'
            try:link.symlink_to(path)
            except OSError:self.skipTest('Symlink fixture not available')
            with regular_preview_stream(link) as (stream,_):self.assertEqual(b'ordinary',stream.read())
