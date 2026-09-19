import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pycommander.mdlinks import markdown_destination, read_linked_markdown
from pycommander.preview import markdown_document


class MarkdownReadingTests(unittest.TestCase):
    def test_tasks_callouts_and_code_are_read_only(self):
        model=markdown_document('# Work\n- [ ] pending\n  - [x] finished\n- [?] unknown\n'
            '> [!warning]- Danger\n> Keep this visible\n\n'
            '```md\n- [x] not a task\n# not a heading\n```\n')
        self.assertEqual(model['tasks'],[1,2])
        self.assertIn('☐ pending',model['content'])
        self.assertIn('☑ finished',model['content'])
        self.assertIn('[?] unknown',model['content'])
        self.assertIn('Keep this visible',model['content'])
        self.assertEqual([h['title'] for h in model['headings']],['Work'])
        self.assertIn('markdown_callout_warning',[t for _,_,t in model['spans']])

    def test_links_have_exact_ranges_and_no_image_embeds(self):
        model=markdown_document('😀 [Child](child.md#section) [[#Local]] ![image](photo.md)\n# Local\n')
        self.assertEqual([v['href'] for v in model['links']],['child.md#section','#Local'])
        for link in model['links']:
            self.assertEqual(model['content'][link['start']:link['end']],link['label'])

    def test_tables_do_not_produce_invalid_link_offsets(self):
        model=markdown_document('A|B\n---|---\n[x](a.md)|value\n\n[next](b.md)')
        self.assertEqual(len(model['links']),1)
        item=model['links'][0]
        self.assertEqual(model['content'][item['start']:item['end']],'next')

    def test_nested_heading_boundaries(self):
        model=markdown_document('# A\nbody\n## B\nchild\n# C\ntail')
        a,b,c=model['headings']
        self.assertEqual(a['end'],c['start']);self.assertEqual(b['end'],c['start'])
        self.assertIn('child',model['content'][a['body']:a['end']])

    def test_metadata_limits_fall_back_instead_of_silent_omission(self):
        with self.assertRaises(ValueError):markdown_document('# Heading\n'*2001)
        with self.assertRaises(ValueError):markdown_document('[X](x.md)\n'*2001)

    def test_unknown_callouts_keep_their_label_and_nested_content(self):
        model=markdown_document('> [!custom]- Read me\n> > Nested warning\n> Body\n')
        self.assertIn('CUSTOM',model['content'])
        self.assertIn('> Nested warning',model['content'])
        self.assertIn('Body',model['content'])

    def test_wiki_anchor_encodes_spaces_percent_and_unicode(self):
        model=markdown_document('[[#Release 100% 中文]]\n# Release 100% 中文\n')
        document=Path(os.path.abspath('scope/start.md'))
        link=model['links'][0]
        self.assertEqual(link['label'],'Release 100% 中文')
        self.assertEqual(markdown_destination(document,document.parent,link['href']),
                         (document,'Release 100% 中文'))

    def test_no_target_io_when_rendering_or_parsing_destination(self):
        with patch.object(Path,'stat',side_effect=AssertionError('unexpected target IO')):
            model=markdown_document('\n'.join(f'[note {i}](missing{i}.md)' for i in range(1000)))
            self.assertEqual(len(model['links']),1000)
            document=Path(os.path.abspath('/scope/start.md'))
            target,fragment=markdown_destination(document,document.parent,'sub/space%20name.md#Intro')
            self.assertEqual(target,document.parent/'sub'/'space name.md');self.assertEqual(fragment,'Intro')

    def test_destination_refuses_escape_network_devices_execution(self):
        document=Path(os.path.abspath('scope/start.md'));root=document.parent
        for value in ('../other.md','%2e%2e/other.md','/etc/test.md','//server/share.md',
                      'C:/secret.md','C:secret.md','\\\\server\\x.md','x.md:stream',
                      'x.exe','https://example.com/x.md','file:///x.md','javascript:alert(1)',
                      'x.md?query=1','x%00.md','%ZZ.md','folder\\x.md','dir./x.md','CON.md','NUL/x.md'):
            with self.subTest(value=value),self.assertRaises((ValueError,UnicodeError)):
                markdown_destination(document,root,value)
        self.assertEqual(markdown_destination(document,root,'#Here'),(document,'Here'))
        self.assertEqual(markdown_destination(root/'sub'/'a.md',root,'../start.md')[0],document)

    def test_exact_safe_read_and_no_enumeration(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);target=root/'a.md';target.write_bytes(b'hello')
            with patch.object(Path,'iterdir',side_effect=AssertionError('unexpected enumeration')):
                data,signature=read_linked_markdown(target,root,2)
                self.assertEqual(data,b'hel');self.assertEqual(signature[1],5)
                data,_=read_linked_markdown(target,root,-1);self.assertEqual(data,b'')
                with self.assertRaises(OSError):read_linked_markdown(root/'missing.md',root,20)

    @unittest.skipIf(os.name=='nt','Requires unprivileged POSIX symlink creation')
    def test_symlink_escape_and_fifo_are_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);scope=root/'scope';scope.mkdir()
            outside=root/'outside.md';outside.write_text('private')
            (scope/'link.md').symlink_to(outside)
            (scope/'redirect').symlink_to(root,target_is_directory=True)
            for target in (scope/'link.md',scope/'redirect'/'outside.md'):
                with self.assertRaises((OSError,ValueError)):read_linked_markdown(target,scope,10)
            os.mkfifo(scope/'pipe.md')
            with self.assertRaises(ValueError):read_linked_markdown(scope/'pipe.md',scope,10)


if __name__=='__main__': unittest.main()
