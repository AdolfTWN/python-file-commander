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
