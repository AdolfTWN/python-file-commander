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

## Overlay navigation latency — v0.18.24

Git/SVN status snapshots retain a maximum 30-second display lifetime and 128-folder
capacity. Entering a previously scanned folder or covered descendant uses that
snapshot during initial row construction, without waiting for the worker. A
background request still uses the original three-second freshness window. Client
completion invalidates both display and query caches. Unknown files never receive
an invented clean state. Repository summaries viewed from outside a worktree do
not cover its descendants; nested repositories and metadata folders remain separate.

Git aggregation now uses lexical normalized paths rooted at the resolved worktree,
instead of resolving every tracked file again. This also keeps tracked-link state
attached to the link, not its target. Existing generation checks continue to discard
old-folder results, and unchanged overlays do not redraw icons.

Validation on 2026-10-09:

- The complete unit suite and package/portable VCS UI regression pass, including
  real Git status parsing, cache freshness/invalidation, nested marker files,
  bounded expiry/capacity and rapid-navigation worker coalescing.
- `tools/vcs_overlay_benchmark.py --before 1480535d361ae14c058ef0d453c60f3c72054d53`
  compares the previous release on a synthetic 2,000-file/eight-subfolder Git
  worktree. Recent child navigation changes from 16 Git commands to zero; per-file
  aggregation changes from 2,000 physical path resolutions to zero. This is a
  host benchmark, not a claim about every user's disk or cold-start latency.
- The same portable candidate passes overlay navigation and reliability checks
  in both ARM64 and Windows-emulated x64 Python 3.13.15/Tk. Eight warm navigations
  populate status-bearing icons in 16–47 ms (ARM64) and 18–89 ms (x64), measured
  through row construction, before processing the worker reply. These fixtures
  contain 100 visible files per child. The VM has no Git CLI: Windows tests
  explicitly inject deterministic Git output and validate parser/cache/UI behavior,
  not real Windows Git process startup or large-repository status performance.
  Four privilege-dependent symlink reliability cases per runtime are skipped.

First visits without a usable snapshot still require background status discovery.
These ARM Windows checks do not establish native x64 Windows compatibility.
