from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch, Mock
from types import SimpleNamespace

from pycommander.singlepanel import branch_segments, child_folders, folder_has_children, root_folders


class FolderTreeTests(unittest.TestCase):
    def test_late_negative_hint_never_replaces_navigation_children(self):
        import queue
        from pycommander.singlepanel import RootFolderTree
        for pending, loaded, branch in ((True, False, False), (False, True, False),
                                         (False, False, True)):
            cancel = threading.Event(); results = queue.Queue()
            results.put((cancel, 'folder', False)); results.put((cancel, None, None))
            tree = Mock()
            owner = SimpleNamespace(_probe_results=results, _probe_cancel=cancel,
                paths={'folder': Path('/folder')}, loaded={'folder'} if loaded else set(),
                pending={'folder': object()} if pending else {}, _child_hints={},
                _has_branch=lambda _iid: branch, tree=tree)
            RootFolderTree._poll_probes(owner)
            self.assertIsNone(owner._probe_cancel)
            self.assertEqual(owner._child_hints, {})
            tree.delete.assert_not_called()

    def test_child_hint_distinguishes_files_empty_and_actual_subfolders(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.assertIs(folder_has_children(root, threading.Event()), False)
            (root/'rule.md').write_text('not read')
            with patch('builtins.open', side_effect=AssertionError('content read')):
                self.assertIs(folder_has_children(root, threading.Event()), False)
                (root/'nested').mkdir()
                self.assertIs(folder_has_children(root, threading.Event()), True)

    def test_child_hint_stops_at_first_directory(self):
        directory = Mock(); directory.is_dir.return_value = True
        entries = Mock(); entries.__enter__ = Mock(return_value=iter([directory, None]))
        entries.__exit__ = Mock(return_value=False)
        with tempfile.TemporaryDirectory() as raw, patch('os.scandir', return_value=entries):
            self.assertIs(folder_has_children(Path(raw), threading.Event()), True)
        directory.is_dir.assert_called_once_with(follow_symlinks=False)

    def test_child_hint_limits_errors_and_cancel_remain_unknown(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); (root/'file').touch()
            self.assertIsNone(folder_has_children(root, threading.Event(), limit=0))
            self.assertIsNone(folder_has_children(root, threading.Event(), seconds=-1))
            cancel = threading.Event(); cancel.set()
            with patch('os.scandir', side_effect=AssertionError('cancel must not scan')):
                self.assertIsNone(folder_has_children(root, cancel))
            with patch('os.scandir', side_effect=PermissionError('denied')):
                self.assertIsNone(folder_has_children(root, threading.Event()))
            entry = Mock(); entry.is_dir.side_effect = PermissionError('denied entry')
            entries = Mock(); entries.__enter__ = Mock(return_value=iter([entry]))
            entries.__exit__ = Mock(return_value=False)
            with patch('os.scandir', return_value=entries):
                self.assertIsNone(folder_has_children(root, threading.Event()))

    def test_child_hint_never_probes_drives_shares_or_reparse_placeholders(self):
        from pathlib import PureWindowsPath
        for path in (Path(Path.cwd().anchor), PureWindowsPath(r'\\server\share\folder')):
            with patch('os.scandir', side_effect=AssertionError('unsafe scan')):
                self.assertIsNone(folder_has_children(path, threading.Event()))
        for flags, mode in ((0x400, 0o40755), (0x1000, 0o40755), (0, 0o120777)):
            with patch.object(Path, 'lstat', return_value=SimpleNamespace(
                    st_file_attributes=flags, st_mode=mode)), patch('os.scandir',
                    side_effect=AssertionError('linked/cloud scan')):
                self.assertIsNone(folder_has_children(Path('/example/folder'), threading.Event()))

    def test_branch_endings_and_ancestor_continuations(self):
        self.assertEqual(branch_segments((False,), True, 20, 30), [(10,15,10,30)])
        self.assertEqual(branch_segments((False,False), False, 20,30),
                         [(10,0,10,15),(10,15,30,15)])
        self.assertEqual(branch_segments((False,True,False), True,20,30),
                         [(10,0,10,30),(30,0,30,15),(30,15,50,15),(50,15,50,30)])

    def test_last_child_chain_does_not_draw_phantom_continuations(self):
        lines=branch_segments((False,)*6,True,20,30)
        self.assertEqual(lines, [(90,0,90,15),(90,15,110,15),(110,15,110,30)])
        for x in (10,30,50,70):
            self.assertNotIn((x,0,x,30),lines)

    def test_only_real_later_siblings_continue_ancestor_lines(self):
        from itertools import product
        for flags in product((False,True), repeat=6):
            for expanded in (False,True):
                lines=branch_segments(flags,expanded,20,30)
                for level in range(1,5):
                    x=(level-.5)*20
                    self.assertEqual((x,0,x,30) in lines,flags[level])
                self.assertIn((90,0,90,30 if flags[-1] else 15),lines)
                self.assertEqual((110,15,110,30) in lines,expanded)

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

    def test_scan_reveal_keeps_whole_row_but_respects_user_scroll_and_collapse(self):
        from pycommander.singlepanel import RootFolderTree
        tree=Mock();tree.winfo_viewable.return_value=True;tree.exists.return_value=True
        tree.selection.return_value=('target',);tree.bbox.return_value=(0,35,100,30)
        tree.winfo_height.return_value=60;tree.parent.return_value=''
        owner=SimpleNamespace(tree=tree,_view_epoch=4,_view_settle_job=None,
                              _draw_lines=Mock(),after_idle=Mock(),_settle_scan_selection=Mock())
        RootFolderTree._settle_scan_selection(owner,'target',4,32)
        tree.see.assert_called_once_with('target');owner._draw_lines.assert_called_once()
        tree.see.reset_mock();owner.after_idle.reset_mock()
        # User wheel/scrollbar/key input invalidates the old completion callback.
        RootFolderTree._settle_scan_selection(owner,'target',3,32)
        tree.see.assert_not_called();owner.after_idle.assert_not_called()
        # Nor should an asynchronously completed scan reopen a collapsed path.
        tree.bbox.return_value=();tree.parent.return_value='parent';tree.item.return_value=False
        RootFolderTree._settle_scan_selection(owner,'target',4,32)
        tree.see.assert_not_called();owner.after_idle.assert_not_called()

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
