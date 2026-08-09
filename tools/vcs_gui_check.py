"""Non-destructive regression check for Git overlay refresh behavior."""

import tempfile
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pycommander.app import Commander
from pycommander.vcs import _git_root_summary, status_for


def wait_for_vcs(app, pane, timeout=10.0):
    deadline = time.monotonic() + timeout
    while pane._vcs_loading and time.monotonic() < deadline:
        app.update(); time.sleep(.03)
    app.update()
    assert not pane._vcs_loading, "VCS scan did not complete"


def main():
    repository = Path(sys.argv[1] if len(sys.argv) > 1 else Path.cwd()).resolve()
    assert (repository / ".git").exists(), repository
    original_ini = Commander._find_ini_path
    with tempfile.TemporaryDirectory() as raw:
        Commander._find_ini_path = staticmethod(lambda: Path(raw) / "pfc.ini")
        app = Commander(); app.withdraw()
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
