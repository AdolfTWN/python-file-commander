"""Non-destructive regression check for Git overlay refresh behavior."""

import tempfile
import time
from pathlib import Path
import sys
import importlib
import subprocess
import os
from contextlib import ExitStack
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
portable = len(sys.argv) > 1 and sys.argv[1] == 'pfc'
module = importlib.import_module('pfc' if portable else 'pycommander.app')
vcs = module if portable else importlib.import_module('pycommander.vcs')
Commander = module.Commander
_git_root_summary, status_for = vcs._git_root_summary, vcs.status_for


def wait_for_vcs(app, pane, timeout=10.0):
    deadline = time.monotonic() + timeout
    while pane._vcs_loading and time.monotonic() < deadline:
        app.update(); time.sleep(.03)
    app.update()
    assert not pane._vcs_loading, "VCS scan did not complete"


def main():
    original_ini = Commander._find_ini_path
    with tempfile.TemporaryDirectory() as raw, ExitStack() as patches:
        repository = (Path(raw) / 'repository').resolve()
        repository.mkdir()
        git = vcs.vcs_cli('git')
        def command(*args):
            subprocess.run([git, '-C', str(repository), *args], check=True,
                           capture_output=True, timeout=20, **vcs._run_options())
        if git:
            command('init', '-q')
        else:
            assert os.name == 'nt', 'Git CLI required for host acceptance'
            (repository / '.git').mkdir()
        for number in range(8):
            folder = repository / f'sub-{number}'; folder.mkdir()
            for index in range(100):
                (folder / f'file-{index:03}.txt').write_text('base\n', encoding='utf-8')
        if git:
            command('add', '.')
            command('-c', 'user.name=PFC Test', '-c', 'user.email=pfc@example.invalid',
                    'commit', '-qm', 'fixture')
            print('Backend: real Git CLI', flush=True)
        else:
            # Explicit UI/parser-only acceptance when this VM lacks Git. Do not
            # mistake injected porcelain bytes for native Git performance.
            real_run, real_cli = subprocess.run, vcs._overlay_cli
            tracked = [f'sub-{n}/file-{i:03}.txt' for n in range(8) for i in range(100)]
            def fixture_run(cmd, *args, **kwargs):
                if cmd[0] != 'PFC-fixture-git':
                    return real_run(cmd, *args, **kwargs)
                relative = cmd[-1].replace('\\', '/') if '--' in cmd else '.'
                selected = [p for p in tracked if relative == '.' or p.startswith(relative + '/')]
                if 'ls-files' in cmd:
                    data = ''.join(p + '\0' for p in selected).encode()
                else:
                    data = (b'## main\0' if '--branch' in cmd else b'')
                    if 'sub-0/file-000.txt' in selected:
                        data += b' M sub-0/file-000.txt\0'
                return subprocess.CompletedProcess(cmd, 0, stdout=data, stderr=b'')
            patches.enter_context(patch.object(vcs, '_overlay_cli',
                side_effect=lambda kind: 'PFC-fixture-git' if kind == 'git' else real_cli(kind)))
            patches.enter_context(patch.object(vcs.subprocess, 'run', side_effect=fixture_run))
            print('Backend: injected Git output; native UI/parser only, Git CLI unavailable', flush=True)
        (repository / 'sub-0' / 'file-000.txt').write_text('changed\n', encoding='utf-8')
        vcs.invalidate_vcs_cache()
        Commander._find_ini_path = staticmethod(lambda: Path(raw) / "pfc.ini")
        app = Commander(); app.geometry('1100x720+60+60'); app.update()
        try:
            pane = app.left_tabs.current()
            assert pane.navigate(repository.parent)
            wait_for_vcs(app, pane)
            expected_root_status = _git_root_summary(repository)
            assert expected_root_status is not None
            assert status_for(pane._vcs_statuses, repository) == expected_root_status
            repository_rows = [iid for iid in pane.tree.get_children()
                               if pane.tree.item(iid, "tags") and
                               Path(pane.tree.item(iid, "tags")[0]) == repository]
            assert len(repository_rows) == 1
            assert pane.tree.item(repository_rows[0], "image"), (
                "Repository root shown from its parent has no overlay icon")
            assert pane.navigate(repository)
            wait_for_vcs(app, pane)
            cli_calls = []
            run = vcs.subprocess.run
            def counted(*args, **kwargs):
                cli_calls.append(args[0]); return run(*args, **kwargs)
            vcs.subprocess.run = counted
            try:
                durations = []
                for number in range(8):
                    child = repository / f'sub-{number}'
                    started = time.monotonic()
                    assert pane.navigate(child)
                    # Check before pumping the event loop: the first paint
                    # already uses known Git states, not a delayed worker reply.
                    target = child / 'file-000.txt'
                    expected = 'modified' if number == 0 else 'clean'
                    assert status_for(pane._vcs_statuses, target) == expected, 'warm navigation lost overlays'
                    rows = [i for i in pane.tree.get_children() if
                            Path(pane.tree.item(i, 'tags')[0]) == target]
                    assert len(rows) == 1 and pane.tree.item(rows[0], 'image')
                    durations.append(time.monotonic() - started)
                    wait_for_vcs(app, pane)
                print('Git overlay first-paint navigation seconds:', durations, flush=True)
                print('Git commands during warm navigation:', len(cli_calls), flush=True)
            finally:
                vcs.subprocess.run = run
            assert pane.navigate(repository)
            wait_for_vcs(app, pane)
            original_item = pane.tree.item
            image_updates = []

            def tracked_item(item, *args, **kwargs):
                if "image" in kwargs:
                    image_updates.append(item)
                return original_item(item, *args, **kwargs)

            pane.tree.item = tracked_item
            pane._vcs_requested_at = 0.0
            pane._request_vcs_statuses()
            wait_for_vcs(app, pane)
            assert not image_updates, "Unchanged Git status repainted file-list icons"

            started = time.monotonic()
            assert pane.navigate(repository / ".git")
            app.update()
            assert time.monotonic() - started < 1.0, ".git navigation blocked the UI"
            wait_for_vcs(app, pane)
            assert pane._vcs_statuses == {}, ".git metadata must not be status-scanned"
        finally:
            app.destroy(); Commander._find_ini_path = original_ini


if __name__ == "__main__":
    main()
