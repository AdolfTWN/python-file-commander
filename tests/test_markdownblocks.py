import unittest

from pycommander.markdownblocks import markdown_blocks, table_cells, property_rows, render_grid, display_width
from pycommander.preview import render_markdown


class MarkdownBlocksTests(unittest.TestCase):
    def test_pipe_escaping_and_code(self):
        self.assertEqual(table_cells(r'| a\|b | `x|y` | |'), ['a|b', '`x|y`', ''])
        self.assertEqual(table_cells('a | b'), ['a', 'b'])
        self.assertEqual(table_cells(r'| a | b\|'), ['a', 'b|'])

    def test_tables_keep_extra_cells_and_short_rows(self):
        blocks = list(markdown_blocks('A|B\n:---|---:\na|b|EXTRA\nshort|\n\nend'))
        self.assertEqual(blocks[0][0], 'table')
        rows, alignment = blocks[0][1]
        self.assertEqual(alignment, ['left', 'right'])
        rendered = render_grid(rows, alignment)
        for word in ['A', 'B', 'a', 'b', 'EXTRA', 'short']: self.assertIn(word, rendered)
        self.assertEqual(blocks[-1], ('text', 'end'))

    def test_code_is_not_a_table_or_frontmatter(self):
        text = '~~~yaml\n---\na: b\n---\nA|B\n---|---\n~~~\n'
        self.assertTrue(all(kind == 'code' for kind, _ in markdown_blocks(text)))

    def test_frontmatter_keeps_nested_and_unknown_values(self):
        raw = 'title: Example\ntags:\n  - one\n  - two\nlong: |\n  first\n  last\ncustom: !unknown literal'
        rows = property_rows(raw.splitlines())
        self.assertEqual(rows[1], ['tags', '\n  - one\n  - two'])
        text, tags = render_markdown('\ufeff---\n'+raw+'\n---\n# Body')
        for word in ['Example', 'one', 'two', 'first', 'last', '!unknown literal', 'Body']:
            self.assertIn(word, text)
        self.assertIn('markdown_table', {t for _, _, t in tags})

    def test_unclosed_frontmatter_is_not_consumed(self):
        self.assertNotIn('properties', [k for k, _ in markdown_blocks('---\nkey: value')])

    def test_rendered_table_keeps_links_and_line_breaks(self):
        text, spans = render_markdown('Name|Value\n---|---\n**bold**|[site](https://example.com)<br>tail')
        self.assertIn('bold', text)
        self.assertIn('https://example.com', text)
        self.assertIn('tail', text)
        self.assertNotIn('<br>', text)
        self.assertTrue(all(0 <= start < end <= len(text) for start, end, _ in spans))

    def test_long_cells_wrap_without_loss_and_cjk_aligns(self):
        result = render_grid([['Head', '值'], ['x'*120+'END', '資料']])
        self.assertEqual(result.count('x'), 120)
        self.assertIn('END', result)
        self.assertEqual(len({display_width(line) for line in result.splitlines()}), 1)

    def test_large_sparse_table_falls_back_without_truncation(self):
        rows = [['a']*1001] + [['END']]*500
        result = render_grid(rows)
        self.assertEqual(result.count('END'), 500)
        self.assertIn('\t', result)


if __name__ == '__main__': unittest.main()
