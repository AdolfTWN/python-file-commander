"""Disposable reliability fixtures, shared by source, portable and Windows tests."""
from __future__ import annotations

import configparser
import ctypes
import importlib
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PORTABLE = __name__ == "__main__" and "pfc" in sys.argv
if PORTABLE:
    sys.argv.remove("pfc")
    fileops = archivefs = clipboard = shellmenu = rename = app = search = space = vcs = importlib.import_module("pfc")
else:
    fileops = importlib.import_module("pycommander.fileops")
    archivefs = importlib.import_module("pycommander.archivefs")
    clipboard = importlib.import_module("pycommander.clipboard")
    shellmenu = importlib.import_module("pycommander.shellmenu")
    rename = importlib.import_module("pycommander.multirename")
    app = importlib.import_module("pycommander.app")
    search = importlib.import_module("pycommander.search")
    space = importlib.import_module("pycommander.spaceanalyzer")
    vcs = importlib.import_module("pycommander.vcs")


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pfc-reliability-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def link(self, target, path, directory=False):
        try:
            path.symlink_to(target, target_is_directory=directory)
        except OSError as exc:
            self.skipTest(f"Symlink privilege unavailable: {type(exc).__name__}")

    def archive(self, path=None, entries=None):
        path = path or self.root / "sample.zip"
        with zipfile.ZipFile(path, "w") as output:
            for name, data in (entries or {"note.txt": b"original"}).items():
                output.writestr(name, data)
        return path

    def test_python311_junction_is_leaf_for_count_and_progress_delete(self):
        junction = self.root / "junction"
        info = SimpleNamespace(st_reparse_tag=0xA0000003)
        with patch.object(fileops.os.path, "isjunction", None, create=True), \
                patch.object(fileops.os, "lstat", return_value=info), \
                patch.object(fileops.os.path, "isdir", return_value=True), \
                patch.object(fileops.os.path, "islink", return_value=False), \
                patch.object(fileops.os, "scandir") as scan, \
                patch.object(fileops.os, "rmdir") as remove:
            self.assertEqual(fileops._count_delete_entries(junction), 1)
            removed = []
            fileops._remove_with_progress(junction, removed.append)
            self.assertEqual(removed, [junction])
            remove.assert_called_once()
            scan.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Native Windows junction fixture")
    def test_native_junction_target_survives_progress_deletion(self):
        protected = self.root / "external"
        protected.mkdir()
        sentinel = protected / "keep.txt"
        sentinel.write_text("protected", encoding="utf-8")
        selected = self.root / "selected"
        selected.mkdir()
        junction = selected / "junction"
        result = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(junction), str(protected)],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, "Cannot construct the Windows junction fixture")
        self.assertEqual(shellmenu.context_menu_paths([junction]), [junction])
        self.assertFalse(space.scan_space(junction).children)
        outcome = fileops.delete_items([selected], progress=lambda *_: None)
        self.assertFalse(outcome.failures)
        self.assertFalse(selected.exists())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "protected")

    def test_dangling_copy_destination_does_not_write_outside(self):
        source_dir, destination = self.root / "src", self.root / "dst"
        source_dir.mkdir(); destination.mkdir()
        source = source_dir / "note.txt"
        source.write_text("new", encoding="utf-8")
        outside = self.root / "outside.txt"
        target = destination / source.name
        self.link(outside, target)
        self.assertNotEqual(fileops.unique_target(target), target)
        outcome = fileops.copy_items([source], destination)
        self.assertFalse(outcome.failures)
        self.assertFalse(outside.exists())
        self.assertFalse(target.is_symlink())
        self.assertEqual(target.read_text(encoding="utf-8"), "new")

    def test_shell_and_clipboard_preserve_selected_symlink(self):
        target = self.root / "real.txt"
        target.write_text("real", encoding="utf-8")
        link = self.root / "link.txt"
        self.link(target, link)
        self.assertEqual(shellmenu.context_menu_paths([link]), [link])
        target.unlink()
        self.assertEqual(shellmenu.context_menu_paths([link]), [link])
        if os.name != "nt":
            clipboard.set_file_clipboard([link], cut=True)
            self.addCleanup(clipboard.clear_file_clipboard)
            self.assertEqual(clipboard.get_file_clipboard(), ([link], True))

    def test_windows_recycle_keeps_lexical_selected_path(self):
        target = self.root / "real.txt"
        target.write_bytes(b"real")
        link = self.root / "link.txt"
        # A lexical '..' spelling also detects unwanted resolve without needing
        # Windows symlink creation privileges in the mock API fixture.
        selected = self.root / "sub" / ".." / "real.txt"
        (self.root / "sub").mkdir()
        submitted = []
        def shell_operation(pointer):
            info = ctypes.cast(pointer, ctypes.POINTER(fileops._SHFILEOPSTRUCTW)).contents
            submitted.append(info.pFrom)
            return 0
        windll = SimpleNamespace(kernel32=SimpleNamespace(GetDriveTypeW=lambda _: 3),
                                 shell32=SimpleNamespace(SHFileOperationW=shell_operation))
        with patch.object(fileops.ctypes, "windll", windll, create=True), patch.object(fileops.os, "name", "nt"):
            result = fileops.recycle_items([selected])
        self.assertFalse(result.failures)
        self.assertEqual(submitted, [os.path.abspath(selected)])
        # Test the actual link spelling as well when the OS permits it.
        self.link(target, link)
        with patch.object(fileops.ctypes, "windll", windll, create=True), patch.object(fileops.os, "name", "nt"):
            fileops.recycle_items([link])
        self.assertEqual(submitted[-1], str(link))
        self.assertEqual(target.read_bytes(), b"real")

    def attachments(self, descriptors, writer=None, provider_error=False):
        medium = clipboard._STGMEDIUM()
        with patch.object(clipboard, "_virtual_descriptors_from_object", return_value=descriptors), \
                patch.object(clipboard, "_register_clipboard_format", return_value=99), \
                patch.object(clipboard, "_get_medium", side_effect=OSError("provider failed") if provider_error else None,
                             return_value=medium), \
                patch.object(clipboard, "_release_medium"), \
                patch.object(clipboard, "_write_virtual_medium", side_effect=writer or
                             (lambda _medium, path, _size: path.write_bytes(b"new"))):
            return clipboard.extract_virtual_files_from_data_object(123, self.root)

    def test_attachment_failure_never_removes_existing_collision(self):
        for name in ("a.txt", "a (2).txt"):
            (self.root / name).write_bytes(b"existing")
        files, failures = self.attachments([clipboard.VirtualFileDescriptor("a.txt", 3)], provider_error=True)
        self.assertFalse(files)
        self.assertEqual(len(failures), 1)
        self.assertEqual((self.root / "a (2).txt").read_bytes(), b"existing")
        self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_duplicate_attachments_choose_unique_names(self):
        (self.root / "a.txt").write_bytes(b"existing")
        (self.root / "a (2).txt").write_bytes(b"existing")
        files, failures = self.attachments([clipboard.VirtualFileDescriptor("a.txt", 3)] * 2)
        self.assertFalse(failures)
        self.assertEqual([path.name for path in files], ["a (3).txt", "a (4).txt"])
        self.assertEqual((self.root / "a (2).txt").read_bytes(), b"existing")

    def test_attachment_partial_and_wrong_size_are_not_published(self):
        def broken(_medium, path, _size):
            path.write_bytes(b"partial")
            raise OSError("interrupted")
        for writer, size in ((broken, 7), (None, 100)):
            with self.subTest(size=size):
                files, failures = self.attachments([clipboard.VirtualFileDescriptor("a.txt", size)], writer)
                self.assertFalse(files)
                self.assertTrue(failures)
                self.assertFalse(list(self.root.iterdir()))

    def test_virtual_names_reject_ads_devices_and_controls(self):
        for name in ("report.txt:stream", "NUL.txt", "COM¹", "bad\x01.txt", "bad?.txt"):
            with self.subTest(name=name), self.assertRaises(OSError):
                clipboard._safe_virtual_name(name)

    def test_zip_output_cannot_destroy_input_or_include_itself(self):
        path = self.archive()
        original = path.read_bytes()
        with self.assertRaises(OSError):
            archivefs.create_zip_archive([path], path)
        self.assertEqual(path.read_bytes(), original)
        folder = self.root / "folder"
        folder.mkdir()
        (folder / "input.txt").write_text("safe", encoding="utf-8")
        with self.assertRaises(OSError):
            archivefs.create_zip_archive([folder], folder / "output.zip")
        self.assertFalse((folder / "output.zip").exists())

    def test_zip_write_failure_preserves_previous_output(self):
        target = self.archive()
        before = target.read_bytes()
        source = self.root / "source.txt"
        source.write_text("safe", encoding="utf-8")
        with patch.object(zipfile.ZipFile, "write", side_effect=OSError("write interrupted")):
            with self.assertRaises(OSError):
                archivefs.create_zip_archive([source], target)
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse(list(self.root.glob(".pfc-zip-*")))

    def test_zip_roundtrip_flushes_a_writable_staging_handle(self):
        source = self.root / "source.txt"
        source.write_bytes(b"roundtrip")
        target = self.root / "output.zip"
        modes = {}
        original_open, original_sync = Path.open, os.fsync
        def tracked_open(path, mode="r", *args, **kwargs):
            stream = original_open(path, mode, *args, **kwargs)
            modes[stream.fileno()] = mode
            return stream
        def writable_sync(fd):
            self.assertTrue(any(c in modes[fd] for c in "wa+"), "Windows flushing needs write access")
            original_sync(fd)
        with patch.object(Path, "open", tracked_open), patch.object(os, "fsync", writable_sync):
            archivefs.create_zip_archive([source], target)
        archivefs.extract_archive_to(target, self.root / "out")
        self.assertEqual((self.root / "out" / source.name).read_bytes(), b"roundtrip")
        self.assertFalse(list(self.root.glob(".pfc-zip-*")))

    def test_zip_duplicate_input_basenames_are_rejected_before_overwrite(self):
        inputs = []
        for name in ("one", "two"):
            folder = self.root / name
            folder.mkdir()
            item = folder / "same.txt"
            item.write_bytes(b"input")
            inputs.append(item)
        target = self.archive()
        before = target.read_bytes()
        with self.assertRaises(OSError):
            archivefs.create_zip_archive(inputs, target)
        self.assertEqual(target.read_bytes(), before)

    def test_archive_draft_links_are_not_followed_when_committing(self):
        path = self.archive()
        before = path.read_bytes()
        session = archivefs.ArchiveSession(path)
        self.addCleanup(session.close)
        external = self.root / "external.txt"
        external.write_bytes(b"outside")
        self.link(external, session.root / "link.txt")
        with self.assertRaises(OSError):
            session.commit()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(external.read_bytes(), b"outside")

    def test_zip_external_destination_creation_is_not_overwritten(self):
        target = self.root / "output.zip"
        source = self.root / "source.txt"
        source.write_text("input", encoding="utf-8")
        def external_writer(*_):
            target.write_bytes(b"external")
        with self.assertRaises(OSError):
            archivefs.create_zip_archive([source], target, progress=external_writer)
        self.assertEqual(target.read_bytes(), b"external")

    def test_archive_two_sessions_refuse_stale_commit(self):
        path = self.archive()
        first, second = archivefs.ArchiveSession(path), archivefs.ArchiveSession(path)
        self.addCleanup(first.close); self.addCleanup(second.close)
        (first.root / "note.txt").write_bytes(b"first")
        first.commit()
        before = path.read_bytes()
        (second.root / "note.txt").write_bytes(b"second")
        with self.assertRaises(OSError):
            second.commit()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual((second.root / "note.txt").read_bytes(), b"second")
        (first.root / "note.txt").write_bytes(b"first again")
        first.commit()
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(archive.read("note.txt"), b"first again")

    def test_zip_read_failure_preserves_existing_extraction_target(self):
        path = self.archive()
        destination = self.root / "out"
        destination.mkdir()
        target = destination / "note.txt"
        target.write_bytes(b"existing")
        with patch.object(zipfile.ZipExtFile, "read", side_effect=[b"partial", zipfile.BadZipFile("CRC failed")]):
            with self.assertRaises(zipfile.BadZipFile):
                archivefs.extract_archive_to(path, destination)
        self.assertEqual(target.read_bytes(), b"existing")
        self.assertFalse(list(destination.glob(".pfc-extract-*")))

    def test_archive_all_members_validated_before_writing(self):
        for bad in ("../escape.txt", "NUL.txt", "safe.txt:stream", "bad?.txt"):
            with self.subTest(bad=bad):
                path = self.archive(entries={"note.txt": b"changed", bad: b"bad"})
                destination = self.root / "out"
                destination.mkdir(exist_ok=True)
                existing = destination / "note.txt"
                existing.write_bytes(b"existing")
                with self.assertRaises(OSError):
                    archivefs.extract_archive_to(path, destination)
                self.assertEqual(existing.read_bytes(), b"existing")

    def test_archive_duplicate_and_link_members_rejected(self):
        for entries in ({"a.txt": b"a", "A.TXT": b"b"}, {"folder": b"a", "folder/file": b"b"}):
            path = self.archive(entries=entries)
            with self.assertRaises(OSError):
                archivefs.ArchiveSession(path)
        path = self.root / "link.zip"
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            archive.writestr(info, "../outside")
        with self.assertRaises(OSError):
            archivefs.extract_archive_to(path, self.root / "out")

    def test_seven_zip_listing_rejects_link_and_unsafe_name_before_launch(self):
        for fields in ("Path = folder/link\nSymbolic Link = ../outside\nSize = 1", "Path = ../outside\nSize = 1"):
            listing = SimpleNamespace(returncode=0, stdout="header\n----------\n" + fields)
            with patch.object(archivefs.subprocess, "run", return_value=listing) as run:
                with self.assertRaises(OSError):
                    archivefs._validated_seven_zip_members(self.root / "test.7z", "7z")
                self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
                self.assertEqual(run.call_args.kwargs["timeout"], 30)

    def test_seven_zip_progress_callback_failure_stops_owned_process(self):
        path = self.root / "sample.7z"
        path.write_bytes(b"fixture")
        process = SimpleNamespace(returncode=None, poll=lambda: None,
                                  communicate=lambda **_: ("", ""))
        stopped = []
        process.terminate = lambda: stopped.append(True)
        with patch.object(archivefs, "_seven_zip_executable", return_value="7z"), \
                patch.object(archivefs, "_validated_seven_zip_members"), \
                patch.object(archivefs.subprocess, "Popen", return_value=process):
            def fail(*_): raise OSError("progress callback failed")
            with self.assertRaises(OSError):
                archivefs.ArchiveSession(path, progress=fail)
        self.assertEqual(stopped, [True])

    def test_archive_extraction_cannot_overwrite_its_own_input(self):
        path = self.archive(entries={"sample.zip": b"replaces input"})
        before = path.read_bytes()
        with self.assertRaises(OSError):
            archivefs.extract_archive_to(path, self.root)
        self.assertEqual(path.read_bytes(), before)

    def test_archive_changed_during_commit_is_preserved(self):
        path = self.archive()
        session = archivefs.ArchiveSession(path)
        self.addCleanup(session.close)
        original_write = zipfile.ZipFile.write
        def external_writer(archive, *args, **kwargs):
            result = original_write(archive, *args, **kwargs)
            path.write_bytes(b"external replacement")
            return result
        with patch.object(zipfile.ZipFile, "write", external_writer):
            with self.assertRaises(OSError):
                session.commit()
        self.assertEqual(path.read_bytes(), b"external replacement")
        self.assertEqual((session.root / "note.txt").read_bytes(), b"original")

    def test_child_repositories_scanned_once_and_svn_failure_is_unknown(self):
        vcs.invalidate_vcs_cache()
        with patch.object(vcs, "_git_status", return_value=None), \
                patch.object(vcs, "_svn_status", return_value=None), \
                patch.object(vcs, "_child_repository_statuses", return_value={}) as children:
            vcs.folder_statuses(self.root)
            children.assert_called_once_with(self.root)
        child = self.root / "svn"
        (child / ".svn").mkdir(parents=True)
        with patch.object(vcs, "_svn_status", return_value={}):
            self.assertEqual(vcs._child_repository_statuses(self.root), {})

    def test_vcs_invalidated_worker_cannot_repopulate_cache(self):
        vcs.invalidate_vcs_cache()
        def invalidate(_folder):
            vcs.invalidate_vcs_cache()
            return {"old": "modified"}
        with patch.object(vcs, "_git_status", side_effect=invalidate), \
                patch.object(vcs, "_child_repository_statuses", return_value={}):
            self.assertEqual(vcs.folder_statuses(self.root), {"old": "modified"})
        self.assertNotIn(os.path.normcase(str(self.root)), vcs._CACHE)

    def test_vcs_cache_is_capacity_bounded_and_expires_old_entries(self):
        vcs.invalidate_vcs_cache()
        clock = 10.0
        with patch.object(vcs.time, "monotonic", side_effect=lambda: clock), \
                patch.object(vcs, "_git_status", return_value={}), \
                patch.object(vcs, "_child_repository_statuses", return_value={}):
            for index in range(vcs._VCS_CACHE_LIMIT + 5):
                vcs.folder_statuses(self.root / str(index))
            self.assertEqual(len(vcs._CACHE), vcs._VCS_CACHE_LIMIT)
            clock += vcs._DISPLAY_CACHE_SECONDS + 1
            vcs.folder_statuses(self.root / "fresh")
            self.assertEqual(list(vcs._CACHE), [os.path.normcase(str(self.root / "fresh"))])

    def test_vcs_overlay_uses_configured_executable_and_readonly_environment(self):
        (self.root / ".git").mkdir()
        completed = subprocess.CompletedProcess([], 0, stdout=b"", stderr=b"")
        with patch.object(vcs, "vcs_cli", return_value="/trusted/git"), \
                patch.object(vcs.subprocess, "run", return_value=completed) as run:
            vcs._git_status(self.root)
            self.assertEqual(run.call_count, 2)
            for call in run.call_args_list:
                self.assertEqual(call.args[0][0], "/trusted/git")
                self.assertEqual(call.kwargs["env"]["GIT_OPTIONAL_LOCKS"], "0")

    def test_rename_invalid_names_do_not_throw_path_errors(self):
        source = self.root / "a.txt"
        source.write_text("a", encoding="utf-8")
        for name in ("", ".", "..", "dir/file", "dir\\file", "NUL.txt", "bad\x01.txt"):
            with self.subTest(name=name):
                plan = rename.validate_rename_plan([source], [name])
                self.assertTrue(plan[0][2])
                self.assertTrue(source.exists())

    def test_batch_rename_refuses_existing_unselected_target(self):
        source, target = self.root / "a.txt", self.root / "b.txt"
        source.write_bytes(b"source"); target.write_bytes(b"existing")
        with self.assertRaises(OSError):
            rename.execute_rename_pairs([(source, target)])
        self.assertEqual(source.read_bytes(), b"source")
        self.assertEqual(target.read_bytes(), b"existing")

    def test_concurrent_config_writes_use_owned_temporary_files(self):
        target = self.root / "pfc.ini"
        barrier = threading.Barrier(2)
        errors = []
        class InterleavedConfig(configparser.ConfigParser):
            def write(self, stream, *args, **kwargs):
                super().write(stream, *args, **kwargs)
                barrier.wait(timeout=5)
        def save(value):
            config = InterleavedConfig()
            config.read_dict({"state": {"value": value}})
            try:
                app.write_config_atomic(config, target)
            except Exception as exc:
                errors.append(exc)
        for iteration in range(50):
            with self.subTest(iteration=iteration):
                threads = [threading.Thread(target=save, args=(value,)) for value in ("one", "two")]
                for thread in threads: thread.start()
                for thread in threads: thread.join(timeout=10)
                self.assertFalse(any(thread.is_alive() for thread in threads))
                self.assertFalse(errors)
                restored = configparser.ConfigParser()
                restored.read(target, encoding="utf-8")
                self.assertIn(restored.get("state", "value"), {"one", "two"})
                self.assertFalse(list(self.root.glob(".pfc-config-*")))

    def test_config_replace_retries_only_transient_windows_errors(self):
        config = configparser.ConfigParser()
        config.read_dict({"state": {"value": "new"}})
        target = self.root / "pfc.ini"
        original_replace = Path.replace
        for code in (5, 32, 33):
            with self.subTest(winerror=code):
                error = PermissionError("temporary sharing conflict")
                error.winerror = code
                attempts = []
                def replace(temporary, destination):
                    attempts.append(temporary)
                    if len(attempts) < 3:
                        raise error
                    return original_replace(temporary, destination)
                with patch.object(Path, "replace", autospec=True, side_effect=replace), \
                        patch.object(app.time, "sleep") as sleep:
                    app.write_config_atomic(config, target)
                self.assertEqual(len(attempts), 3)
                self.assertEqual([call.args[0] for call in sleep.call_args_list], [.01, .02])
                self.assertIn("value = new", target.read_text(encoding="utf-8"))
                self.assertFalse(list(self.root.glob(".pfc-config-*")))

    def test_config_replace_retry_exhaustion_preserves_previous_file(self):
        target = self.root / "pfc.ini"
        previous = b"[state]\nvalue = existing\n"
        config = configparser.ConfigParser()
        config.read_dict({"state": {"value": "new"}})
        for code, count in ((32, 5), (87, 1), (None, 1)):
            with self.subTest(winerror=code):
                target.write_bytes(previous)
                error = PermissionError("persistent failure")
                if code is not None:
                    error.winerror = code
                with patch.object(Path, "replace", side_effect=error) as replace, \
                        patch.object(app.time, "sleep") as sleep:
                    with self.assertRaises(PermissionError):
                        app.write_config_atomic(config, target)
                self.assertEqual(replace.call_count, count)
                self.assertEqual(sleep.call_count, count - 1)
                self.assertLessEqual(sum(call.args[0] for call in sleep.call_args_list), .15 + 1e-9)
                self.assertEqual(target.read_bytes(), previous)
                self.assertFalse(list(self.root.glob(".pfc-config-*")))

    def test_config_serialization_failure_cleans_only_owned_temp(self):
        target = self.root / "pfc.ini"
        target.write_text("[state]\nvalue = existing\n", encoding="utf-8")
        previous_temp = self.root / "pfc.ini.tmp"
        previous_temp.write_bytes(b"not ours")
        config = configparser.ConfigParser()
        with patch.object(config, "write", side_effect=ValueError("serialization failed")):
            with self.assertRaises(ValueError):
                app.write_config_atomic(config, target)
        self.assertIn("existing", target.read_text(encoding="utf-8"))
        self.assertEqual(previous_temp.read_bytes(), b"not ours")
        self.assertFalse(list(self.root.glob(".pfc-config-*")))

    def test_office_search_bounds_xml_read_and_survives_encrypted_content(self):
        path = self.archive(self.root / "sample.docx", {"one.xml": b"a" * 100 + b"needle"})
        original = zipfile.ZipExtFile.read
        requests = []
        def read(stream, size=-1):
            requests.append(size)
            return original(stream, size)
        with patch.object(search, "CONTENT_LIMIT", 16), patch.object(zipfile.ZipExtFile, "read", read):
            self.assertFalse(search.content_matches(path, "needle", False))
        self.assertEqual(requests, [16])
        with patch.object(zipfile.ZipFile, "open", side_effect=RuntimeError("password required")):
            self.assertFalse(search.content_matches(path, "needle", False))

    def test_search_result_limit_stops_outer_traversal(self):
        item = self.root / "a.txt"
        item.write_bytes(b"a")
        visited = []
        def walk(_root):
            visited.append("first")
            yield str(self.root), [], [item.name]
            visited.append("second")
            yield str(self.root), [], [item.name]
            visited.append("third")
            raise AssertionError("Continued walking after result limit")
        window = SimpleNamespace(cancel_event=threading.Event(), messages=queue.Queue())
        criteria = dict(root=self.root, max_depth=None, folders=False, files=True, masks="*", case=False,
                        min_size=None, max_size=None, since=None, content="")
        with patch.object(search, "RESULT_LIMIT", 1), patch.object(search.os, "walk", walk):
            search.SearchWindow._search(window, criteria)
        messages = list(window.messages.queue)
        self.assertFalse(any(message[0] == "error" for message in messages))
        self.assertNotIn("third", visited)
        self.assertEqual(messages[-1], ("done", 1, False, True))

    def test_search_invalid_numeric_criteria_are_rejected(self):
        def var(value): return SimpleNamespace(get=lambda: value)
        window = SimpleNamespace(depth_values={}, depth_var=var("All"), path_var=var(str(self.root)),
            mask_var=var(""), content_var=var(""), case_var=var(False), files_var=var(True), folders_var=var(True),
            min_size_var=var(""), max_size_var=var(""), days_var=var(""))
        for value in ("NaN", "inf", "-1", "bad", "1e100"):
            window.days_var = var(value)
            with self.subTest(value=value), self.assertRaises((ValueError, OverflowError)):
                search.SearchWindow.criteria(window)

    def test_search_reads_bom_marked_utf32_in_both_byte_orders(self):
        for encoding, bom in (("utf-32-le", b"\xff\xfe\x00\x00"), ("utf-32-be", b"\x00\x00\xfe\xff")):
            path = self.root / (encoding + ".txt")
            path.write_bytes(bom + "Find 中文 needle".encode(encoding))
            self.assertTrue(search.content_matches(path, "中文 needle", False))

    def test_vcs_failed_thread_start_does_not_wedge_future_queries(self):
        pane = SimpleNamespace(path=self.root, archive_session=None, _vcs_inflight=None,
            _vcs_path=None, _vcs_statuses={}, _vcs_requested_at=0, _vcs_generation=0,
            _vcs_loading=False, _vcs_results=queue.Queue(), winfo_toplevel=lambda:
            SimpleNamespace(vcs_overlay_var=SimpleNamespace(get=lambda: True)))
        with patch.object(app.threading.Thread, "start", side_effect=RuntimeError("thread capacity")):
            app.FilePane._request_vcs_statuses(pane)
        self.assertIsNone(pane._vcs_inflight)
        self.assertIsNone(pane._vcs_path)
        self.assertFalse(pane._vcs_loading)

    def test_vcs_navigation_coalesces_workers_and_discards_stale_results(self):
        enabled = True
        overlay = SimpleNamespace(get=lambda: enabled)
        calls, workers, applied = [], [], []
        pane = SimpleNamespace(path=self.root, archive_session=None, _vcs_inflight=None,
            _vcs_path=None, _vcs_statuses={}, _vcs_requested_at=0, _vcs_generation=0,
            _vcs_loading=False, _vcs_results=queue.Queue(), winfo_toplevel=lambda: SimpleNamespace(vcs_overlay_var=overlay),
            after=lambda *_: None, _apply_vcs_icons=lambda old: applied.append(old))
        pane._request_vcs_statuses = lambda: app.FilePane._request_vcs_statuses(pane)
        pane._poll_vcs_results = lambda: app.FilePane._poll_vcs_results(pane)
        def thread(*, target, **_):
            workers.append(target)
            return SimpleNamespace(start=lambda: None)
        def statuses(path):
            calls.append(path)
            return {"a.txt": "modified"}
        with patch.object(app.threading, "Thread", thread), patch.object(app, "folder_statuses", statuses):
            pane._request_vcs_statuses()
            for number in range(100):
                pane.path = self.root / str(number)
                pane._request_vcs_statuses()
            self.assertEqual(len(workers), 1)
            workers[0]()
            app.FilePane._poll_vcs_results(pane)
            self.assertEqual(len(workers), 2)
            self.assertFalse(applied)
            workers[1]()
            app.FilePane._poll_vcs_results(pane)
            self.assertEqual(calls, [self.root, self.root / "99"])
            self.assertEqual(len(applied), 1)
            pane._vcs_generation += 1
            pane._vcs_requested_at = 0
            pane._request_vcs_statuses()
            enabled = False
            workers[2]()
            app.FilePane._poll_vcs_results(pane)
            self.assertEqual(len(applied), 1)
            self.assertIsNone(pane._vcs_inflight)


if __name__ == "__main__":
    unittest.main(verbosity=2)
