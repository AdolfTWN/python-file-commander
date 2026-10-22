import base64
import json
import unittest
from unittest.mock import patch,Mock
from pycommander.rendercore import (structured_preview,structured_search,table_preview,patch_preview,static_preview_html,
    static_preview_svg,safe_preview_image,safe_preview_css,notebook_preview_html,preview_vendor,RENDER_EXTENSIONS)
from pycommander.renderbrowser import raster_preview,re_preview_directive,_preview_browser_port
from pycommander.preview import markdown_document
from pycommander.previewassets import PREVIEW_DEPENDENCY_NOTICES
from pycommander.renderui import preview_cell_text


class StructuredPreviewTests(unittest.TestCase):
    def test_search_reveals_late_real_ancestor_path_and_occurrences(self):
        source=json.dumps({'early':list(range(5000)),'nested':{'key':'AW27 then AW27'}})
        original=structured_preview(source,'.json')
        self.assertTrue(original['truncated'])
        result=structured_search(source,'.json','AW27',index=1)
        self.assertEqual((result['count'],result['index'],result['partial']),(2,1,False))
        self.assertEqual([r['label'] for r in result['rows']],['$','nested','key'])
        self.assertEqual(result['rows'][-1]['path'],'/nested/key')
        self.assertEqual(result['start'],10)
        self.assertEqual(structured_search(source,'.json','aw27',True)['count'],0)

    def test_search_duplicate_keys_have_distinct_stable_ids_and_limits_are_honest(self):
        source='{"same":"AW27","same":"AW27"}'
        first=structured_search(source,'.json','AW27',index=0)
        second=structured_search(source,'.json','AW27',index=-1)
        self.assertNotEqual(first['rows'][-1]['id'],second['rows'][-1]['id'])
        result=structured_search(json.dumps(['hit']*6000),'.json','hit')
        self.assertEqual(result['count'],5000);self.assertTrue(result['partial'])

    def test_cell_line_breaks_display_once_without_changing_raw_value(self):
        for newline in ('\n','\r\n','\r'):
            raw='line one'+newline+'line two'
            self.assertEqual(preview_cell_text(raw),'line one ↵ line two')
            self.assertIn(newline,raw)
    def test_portable_contains_upstream_license_notices(self):
        for name in ('mermaid 12.2.0','yaml 6.0.3','tomli 2.5.0','Permission is hereby granted'):
            self.assertIn(name,PREVIEW_DEPENDENCY_NOTICES)
    def test_browser_port_retries_windows_lock_and_partial_publication(self):
        active=Mock();active.read_text.side_effect=[PermissionError('locked'),'','partial','65536','12345\n/devtools/browser/id']
        process=Mock();process.poll.return_value=None
        with patch('pycommander.renderbrowser.time.monotonic',return_value=1),patch('pycommander.renderbrowser.time.sleep'):
            self.assertEqual(_preview_browser_port(active,process,2),12345)
        process.poll.return_value=1
        with patch('pycommander.renderbrowser.time.monotonic',return_value=1),self.assertRaises(ValueError):
            _preview_browser_port(active,process,2)
        with patch('pycommander.renderbrowser.time.monotonic',return_value=3),self.assertRaises(TimeoutError):
            _preview_browser_port(active,process,2)
    def test_json_preserves_numbers_ids_and_duplicate_keys(self):
        model=structured_preview('{"id":"001","large":12345678901234567890123456789,"n":1.2300e-9,"id":"002","ok":true}', '.json')
        values=[r['value'] for r in model['rows']]
        for value in ('001','002','12345678901234567890123456789','1.2300e-9','true'):self.assertIn(value,values)
        self.assertIn('Duplicate',model['notice'])
        self.assertEqual([r['kind'] for r in model['rows'] if r['label']=='n'],['number'])
    def test_json_rejects_nonfinite_and_invalid(self):
        for text in ('{"n":NaN}','{"n":Infinity}','{',''):
            with self.subTest(text=text),self.assertRaises(ValueError):structured_preview(text,'.json')
    def test_jsonl_keeps_record_boundaries_and_reports_bad_line(self):
        m=structured_preview('{"a":1}\n{"b":"two"}\n','.jsonl')
        self.assertEqual([r['label'] for r in m['rows'] if not r['parent']],['Record 1','Record 2'])
        for text in ('{}\n\n{}','{}\nbroken'):
            with self.assertRaisesRegex(ValueError,'line 2'):structured_preview(text,'.ndjson')
    def test_tree_limits_are_explicit_and_parent_ids_valid(self):
        m=structured_preview(json.dumps(list(range(4000))),'.json')
        self.assertLessEqual(len(m['rows']),3000);self.assertIn('3,000',m['notice'])
        self.assertNotIn('source',m)
        seen={''}
        for r in m['rows']:self.assertIn(r['parent'],seen);seen.add(r['id'])
    def test_large_repeated_paths_cannot_expand_model_unboundedly(self):
        m=structured_preview(json.dumps({'x'*100000:dict.fromkeys(map(str,range(100)),0)}),'.json')
        self.assertTrue(m['truncated']);self.assertLess(len(m['content']),3*1024*1024)
    def test_yaml_aliases_and_tags_are_never_constructed(self):
        m=structured_preview('a: &a\n  x: 001\n  recurse: *a\ncommand: !!python/object/apply:os.system ["false"]\n','.yaml')
        self.assertIn('001',[r['value'] for r in m['rows']]);self.assertIn('Alias / recursive reference',[r['value'] for r in m['rows']])
        self.assertIn('false',[r['value'] for r in m['rows']])
    def test_yaml_multidocument_and_complex_keys_are_bounded(self):
        m=structured_preview('---\na: 1\n---\nb: 2\n','.yml')
        self.assertEqual(len([r for r in m['rows'] if not r['parent']]),2)
    def test_toml_sections_and_decimal_literal(self):
        m=structured_preview('[tool.agent]\nid="001"\nratio=1.2300\n','.toml')
        self.assertIn('/tool/agent/ratio',[r['path'] for r in m['rows']]);self.assertIn('1.2300',[r['value'] for r in m['rows']])
        self.assertEqual(preview_vendor('tomli').loads('n=1'),{'n':1})
    def test_csv_preserves_text_quotes_newlines_and_formula(self):
        m=table_preview('ID,body,value\r\n001,"one,two\nnext",=SUM(A1:A2)\r\n','.csv')
        self.assertEqual(m['columns'],['ID','body','value'])
        self.assertEqual(m['rows'],[['001','one,two\nnext','=SUM(A1:A2)']])
    def test_tsv_ragged_and_empty(self):
        m=table_preview('a\tb\n1\n2\t3\t4\n','.tsv')
        self.assertEqual(len(m['columns']),3);self.assertEqual(m['rows'][0],['1','',''])
        self.assertIn('Empty',table_preview('','.csv')['notice'])
    def test_table_limits_and_malformed_quotes(self):
        m=table_preview('x\n'+'item\n'*1100,'.csv');self.assertLessEqual(len(m['rows']),1000);self.assertIn('limited',m['notice'])
        with self.assertRaises(Exception):table_preview('a,b\n"unclosed','.csv')
    def test_ragged_padding_counts_toward_the_display_cell_limit(self):
        m=table_preview('\t'.join('c'+str(i) for i in range(200))+'\n'+'value\n'*1000,'.tsv')
        self.assertLessEqual((len(m['rows'])+1)*len(m['columns']),20000)
        self.assertTrue(m['truncated']);self.assertIn('limited',m['notice'])
    def test_patch_model_never_applies_and_preserves_all_text(self):
        source='diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1 +1 @@\n-old\n+new\n'
        m=patch_preview(source);self.assertEqual(m['content'],source)
        self.assertTrue(m['sections']);self.assertIn('never applied',m['notice'])
        self.assertEqual({s[2] for s in m['spans']},{'render_heading','render_hunk','render_add','render_remove'})


class StaticPreviewSafetyTests(unittest.TestCase):
    def test_html_removes_active_content_and_all_resource_links(self):
        text='<h1 onclick="evil()">Title</h1><script>evil()</script><iframe src="file:///secret"></iframe><form><input></form><img src="http://example.invalid/x"><a href="javascript:evil()">Label</a><p style="background:url(file:///secret)">safe</p>'
        result=static_preview_html(text)
        for token in ('evil','iframe','onclick','file:','http:','javascript:','<form','<input'):self.assertNotIn(token,result)
        self.assertIn('Title',result);self.assertIn('Label',result);self.assertIn('safe',result)
    def test_html_malformed_nesting_does_not_restore_scripts(self):
        for text in ('<script><b></script><p>safe</p>','<svg><foreignObject><script>bad()</script></foreignObject></svg><p>safe</p>'):
            result=static_preview_html(text);self.assertNotIn('bad()',result);self.assertNotIn('<script',result)
    def test_css_blocks_external_imports_and_escaped_urls(self):
        for css in ('@import "https://bad"','background:url(https://bad)','background:u\\72l(http://bad)','behavior:url(x)'):
            self.assertEqual(safe_preview_css(css),'')
        self.assertTrue(safe_preview_css('fill:url(#gradient);color:#123'))
    def test_svg_removes_events_external_images_and_foreign_objects(self):
        text='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50"><script>bad()</script><foreignObject><p>x</p></foreignObject><rect onclick="bad()" width="50" height="20" fill="red"/><image href="file:///secret"/><text x="5" y="40">Hi</text></svg>'
        result=static_preview_svg(text)
        for value in ('script','onclick','foreignObject','file:'):self.assertNotIn(value,result)
        self.assertIn('rect',result);self.assertIn('Hi',result)
    def test_svg_entities_and_wrong_root_rejected(self):
        for text in ('<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///secret">]><svg>&x;</svg>','<html/>'):
            with self.assertRaises(ValueError):static_preview_svg(text)
    def test_oversized_or_external_embedded_images_are_rejected(self):
        self.assertIsNone(safe_preview_image('https://bad/image.png'))
        fake=b'\x89PNG\r\n\x1a\n'+b'\0'*8+(10000).to_bytes(4,'big')*2
        self.assertIsNone(safe_preview_image('data:image/png;base64,'+base64.b64encode(fake).decode()))
    def test_notebook_only_stored_content_no_execution(self):
        data={'nbformat':4,'cells':[{'cell_type':'markdown','source':['# Heading']},
              {'cell_type':'code','source':['print("not executed")'],'outputs':[{'output_type':'stream','text':['stored output']},
                 {'output_type':'display_data','data':{'text/html':'<b>saved</b><script>bad()</script>'}}]}]}
        result,notice=notebook_preview_html(json.dumps(data))
        self.assertIn('<h1>Heading</h1>',result);self.assertIn('not executed',result);self.assertIn('stored output',result)
        self.assertIn('saved',result);self.assertNotIn('<script',result);self.assertIn('no cell execution',notice)
    def test_notebook_output_styles_cannot_hide_other_cells(self):
        data={'nbformat':4,'cells':[{'cell_type':'code','source':'safe','outputs':[{'data':{'text/html':'<style>body{display:none}</style><div style="position:fixed">saved</div>'}}]}]}
        result,_=notebook_preview_html(json.dumps(data));self.assertNotIn('display:none',result);self.assertNotIn('position:fixed',result)
    def test_unknown_notebook_and_diagram_configuration_rejected(self):
        with self.assertRaises(ValueError):notebook_preview_html('{"nbformat":3}')
        self.assertTrue(re_preview_directive('%%{init:{securityLevel:"loose"}}%%\ngraph TD\na-->b'))
        self.assertFalse(re_preview_directive('flowchart LR\nA-->B'))
    def test_missing_graphics_engine_is_explicit(self):
        with patch('pycommander.renderbrowser.preview_browser_path',return_value=None),self.assertRaisesRegex(ValueError,'showing Source'):
            raster_preview('<svg/>','.svg')
    def test_md_mermaid_discovery_preserves_text_and_heading_offsets(self):
        for newline in ('\n','\r\n'):
            with self.subTest(newline=newline):
                m=markdown_document('# Before\n\n```mermaid\nflowchart LR\n A-->B\n```\n\n# After\ntext'.replace('\n',newline))
                self.assertEqual(len(m['diagrams']),1)
                d=m['diagrams'][0];self.assertEqual(m['content'][d['start']:d['end']],d['source'])
                self.assertEqual(m['content'][m['headings'][1]['start']:].splitlines()[0],'After')
    def test_all_requested_suffixes_have_handlers(self):
        self.assertTrue({'.json','.jsonl','.csv','.tsv','.svg','.yaml','.toml','.ipynb','.mmd','.diff','.patch','.html'}<=RENDER_EXTENSIONS)


if __name__=='__main__':unittest.main()
