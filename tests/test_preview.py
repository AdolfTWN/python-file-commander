import unittest
from pathlib import Path

from pycommander.preview import decode_text, looks_text, render_hex, render_markdown, syntax_spans


class PreviewTests(unittest.TestCase):
    def test_text_detection_and_decoding(self):
        self.assertTrue(looks_text(Path("notes.txt"), b"hello\nworld"))
        self.assertFalse(looks_text(Path("data.bin"), b"a\x00b"))
        self.assertEqual(decode_text(b"hello"), ("hello", "UTF-8"))

    def test_hex_has_offset_bytes_and_ascii(self):
        rendered = render_hex(b"ABC\x00")
        self.assertIn("00000000", rendered)
        self.assertIn("41 42 43 00", rendered)
        self.assertIn("|ABC.|", rendered)

    def test_explicit_unicode_boms_including_utf32_are_detected_without_guessing(self):
        text='中😀 {"value":"needle"}'
        for codec,bom,label in (('utf-32-le',b'\xff\xfe\0\0','UTF-32'),
                                ('utf-32-be',b'\0\0\xfe\xff','UTF-32'),
                                ('utf-16-le',b'\xff\xfe','UTF-16'),
                                ('utf-16-be',b'\xfe\xff','UTF-16'),
                                ('utf-8',b'\xef\xbb\xbf','UTF-8')):
            with self.subTest(codec=codec):
                data=bom+text.encode(codec)
                self.assertTrue(looks_text(Path('unknown.data'),data))
                self.assertEqual(decode_text(data),(text,label))

    def test_python_and_markdown_effects(self):
        python = "def answer():\n    # note\n    return 42\n"
        tags = {tag for _start, _end, tag in syntax_spans(python, ".py")}
        self.assertTrue({"syntax_keyword", "syntax_comment", "syntax_number"} <= tags)
        rendered, markdown_tags = render_markdown(
            "# Heading\n\n- **Bold** and `code`\n[Site](https://example.com)\n")
        self.assertIn("Heading", rendered)
        self.assertIn("• Bold and code", rendered)
        self.assertNotIn("**", rendered)
        self.assertTrue({"markdown_h1", "markdown_bold", "markdown_code",
                         "markdown_link"} <= {tag for _start, _end, tag in markdown_tags})


if __name__ == "__main__":
    unittest.main()
