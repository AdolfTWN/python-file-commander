import codecs
import configparser
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pycommander.textio import read_text_document, TEXT_EDIT_LIMIT
from pycommander.workflowdata import (WorkflowRecords, compare_excluded, compare_sync_plans,
    comparison_report, write_comparison_report, reading_anchor, resolve_reading_anchor)
from pycommander.workflows import command_matches
from pycommander.workspaces import validate_workspace
from pycommander.compare import folder_rows, aligned_text, detect_compare_type


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()

    def test_encoding_bom_eol_and_final_newline_round_trip(self):
        for encoding, bom in [('utf-8', b''), ('utf-8', codecs.BOM_UTF8),
                              ('utf-16-le', codecs.BOM_UTF16_LE), ('utf-16-be', codecs.BOM_UTF16_BE),
                              ('utf-32-le', codecs.BOM_UTF32_LE), ('utf-32-be', codecs.BOM_UTF32_BE)]:
            for ending in ('\n', '\r\n', '\r'):
                for final in ('', ending):
                    with self.subTest(encoding=encoding, ending=ending, final=final):
                        path = self.root/'note.txt'
                        original = '第一行'+ending+'café 🙂'+final
                        path.write_bytes(bom+original.encode(encoding))
                        document = read_text_document(path)
                        self.assertFalse(document.reason)
                        document.save(document.text)
                        self.assertEqual(path.read_bytes(), bom+original.encode(encoding))
                        document.save(document.text.replace('café', 'coffee'))
                        self.assertEqual(path.read_bytes(), bom+original.replace('café', 'coffee').encode(encoding))

    def test_unknown_encoding_and_mixed_eol_never_write(self):
        path = self.root/'legacy.txt'
        for original in (b'caf\xe9\r\n', b'one\r\ntwo\n', b'a\0b'):
            path.write_bytes(original); document = read_text_document(path)
            self.assertTrue(document.reason)
            with self.assertRaises(OSError): document.save('replaced')
            self.assertEqual(path.read_bytes(), original)

    def test_conflict_does_not_discard_newer_disk_content(self):
        path = self.root/'note.txt'; path.write_bytes(b'original')
        document = read_text_document(path); path.write_bytes(b'external change')
        with self.assertRaisesRegex(OSError, 'changed'): document.save('my draft')
        self.assertEqual(path.read_bytes(), b'external change')

    def test_editor_respects_readonly_and_output_bound(self):
        path = self.root/'readonly.txt'; path.write_bytes(b'original')
        path.chmod(0o444)
        try:
            document = read_text_document(path)
            self.assertTrue(document.reason)
            with self.assertRaises(OSError): document.save('edited')
            self.assertEqual(path.read_bytes(), b'original')
        finally: path.chmod(0o600)
        document = read_text_document(path)
        with self.assertRaisesRegex(OSError,'2 MiB'): document.save('x'*(TEXT_EDIT_LIMIT+1))
        self.assertEqual(path.read_bytes(), b'original')

    def test_record_size_refuses_new_data_without_discarding_saved_entries(self):
        records = WorkflowRecords(configparser.ConfigParser(), 'sessions')
        records.put('Kept', {'path': 'safe'})
        with self.assertRaisesRegex(ValueError, 'limit'):
            records.put('Huge', {'path': 'x'*(1024*1024)})
        self.assertEqual(records.read(), [{'name': 'Kept', 'data': {'path': 'safe'}}])

    def test_report_does_not_overwrite_source_or_link_and_replaces_atomically(self):
        source = self.root/'source.txt'; source.write_text('keep source')
        rows = [('Left only', source.name, source, None)]
        with self.assertRaises(OSError): write_comparison_report(source, rows, {})
        self.assertEqual(source.read_text(), 'keep source')
        target = self.root/'report.txt'; target.write_text('old report')
        with mock.patch('pycommander.workflowdata.os.replace', side_effect=OSError('locked')):
            with self.assertRaises(OSError): write_comparison_report(target, rows, {})
        self.assertEqual(target.read_text(), 'old report')
        self.assertEqual(list(self.root.glob('.pfc-report-*')), [])
        write_comparison_report(target, rows, {})
        self.assertIn('PFC comparison report', target.read_text())
        import os
        if os.name != 'nt':
            link = self.root/'alias.txt'; link.symlink_to(source)
            with self.assertRaises(OSError): write_comparison_report(link, rows, {})
            directory = self.root/'parent-alias'; directory.symlink_to(self.root, target_is_directory=True)
            with self.assertRaises(OSError): write_comparison_report(directory/source.name, rows, {})
            self.assertEqual(source.read_text(), 'keep source')

    def test_large_direct_selection_plans_without_cross_product(self):
        rows = [('Left only', f'docs/file-{i}.txt', self.root/f'file-{i}.txt', None)
                for i in range(10000)]
        actions = {row[1]: 'right' for row in rows}
        with mock.patch('pycommander.workflowdata.compare_path_blocked', return_value=False), \
             mock.patch.object(Path, 'is_file', return_value=True), \
             mock.patch.object(Path, 'exists', return_value=False), \
             mock.patch.object(Path, 'is_symlink', return_value=False):
            plans = compare_sync_plans(rows, actions, self.root, self.root/'destination')
        self.assertEqual(len(plans), 10000)

    def test_save_failure_keeps_original_and_cleans_staging(self):
        path = self.root/'note.txt'; path.write_bytes(b'original')
        document = read_text_document(path)
        import os
        if os.name == 'nt': self.skipTest('POSIX replace injection; Windows ReplaceFile tested in guest')
        with mock.patch('pycommander.textio.os.replace', side_effect=OSError('locked')):
            with self.assertRaises(OSError): document.save('edited')
        self.assertEqual(path.read_bytes(), b'original')
        self.assertEqual(list(self.root.glob('.pfc-edit-*')), [])

    def test_text_limit_and_large_line_fallback_are_bounded(self):
        path = self.root/'big.txt'; path.write_bytes(b'x'*(TEXT_EDIT_LIMIT+1))
        with self.assertRaisesRegex(OSError, '2 MiB'): read_text_document(path)
        rows, differences = aligned_text('x\n'*4100, 'x\n'*4099+'y\n')
        self.assertEqual(len(rows), 4100); self.assertEqual(differences, [4100])

    def test_type_detection_does_not_read_whole_file(self):
        path = self.root/'data.unknown'; path.write_text('hello')
        with mock.patch.object(Path, 'read_bytes', side_effect=AssertionError('unbounded read')):
            self.assertEqual(detect_compare_type(path, path), 'Text')

    def test_exclusion_names_paths_case_and_wildcards(self):
        for value in ('a/node_modules/b', 'NODE_MODULES', 'nested/.git/objects/x', 'build/cache.tmp'):
            self.assertTrue(compare_excluded(value, 'node_modules;*.tmp'))
        self.assertTrue(compare_excluded('src/generated/x', 'src/generated'))
        self.assertFalse(compare_excluded('src/generated/x', 'other/generated'))
        self.assertFalse(compare_excluded('src/module.py', '*.tmp'))

    def test_parent_sync_cannot_bypass_exclusions_or_skip(self):
        left, right = self.root/'left', self.root/'right'; left.mkdir(); right.mkdir()
        (left/'project/node_modules').mkdir(parents=True)
        (left/'project/node_modules/secret.js').write_text('excluded')
        (left/'project/a.txt').write_text('a'); (left/'project/b.txt').write_text('b')
        rows = list(folder_rows(left, right, excludes='node_modules'))
        plans = compare_sync_plans(rows, {'project': 'right', 'project/b.txt': 'skip'}, left, right)
        self.assertEqual(plans, [(left/'project/a.txt', right/'project/a.txt')])
        self.assertEqual(compare_sync_plans(rows, {'project': 'right'}, left, right, right_read_only=True), [])
        (left/'project/new.txt').write_text('created after scan')
        self.assertNotIn(left/'project/new.txt', [a for a,b in compare_sync_plans(rows, {'project':'right'},left,right)])

    def test_report_is_inert_relative_and_has_rules(self):
        rows = [('Different', '<script>alert(1)</script>.md', self.root/'private/a.md', None)]
        report = comparison_report(rows, {'excludes':'*.tmp', 'recursive':True})
        self.assertNotIn('<script>', report); self.assertNotIn(str(self.root), report)
        self.assertIn('&lt;script&gt;', report); self.assertIn('Content-Security-Policy', report)
        self.assertIn('excludes: *.tmp', report); self.assertIn('Different: 1', report)
        self.assertIn('Different\t', comparison_report(rows, {}, 'text'))

    def test_named_records_round_trip_replace_and_bounds(self):
        config = configparser.ConfigParser(interpolation=None); store = WorkflowRecords(config, 'test')
        store.put('工作', {'path':str(self.root/'100%/x')})
        store.put('工作', {'path':'updated'})
        self.assertEqual(len(store.read()), 1); self.assertEqual(store.read()[0]['data']['path'], 'updated')
        for index in range(39): store.put(str(index), {})
        with self.assertRaises(ValueError): store.put('forty-one', {})
        store.remove('0'); store.put('new', {})
        config.set('workflows', 'test', '{corrupt')
        self.assertEqual(store.read(), [])

    def test_reading_position_uses_unique_heading_when_changed(self):
        model = {'headings':[{'title':'Intro','start':0}, {'title':'Work','start':40}]}
        saved = reading_anchor(model, 55, .4, [1,100])
        self.assertEqual(saved['heading'], 'Work')
        self.assertEqual(resolve_reading_anchor(model, saved, [1,100]), ('fraction',.4,False))
        moved = {'headings':[{'title':'Work','start':80}]}
        self.assertEqual(resolve_reading_anchor(moved,saved,[2,150]),('offset',80,True))
        moved['headings'].append({'title':'Work','start':100})
        self.assertEqual(resolve_reading_anchor(moved,saved,[2,150]),('fraction',0.,True))

    def test_command_matching_uses_labels_categories_and_aliases(self):
        items=[('比較','Files','F9','Compare diff',None),('工作區','Tools','','workspace project',None)]
        self.assertEqual(command_matches(items,'compare'),items[:1])
        self.assertEqual(command_matches(items,'工作'),items[1:])
        self.assertEqual(command_matches(items,'files f9'),items[:1])
        self.assertEqual(command_matches(items,'missing'),[])

    def test_workspace_missing_paths_rejects_before_any_ui_change(self):
        data={'groups':[{'tabs':[{'path':str(self.root),'lock':'unlocked'}]} for _ in range(4)],
              'panels':1,'multi':2,'ratio':.33}
        self.assertEqual(len(validate_workspace(data)),4)
        data['groups'][2]['tabs'][0]['path']=str(self.root/'missing')
        with self.assertRaisesRegex(OSError,'No tabs were changed'): validate_workspace(data)

    def test_sync_rejects_broken_destination_link(self):
        import os
        if os.name == 'nt': self.skipTest('Needs Windows symbolic link privilege')
        left,right=self.root/'left',self.root/'right';left.mkdir();right.mkdir()
        source=left/'note.txt';source.write_text('safe')
        target=right/'note.txt';target.symlink_to(self.root/'outside.txt')
        rows=[('Unknown','note.txt',source,target)]
        self.assertEqual(compare_sync_plans(rows,{'note.txt':'right'},left,right),[])


if __name__ == '__main__': unittest.main()
