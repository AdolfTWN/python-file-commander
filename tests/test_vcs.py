import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pycommander.vcs import (_CACHE, _git_root_summary, _git_status, folder_statuses,
                             is_metadata_path, status_for)


class VCSOverlayTests(unittest.TestCase):
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
