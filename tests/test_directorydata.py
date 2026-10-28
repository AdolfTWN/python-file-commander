import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pycommander.directorydata import directory_items,listing_items,listing_signature,ordered_listing
from pycommander.columnsettings import modified_text


class DirectoryDataTests(unittest.TestCase):
    def test_cross_folder_same_name_missing_result_has_stable_full_identity(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);(root/'one').mkdir();(root/'two').mkdir()
            first=root/'one'/'config.json';second=root/'two'/'config.json'
            first.write_text('{}');second.write_text('{}')
            self.assertNotEqual(listing_signature(listing_items([first])),
                                listing_signature(listing_items([second])))
            first.unlink();rows=listing_items([first,second])
            self.assertEqual(listing_signature(rows),listing_signature(tuple(reversed(rows))))
            self.assertEqual(2,len(listing_signature(rows)))

    def test_one_metadata_read_per_item_and_stable_numeric_sort(self):
        with tempfile.TemporaryDirectory() as raw:
            folder=Path(raw);a=folder/'a.md';a.write_text('a');b=folder/'b.txt';b.write_text('bb')
            missing=folder/'missing';original=Path.stat;calls=[]
            def stat(path,*args,**kw):calls.append(path);return original(path,*args,**kw)
            with patch.object(Path,'stat',stat):rows=listing_items((a,b,missing))
            self.assertEqual([a,b,missing],calls)
            self.assertEqual([missing,a,b],[r.path for r in ordered_listing(rows,'size')])
            self.assertEqual([b,a,missing],[r.path for r in ordered_listing(rows,'size',True)])
            self.assertEqual(listing_signature(rows),listing_signature(tuple(reversed(rows))))

    def test_flags_and_explicit_reveal_keep_existing_visibility_semantics(self):
        with tempfile.TemporaryDirectory() as raw:
            folder=Path(raw)
            for name in ('.hidden','system','visible'):(folder/name).write_text(name)
            with patch('pycommander.directorydata.is_system',side_effect=lambda p:p.name=='system'):
                self.assertEqual(['visible'],[r.path.name for r in directory_items(folder)])
                self.assertEqual({'.hidden','visible'}, {r.path.name for r in directory_items(folder,reveal=folder/'.hidden')})
                self.assertEqual(3,len(directory_items(folder,True,True)))

    def test_directories_first_and_extension_order(self):
        with tempfile.TemporaryDirectory() as raw:
            folder=Path(raw);(folder/'z.dir').mkdir();(folder/'b.txt').write_text('b');(folder/'a.md').write_text('a')
            rows=directory_items(folder)
            for reverse in (False,True):
                self.assertEqual('z.dir',ordered_listing(rows,'ext',reverse,False)[0].path.name)

    def test_invalid_timestamps_do_not_break_display(self):
        for timestamp in (float('nan'),float('inf'),float('-inf'),1e50,-1e50):
            self.assertEqual('—',modified_text(timestamp,'ymd','24'))


if __name__=='__main__':unittest.main()
