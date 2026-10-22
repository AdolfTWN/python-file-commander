"""Deterministic parser exploration; small mutated inputs, no document execution."""
import csv
import json
import random
import unittest

from pycommander.rendercore import structured_preview,table_preview,notebook_preview_html,preview_vendor


class RenderParserReliabilityTests(unittest.TestCase):
    def test_mutated_structures_fail_closed_or_keep_valid_parent_links(self):
        rng=random.Random(1838)
        expected_errors=(ValueError,TypeError,RecursionError,preview_vendor('yaml').YAMLError)
        fixtures={'.json':'{"a":[1,true,null,"😀"],"b":{"x":"value"}}',
                  '.yaml':'a: [one, two]\nb:\n  x: value\n',
                  '.toml':'a=[1,2]\n[b]\nx="value"\n',
                  '.jsonl':'{"a":1}\n{"b":"value"}\n'}
        for suffix,text in fixtures.items():
            variants=[text]+[text[:(at:=rng.randrange(len(text)+1))]+rng.choice(['[','"',':','\n','中'])+text[at:] for _ in range(30)]
            for value in variants:
                with self.subTest(suffix=suffix,value=value):
                    try:model=structured_preview(value,suffix)
                    except expected_errors:continue
                    seen={''}
                    for row in model['rows']:
                        self.assertIn(row['parent'],seen);self.assertNotIn(row['id'],seen)
                        self.assertTrue(all(isinstance(row[key],str) for key in ('id','parent','label','value','path')))
                        seen.add(row['id'])
    def test_csv_limit_restored_after_success_and_failure(self):
        previous=csv.field_size_limit()
        try:
            csv.field_size_limit(99)
            value='x'*150000
            self.assertEqual(table_preview('Data\n'+value,'.csv')['rows'],[[value]])
            self.assertEqual(csv.field_size_limit(),99)
            with self.assertRaises(csv.Error):table_preview('Data\n"unfinished','.csv')
            self.assertEqual(csv.field_size_limit(),99)
        finally:csv.field_size_limit(previous)
    def test_notebook_limits_propagate_without_changing_default_return_contract(self):
        data={'nbformat':4,'cells':[{'cell_type':'markdown','source':'# Cell'}]*61}
        source=json.dumps(data)
        self.assertEqual(len(notebook_preview_html(source)),2)
        body,notice,partial=notebook_preview_html(source,with_limits=True)
        self.assertTrue(partial);self.assertIn('60',notice);self.assertNotIn('Cell 61',body)
        data['cells']=data['cells'][:1]
        self.assertFalse(notebook_preview_html(json.dumps(data),with_limits=True)[2])


if __name__=='__main__':unittest.main()
