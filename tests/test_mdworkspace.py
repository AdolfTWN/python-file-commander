import os
import configparser
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pycommander.mdworkspace import scan_markdown_workspace, wiki_destination, workspace_root, remember_markdown_workspace
from pycommander.workflowdata import WorkflowRecords
from pycommander.preview import markdown_document, decode_text


class MarkdownWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);self.document = self.root/'Notes.md'
        self.document.write_text('# Notes\n',encoding='utf-8')

    def scan(self,**kw):
        request=dict(root=str(self.root),path=str(self.document),depth=3,mode='files')
        request.update(kw)
        return scan_markdown_workspace(request,markdown_document,decode_text)

    def test_wiki_alias_heading_and_no_io(self):
        with patch('os.scandir',side_effect=AssertionError('Unexpected I/O')):
            model=markdown_document('[[Spec#中文標題|別名]] [[#Local]] `[[ignore]]`\n\n```\n[[skip]]\n```')
        self.assertEqual([l['label'] for l in model['links']],['別名','Local'])
        self.assertEqual(wiki_destination('Spec#中文標題|別名')['name'],'Spec.md')
        for value in ('../escape','C:/notes','//host/a','a\\b','bad\x00name','note#^block','file.exe'):
            with self.subTest(value=value),self.assertRaises(ValueError):wiki_destination(value)

    def test_percent_paths_survive_ini_and_reading_records(self):
        config=configparser.ConfigParser();root=self.root/'Project 100%'
        remember_markdown_workspace(config,root,5)
        WorkflowRecords(config,'reading_positions').put('100% document',{'path':str(root/'Notes.md')})
        stream=io.StringIO();config.write(stream)
        restored=configparser.ConfigParser();restored.read_string(stream.getvalue())
        self.assertEqual(restored.get('markdown_workspace','root'),str(root))
        self.assertEqual(WorkflowRecords(restored,'reading_positions').read()[0]['data']['path'],str(root/'Notes.md'))

    def test_scope_must_contain_document_and_not_broad(self):
        for root in (self.root.anchor,str(Path.home()),str(self.root/'other'),'relative'):
            with self.subTest(root=root),self.assertRaises(ValueError):workspace_root(root,self.document)

    def test_depth_exclusion_filename_only(self):
        leaf=self.root/'a'/'b'/'c'/'d';leaf.mkdir(parents=True)
        (leaf/'deep.md').write_text('deep')
        excluded=self.root/'node_modules';excluded.mkdir();(excluded/'bad.md').write_text('bad')
        with patch('pycommander.mdworkspace.read_linked_markdown',side_effect=AssertionError('Filename search read content')):
            shallow=self.scan();deep=self.scan(depth=5)
        self.assertEqual([r['path'] for r in shallow['results']],['Notes.md'])
        self.assertIn(str(Path('a/b/c/d/deep.md')),[r['path'] for r in deep['results']])
        self.assertNotIn(str(Path('node_modules/bad.md')),[r['path'] for r in deep['results']])

    def test_all_entries_count_and_duplicates_preserved(self):
        for name in ('a','b'):
            (self.root/name).mkdir();(self.root/name/'Spec.md').write_text('spec')
        result=self.scan(mode='wiki',query='Spec.md')
        self.assertEqual(len(result['results']),2)
        exact=self.scan(mode='wiki',query='a/Spec.md')
        self.assertEqual([r['path'] for r in exact['results']],[str(Path('a/Spec.md'))])
        limited=self.scan(max_entries=1)
        self.assertEqual(limited['visited'],1);self.assertIn('entries',limited['reasons'])

    def test_backlinks_exact_ambiguous_and_code_ignored(self):
        (self.root/'exact.md').write_text('[Notes](Notes.md#Notes)',encoding='utf-8')
        (self.root/'possible.md').write_text('[[Notes|Alias]]',encoding='utf-8')
        (self.root/'code.md').write_text('`[[Notes]]`\n\n```\n[Notes](Notes.md)\n```',encoding='utf-8')
        result=self.scan(mode='backlinks')
        pairs={r['path']:r['detail'] for r in result['results']}
        self.assertEqual(pairs,{'exact.md':'Exact path reference','possible.md':'Possible filename reference'})

    @unittest.skipIf(os.name=='nt','Requires unprivileged symlinks')
    def test_symlinks_not_followed_and_linked_root_rejected(self):
        (self.root/'loop').symlink_to(self.root,target_is_directory=True)
        (self.root/'linked.md').symlink_to(self.document)
        result=self.scan();self.assertEqual([r['path'] for r in result['results']],['Notes.md'])
        self.assertIn('unavailable',result['reasons'])
        with self.assertRaises((ValueError,OSError)):
            self.scan(root=str(self.root/'loop'),path=str(self.root/'loop/Notes.md'))

    def test_backlinks_large_documents_report_incomplete(self):
        (self.root/'large.md').write_bytes(b'x'*(256*1024+1))
        result=self.scan(mode='backlinks')
        self.assertIn('large documents',result['reasons'])

    def test_clock_budget(self):
        with patch('pycommander.mdworkspace.time.monotonic',side_effect=[0,4,4]):
            result=self.scan()
        self.assertIn('time',result['reasons']);self.assertEqual(result['visited'],0)

    def test_result_limit(self):
        for i in range(55):(self.root/f'{i}.md').write_text('')
        result=self.scan();self.assertEqual(len(result['results']),50)
        self.assertIn('results',result['reasons'])

    def test_backlinks_resident_read_failure_never_becomes_complete(self):
        (self.root/'other.md').write_text('[[Notes]]')
        with patch('pycommander.mdworkspace.read_linked_markdown',side_effect=PermissionError()):
            result=self.scan(mode='backlinks')
        self.assertIn('unavailable',result['reasons']);self.assertFalse(result['results'])

    def test_time_limit_cannot_be_raised_by_request(self):
        (self.root/'other.md').write_text('[[Notes]]')
        with patch('pycommander.mdworkspace.time.monotonic',side_effect=[0,4,4]):
            result=self.scan(seconds=999)
        self.assertIn('time',result['reasons'])

    def test_backlink_total_read_budget_even_when_files_grow(self):
        for number in range(40):(self.root/f'grow-{number}.md').touch()
        counts=[]
        def growing_read(path,root,limit):
            counts.append(limit)
            return b'x'*limit,(0,limit)
        request=dict(root=str(self.root),path=str(self.document),mode='backlinks')
        with patch('pycommander.mdworkspace.read_linked_markdown',growing_read):
            result=scan_markdown_workspace(request,lambda source:{'links':[]},decode_text)
        self.assertEqual(sum(counts),8*1024*1024)
        self.assertIn('content budget',result['reasons'])

    def test_windows_cloud_metadata_is_skipped_without_reading(self):
        import types
        from contextlib import contextmanager
        entry=types.SimpleNamespace(name='Online.md',stat=lambda **kw:types.SimpleNamespace(
            st_mode=0o100644,st_file_attributes=0x400000,st_size=20))
        @contextmanager
        def entries(path):yield iter([entry])
        with patch('pycommander.mdworkspace.workspace_entries',entries),patch(
                'pycommander.mdworkspace.read_linked_markdown',side_effect=AssertionError('Cloud content read')):
            result=self.scan(mode='backlinks')
        self.assertEqual(result['skipped'],1);self.assertIn('unavailable',result['reasons'])
