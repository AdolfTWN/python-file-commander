from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch, Mock
from types import SimpleNamespace

from pycommander.singlepanel import branch_segments, child_folders, root_folders


class FolderTreeTests(unittest.TestCase):
    def test_solid_branch_endings_and_ancestor_continuations(self):
        self.assertEqual(branch_segments((False,), True, 20, 30), [(10,15,10,30)])
        self.assertEqual(branch_segments((False,False), False, 20,30),
                         [(10,0,10,15),(10,15,30,15)])
        self.assertEqual(branch_segments((False,True,False), True,20,30),
                         [(10,0,10,30),(30,0,30,30),(30,15,50,15),(50,15,50,30)])

    def test_startup_guides_do_not_need_discovered_siblings(self):
        lines=branch_segments((False,)*6,True,20,30)
        for x in (10,30,50,70,90):
            self.assertIn((x,0,x,30),lines)
        self.assertEqual(lines,branch_segments((True,)*6,True,20,30))

    def test_tree_divider_waits_for_geometry_and_ignores_reentry(self):
        from pycommander.app import Commander
        split=Mock();split.panes.return_value=('tree','files');split.winfo_width.return_value=900
        owner=SimpleNamespace(split=split,_single_layout=True,_tree_ratio=1/3)
        events=[]
        def geometry():
            events.append('geometry')
            Commander._place_tree_sash(owner)
        split.update_idletasks.side_effect=geometry
        split.sashpos.side_effect=lambda *args:events.append(args)
        Commander._place_tree_sash(owner)
        self.assertEqual(events,['geometry',(0,300)])
        self.assertFalse(owner._placing_tree_sash)

    def test_scan_is_one_level_and_does_not_open_files_or_recurse(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); (root/'a').mkdir(); (root/'a'/'nested').mkdir()
            (root/'b').mkdir(); (root/'document.md').write_text('not read')
            with patch('builtins.open', side_effect=AssertionError('content read')):
                found, partial=child_folders(root, threading.Event())
            self.assertEqual(found,[root/'a',root/'b'])
            self.assertFalse(partial)

    def test_entry_budget_and_cancellation_are_bounded(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            for i in range(15): (root/str(i)).mkdir()
            found, partial=child_folders(root,threading.Event(),limit=3)
            self.assertEqual(len(found),3); self.assertTrue(partial)
            cancel=threading.Event();cancel.set()
            found, partial=child_folders(root,cancel)
            self.assertEqual(found,[]);self.assertTrue(partial)

    def test_scan_does_not_follow_symlink_cycles(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            try: (root/'cycle').symlink_to(root,target_is_directory=True)
            except OSError: self.skipTest('Symlink creation unavailable')
            found,_=child_folders(root,threading.Event())
            self.assertEqual(found,[])

    def test_roots_do_not_probe_disks(self):
        with patch.object(Path,'exists',side_effect=AssertionError('disk probe')):
            self.assertTrue(root_folders())


if __name__=='__main__':unittest.main()
