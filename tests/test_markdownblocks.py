import unittest

from pycommander.markdownblocks import markdown_blocks, table_cells, property_rows, render_grid, display_width
from pycommander.preview import markdown_document, render_markdown


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

    def test_pixel_tables_keep_ranges_empty_cells_and_multiline_rows(self):
        model = markdown_document(
            '# 摘要😀\n\n| 欄名 | Value | 數量 |\n| --- | :---: | ---: |\n'
            '| **接頭** | 中<br>英 | 2 |\n| 短列 | raw |\n\n# Next\n',
            pixel_tables=True)
        start, end, aligns = model['tables'][0]
        lines = model['content'][start:end].splitlines()
        self.assertEqual(aligns, ['left', 'center', 'right'])
        self.assertEqual([line.split('\t')[1::2] for line in lines], [
            ['欄名', 'Value', '數量'], ['接頭', '中', '2'],
            ['', '英', ''], ['短列', 'raw', '']])
        self.assertIn((start, start+len(lines[0]), 'markdown_table_header'), model['spans'])
        self.assertEqual(model['headings'][1]['start'], end+1)

    def test_pixel_table_layout_limit_keeps_data_and_later_tables(self):
        cells = '|'.join(['extra']*65)
        model = markdown_document('A|B\n---|---\n'+cells+'\n\nC|D\n---|---\nlast|value',
                                  pixel_tables=True)
        self.assertTrue(model['table_layout_limited'])
        self.assertEqual(model['content'].count('extra'), 65)
        self.assertEqual(len(model['tables']), 1)
        self.assertIn('last', model['content'][model['tables'][0][0]:])


if __name__ == '__main__': unittest.main()
