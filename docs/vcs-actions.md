# F8 · Git / SVN

The bottom action bar uses measured widths, compact labels and, on narrow windows,
key-only labels where necessary. Text keeps the user's font scale. Hover shows
the full action; Copy/Move retain their destination panel and zoom stays separate.

Select a file/folder (or a row in the single-panel folder tree), then press F8.
With no selection the current directory is used. F8 identifies Git/SVN independent
of the overlay visibility switch; metadata directories and archive previews are
not working copies. The same menu is in PFC's file/folder right-click menu.
Windows Explorer's native context menu is not modified.

## Scope and meaning

- **Commit selected…** passes the selected paths to Tortoise's commit dialog.
  Folder selection includes changes below that folder. Review the client's file
  checklist before confirming. PFC never stages or commits files itself.
- **Commit entire working copy…** explicitly widens scope. Mixed working-copy
  selections disable both Commit choices and Push; select one working copy first.
- **Push current branch…** (Git only) opens the client's push dialog. Push acts on
  commits/branches, not individual selected files. Remote/branch/options remain
  visible in the client and require user confirmation.
- **Show History** targets the focused selected path, even in a multi-selection.
  These are commit records, not a complete audit log of server push events.
- **Show Graph** opens Git's repository revision graph, or SVN's selected-path
  graph. Git's current branch/detached HEAD and SVN's relative repository URL are
  shown in the summary; PFC does not infer a file's original branch of creation.
- SVN Commit submits to the server directly, so there is no separate Push.
  SVN History/Graph entries warn that they may use the network.

## Dependencies, performance and safety

Windows requires installed TortoiseGit/TortoiseSVN for GUI actions. Known install
locations and the user's explicit choice are checked. **Choose Tortoise client…**
saves `[vcs] git_client` / `svn_client` in the existing INI. Nothing is downloaded
or installed. Git/SVN command-line clients supply status summaries; without them,
the menu explains that status is unavailable while GUI actions remain accessible.

Selection discovery is debounced and performed by one background worker with one
pending latest request. It searches ancestors only, respecting nearer nested
repositories and `.git` worktree/submodule files. Detailed status is requested on
menu opening, with a short bounded cache, command timeouts and stale-result checks.
No UI-thread command, whole-drive index, Fetch, credential prompt or periodic
network scan is introduced. Git status suppresses optional index writes and
fsmonitor hooks. Native clients receive argument arrays, not shell command strings.

Git ahead/behind is relative to the configured upstream **as last known locally**,
not proof of the server's current state or a different push destination. Missing
upstream, unavailable commands and timeouts remain unknown, never “synchronized”.
Untracked counts can include grouped directories. Refresh status requests fresh
local data; after a launched client exits, caches and existing overlays refresh
without rebuilding rows or changing selection.

Official dialog interfaces:
[TortoiseGit](https://tortoisegit.org/docs/tortoisegit/tgit-automation.html),
[TortoiseSVN](https://tortoisesvn.net/docs/release/TortoiseSVN_en/tsvn-automation.html).

## Checks

`tests/test_vcs_actions.py` covers real local Git repositories, selected-only
changes, cached upstream divergence, worktrees, nested repositories, detached
HEAD, literal paths, conflict/rename parsing, SVN XML including property/tree
conflicts, missing CLI, timeouts and non-mutating dialog argument construction.

`tools/vcs_actions_check.py [pfc]` exercises package/portable GUI routing, mixed
scope blocking, background result updates, tree vs file focus, external-window
hotkey guards, and 1–4 panels at 100/150/175/200% in English and both Chinese UIs.
Client launches are intercepted: this test never commits or pushes. Actual
Tortoise windows require a Windows machine with the corresponding client installed.
