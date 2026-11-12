import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from pycommander.directorydata import directory_items,listing_items,listing_signature,ordered_listing
from pycommander.columnsettings import modified_text


class DirectoryDataTests(unittest.TestCase):
    def test_windows_enumerated_flags_avoid_per_file_attribute_or_stat_queries(self):
        import pycommander.directorydata as data
        with tempfile.TemporaryDirectory() as raw:
            folder=Path(raw)
            for name in ('hidden', 'system', 'visible', '.dot'):(folder/name).touch()
            calls=[]
            class Entry:
                def __init__(self,name):self.name=name
                def stat(self,*,follow_symlinks=True):
                    calls.append((self.name,follow_symlinks))
                    return SimpleNamespace(st_file_attributes={'hidden':2,'system':4,'visible':0,'.dot':0}[self.name])
            class Scan:
                def __enter__(self):return iter(Entry(n) for n in ('hidden','system','visible','.dot'))
                def __exit__(self,*args):pass
            with patch.object(data,'os',SimpleNamespace(name='nt',scandir=lambda _:Scan())),patch.object(Path,'stat',side_effect=AssertionError('Must not reopen ordinary files')):
                self.assertEqual(['visible'],[r.path.name for r in data.directory_items(folder)])
                self.assertEqual([('hidden',False),('system',False),('visible',False),('visible',True)],calls)
                calls.clear()
                self.assertEqual(4,len(data.directory_items(folder,True,True)))
                self.assertEqual(8,len(calls))
                self.assertEqual({'visible','hidden'}, {r.path.name for r in data.directory_items(folder,reveal=folder/'hidden')})

    def test_windows_filter_uses_link_attributes_but_metadata_follows_link(self):
        import pycommander.directorydata as data
        from contextlib import nullcontext
        metadata=SimpleNamespace(st_mode=0o40755,st_size=20,st_mtime_ns=123)
        entry=SimpleNamespace(name='junction',stat=lambda *,follow_symlinks=True:
                              metadata if follow_symlinks else SimpleNamespace(st_file_attributes=0x400))
        with patch.object(data,'os',SimpleNamespace(name='nt',scandir=lambda _:nullcontext(iter([entry])))),patch.object(Path,'stat',return_value=metadata) as followed:
            rows=data.directory_items(Path('/fixture'))
        followed.assert_called_once_with()
        self.assertIs(rows[0].metadata,metadata);self.assertTrue(rows[0].is_dir)

    def test_windows_cancellation_even_if_every_entry_is_hidden(self):
        import pycommander.directorydata as data
        import threading
        from contextlib import nullcontext
        cancelled=threading.Event()
        def stat(**_):
            cancelled.set();return SimpleNamespace(st_file_attributes=2)
        entry=SimpleNamespace(name='hidden',stat=stat)
        with patch.object(data,'os',SimpleNamespace(name='nt',scandir=lambda _:nullcontext(iter([entry]*10)))):
            with self.assertRaises(data.DirectoryReadCancelled):
                data.directory_items(Path('/fixture'),cancelled=cancelled)
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
