import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pycommander import vcs
from pycommander.vcs import (_CACHE, _git_root_summary, _git_status, folder_statuses,
                             is_metadata_path, status_for)


class VCSOverlayTests(unittest.TestCase):
    def setUp(self):
        vcs.invalidate_vcs_cache()

    def tearDown(self):
        vcs.invalidate_vcs_cache()

    def test_status_aggregation_does_not_resolve_each_file_or_follow_link_target(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            path = root / 'sub' / 'tracked-link'
            states = {}
            with patch.object(Path, 'resolve', side_effect=AssertionError('per-file filesystem lookup')):
                vcs._merge(states, path, 'modified', root)
                self.assertEqual(status_for(states, path), 'modified')
                self.assertEqual(status_for(states, root / 'sub'), 'modified')
                self.assertEqual(status_for(states, root), 'modified')

    def test_parent_scan_supplies_child_overlays_without_another_git_command(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve(); (root / '.git').mkdir()
            child = root / 'sub'; child.mkdir()
            states = {os.path.normcase(str(child / 'file')): 'clean'}
            with patch.object(vcs, '_git_status', return_value=states) as scan, \
                    patch.object(vcs, '_child_repository_statuses', return_value={}):
                self.assertEqual(folder_statuses(root), states)
                self.assertEqual(folder_statuses(child), states)
                self.assertEqual(vcs.cached_folder_statuses(child), states)
                self.assertEqual(scan.call_count, 1)

    def test_display_snapshot_is_bounded_and_does_not_delay_fresh_query(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve(); (root / '.git').mkdir()
            clock = 10.0
            with patch.object(vcs.time, 'monotonic', side_effect=lambda: clock), \
                    patch.object(vcs, '_git_status', return_value={'old': 'modified'}) as scan, \
                    patch.object(vcs, '_child_repository_statuses', return_value={}):
                folder_statuses(root)
                clock += vcs._CACHE_SECONDS + 1
                self.assertEqual(vcs.cached_folder_statuses(root), {'old': 'modified'})
                scan.return_value = {'new': 'clean'}
                self.assertEqual(folder_statuses(root), {'new': 'clean'})
                self.assertEqual(scan.call_count, 2)
                clock += vcs._DISPLAY_CACHE_SECONDS
                self.assertIsNone(vcs.cached_folder_statuses(root))

    def test_unrelated_navigation_does_not_probe_filesystem_for_cached_overlay(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            with patch.object(vcs, '_git_status', return_value={}), \
                    patch.object(vcs, '_child_repository_statuses', return_value={}):
                folder_statuses(root / 'one')
            with patch.object(Path, 'exists', side_effect=AssertionError('unrelated marker probe')):
                self.assertIsNone(vcs.cached_folder_statuses(root / 'two'))

    def test_parent_summary_is_not_descendant_coverage_and_nested_roots_are_isolated(self):
        with tempfile.TemporaryDirectory() as raw:
            outer = Path(raw).resolve(); project = outer / 'project'
            (project / '.git').mkdir(parents=True)
            child = project / 'sub'; child.mkdir()
            with patch.object(vcs, '_git_status', return_value=None), \
                    patch.object(vcs, '_svn_status', return_value=None), \
                    patch.object(vcs, '_child_repository_statuses', return_value={str(project): 'modified'}):
                folder_statuses(outer)
            self.assertIsNone(vcs.cached_folder_statuses(project))
            with patch.object(vcs, '_git_status', return_value={'outer': 'clean'}), \
                    patch.object(vcs, '_child_repository_statuses', return_value={}):
                folder_statuses(project)
            self.assertIsNotNone(vcs.cached_folder_statuses(child))
            (child / '.git').write_text('gitdir: elsewhere', encoding='utf-8')
            self.assertIsNone(vcs.cached_folder_statuses(child))
            vcs.invalidate_vcs_cache()
            self.assertIsNone(vcs.cached_folder_statuses(project))

    def test_git_commands_never_create_a_windows_console(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); (root / ".git").mkdir()
            completed = subprocess.CompletedProcess([], 0, stdout=b"", stderr=b"")
            with patch("pycommander.vcs.subprocess.run", return_value=completed) as run:
                self.assertEqual(_git_status(root), {})
            self.assertEqual(run.call_count, 2)
            expected = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.assertTrue(all(call.kwargs.get("creationflags") == expected
                                for call in run.call_args_list))

    def test_metadata_folder_is_not_status_scanned(self):
        with tempfile.TemporaryDirectory() as raw:
            metadata = Path(raw) / ".git" / "objects"
            metadata.mkdir(parents=True)
            self.assertTrue(is_metadata_path(metadata))
            self.assertEqual(folder_statuses(metadata), {})
    def test_git_modified_and_untracked_statuses_include_parent_folder(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            tracked = root / "tracked.txt"
            tracked.write_text("one", encoding="utf-8")
            clean = root / "clean.txt"
            clean.write_text("clean", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "tracked.txt", "clean.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=PFC Test",
                            "-c", "user.email=pfc@example.invalid", "commit", "-qm", "base"],
                           check=True)
            tracked.write_text("two", encoding="utf-8")
            untracked = root / "new.txt"
            untracked.write_text("new", encoding="utf-8")
            statuses = folder_statuses(root)
            self.assertEqual(status_for(statuses, tracked), "modified")
            self.assertEqual(status_for(statuses, untracked), "untracked")
            self.assertEqual(status_for(statuses, clean), "clean")
            self.assertEqual(status_for(statuses, root), "modified")

    def test_repository_root_overlay_is_visible_from_outer_folder(self):
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw); root = parent / "project"; root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            tracked = root / "tracked.txt"; tracked.write_text("one", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=PFC Test",
                            "-c", "user.email=pfc@example.invalid", "commit", "-qm", "base"],
                           check=True)
            _CACHE.clear()
            self.assertEqual(status_for(folder_statuses(parent), root), "clean")
            tracked.write_text("two", encoding="utf-8")
            _CACHE.clear()
            self.assertEqual(status_for(folder_statuses(parent), root), "modified")
            ordinary = parent / "ordinary"; ordinary.mkdir()
            self.assertIsNone(status_for(folder_statuses(parent), ordinary))

    def test_repository_root_is_not_clean_when_upstream_is_ahead_or_behind(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); (root / ".git").mkdir()
            completed = subprocess.CompletedProcess(
                [], 0, stdout=b"## main...origin/main [ahead 1]\0", stderr=b"")
            with patch("pycommander.vcs.subprocess.run", return_value=completed):
                self.assertEqual(_git_root_summary(root), "modified")


if __name__ == "__main__":
    unittest.main()
