# One-panel workspace — v0.17.29

Select **View → Panel Counts → 1 Panel**, also available through the background
context menu. This is one navigation workspace, not a second transfer panel.

- One full-width tab strip sits above the whole workspace. It presents the tabs
  from the previously visible 2/3/4 panel groups without copying or reparenting
  FilePanes. Existing paths, selection, ZIP sessions, filters, colors and lock
  modes remain with their original owners.
- The left third is a folder tree rooted at **This PC**, showing drive letters
  on Windows (`/` on Linux). The right two thirds display the active file pane.
  The sash is adjustable; its ratio is saved (15–65% tree width).
- Fine, muted dotted connectors distinguish parents, siblings
  and last-child corners. Visible indentation cells are painted without covering
  native folder names; lines follow scrolling, font zoom and light/dark colors.
  The active folder and its ancestors expand by default. Expanded rows have no
  collapse symbol; double-clicking a folder name, icon or connector area toggles
  expansion. Selection, context menus and native keyboard navigation remain
  available. Closed branches use small outlined plus controls. Antialiased
  folder, drive and computer icons scale with the font and sit directly on the
  branch joints, so child connectors descend from the parent icon. Rendering reads cached
  tree items only, with no filesystem queries.
- Clicking a folder navigates the active tab; tab/path changes synchronize the
  tree. ZIP previews synchronize to their containing persistent folder, never
  exposing an extraction temp path as the logical root.
  Same-path background saves preserve manual collapse, selection and scroll
  position. Manual collapse cancels Expand All; actual navigation to a different
  folder still reveals its ancestors.
- Switching back to 2/3/4 panels restores original group ownership and order.
  Shared-strip reordering is saved separately. New tabs and search-result tabs
  created in one-panel mode belong to P1.
- Tab color/lock/style menus use the same settings as multi-panel mode. Return
  locks also restore when switching to a tab owned by a different panel.
- Ctrl+Tab/Shift+Ctrl+Tab traverse the combined strip. Tab switches focus between
  tree and file list; tree arrow keys retain their native expand/collapse behavior.
  Delete/Shift+Delete and rename/cut/copy shortcuts on the navigation tree must
  not operate on an unrelated selected file in the right pane.
- Each original panel still retains at least one tab, matching the existing
  close-tab rule; this also ensures it can be restored as a usable panel.

## Floating ancestor context

Parents of the first visible tree row are pinned above the scrollable area once
they leave the viewport. The icons and dotted joints use the same indentation
and horizontal scroll offset as the tree; each parent has its own text row.
This follows the viewport rather than the selected folder. Native rows are not
covered, and returning to the top removes the pinned area automatically.

Click a parent to reveal/select it through normal navigation. The mouse wheel
continues scrolling over the floating area, and hovering exposes the full path.
All ancestors are shown directly: no omitted levels or overflow menu. Normal
spacing follows the UI font; unusually deep paths use tighter spacing and, only
when needed, smaller context text/icons to retain two ordinary tree rows below.
Ancestor connectors follow actual sibling relationships, ending when there is
no following sibling. Startup fills the expanded active-path levels using bounded
one-directory background scans; painting only reads cached parent relationships.
Floating connectors use the same topology, with every ancestor still labeled.
If a joint falls outside the horizontal viewport, its floating name/icon stays
at the edge with a direction hint instead of becoming invisible too.

## Operations have explicit targets

In one-panel mode, F5/F6 ask for a destination folder. Cancelling does nothing.
F9 with one file/folder (or no selection, meaning the current folder) asks for a
matching comparison target. Two selected items can be compared directly.
Hidden panels are never used as implicit copy/move/compare destinations.

## Bounded, opt-in expansion

**Expand All** sits beside Folders and defaults off on every launch. It expands
only the current folder's subtree, not every drive under This PC. Unchecking,
changing folders, refreshing or leaving one-panel mode stops further work; already
expanded branches remain open. The option is a session action, not a saved INI
preference. A completed run stays checked until cancelled or navigation changes.

Expansion uses the existing bounded worker pool and at most 24 cached nodes per
UI tick. A run stops after 30 seconds, 500 folders, 32 descendant levels or the 10,000-node
cache cap, showing a limit message rather than claiming complete expansion.
Permission errors, links and Windows reparse/cloud directories are skipped and
reported as incomplete. Even previously cached nodes are checked before automatic
descent. Manual cloud-folder navigation is unchanged. Cancelled and timed-out
results cannot insert stale rows. Python cannot interrupt an OS call already
blocked in a filesystem provider; it does not block the UI or create more workers.

Drive enumeration uses the Windows drive-letter bitmask rather than probing all
drives. Expanding a tree node reads only that directory's immediate entries on
background workers. Selecting a tab inserts its already-known ancestor path
immediately, then queues the active folder and its ancestors' immediate children,
nearest first. Busy workers do not drop queued ancestor levels. Discovered siblings
are merged alphabetically without replacing existing IDs or open/selection states.
The visible selection (or top row when scrolled away) anchors background updates.
Unrelated descendants and other drives are not scanned recursively.

- No recursive walk, full-drive index or file-content read.
- At most two daemon scans in flight; no unbounded worker/task queue.
- Stop after 2,000 examined entries or a 3-second cooperative budget; ignore a
  result after 5 seconds. A blocked OS call cannot be killed by Python, but it
  does not block the GUI scan dispatcher or spawn additional workers.
- Tree cache is capped at 10,000 scanned nodes. Show partial/error/timeout status
  rather than silently claiming a complete listing. Refresh resets the cache.
- Do not follow symlink directory cycles. Normal folder navigation/file-list
  loading continues to use the existing FilePane implementation.

Tests: `tests/test_singlepanel.py` and `tools/single_panel_check.py` (source and
portable), alongside existing context-menu, tab-lock, drag and archive tests.
Full `tools/run_headless_checks.sh` passed: 186 unit tests (8 platform skips)
and the source/portable GUI regression checks. Additional focused checks cover
closing a shared-strip tab and cycling the combined strip with Ctrl+Tab.

Offline Windows 11 portable validation passed on 2026-09-20: shared tabs and
layout, bounded lazy tree, reset-lock navigation, group restoration and restart,
explicit/cancelled transfer and comparison targets, and saved divider/metadata.
The 150% visual check confirmed the full-width strip and 1/3–2/3 workspace.
Artifact SHA-256: `35f31a50d7ba8e5de65f3f56fdc2d7dceabfaec97d91c4e35596cf2642c4642f`.
The initial checks above preceded the v0.17.21 release preparation. Connector
regression is in `tools/folder_lines_check.py`, covering 100/150/300%, all three
themes, solid geometry, text clearance, scrolling and pointer hit testing.

Final v0.17.21 Windows portable checks passed on 2026-09-21: solid connectors
(including real scrolling at 100%), shared-panel operations/restart, and tab-lock
visuals/behavior. The 150% native screenshot was also inspected. Matched portable
SHA-256: `1d157c8e3a95097755453f20d9fda3f13ffa63adfed8a548f32f8edbc0a5e6d8`.
Final full headless suite passed with 187 unit tests (8 platform skips) and all
source/portable GUI regressions. The expanded scrolling fixture also passed
separate source, portable and native Windows runs.

v0.17.23 focused validation passed for source and portable: dotted one-pixel
connectors, icon/text clearance, scrolling, all themes at 100/150/300%, default-off
expansion, current-folder boundaries (including native tree selection), cancellation,
stale-result rejection, folder/depth/time budgets, and navigation/unmap/refresh stop.
Linux checks exercise real symlinks; Windows checks inject reparse attributes on
an already cached node to ensure caching cannot bypass the automatic traversal
guard. Windows native visuals were inspected at 150%. Matched portable SHA-256:
`6de6e94e5215fe95e1c4491ad59cc511933d9c9c874052bc657d42110f31402b`.

v0.17.24 validation: 199 unit tests passed (8 platform skips); source and portable
checks passed for real double-click pairs, dotted joint/icon geometry at
100/150/300% in three themes, bounded expansion, shared-panel behavior, path
navigation and ZIP exit. The previous sync implementation reproduced the
autosave-reopens-collapse failure in the new double-click regression. Offline
Windows portable checks passed for double-clicks, connector geometry, expansion
and shared panels; the 150% native tree was visually inspected. Matched portable
SHA-256: `f780b55be42249a1756f90b6f6c7bda085facc2b4aeb31f98e303a1a675f7db8`.

v0.17.25 validation: 199 unit tests passed (8 platform skips). Source and portable
GUI checks covered viewport-following ancestors, aligned joints, top restoration,
branch changes, three themes at 100/150/300%, horizontal clipping, deep-path
overflow, wheel/click behavior, refresh and stable bottom scrolling. Related
double-click, connector, bounded expansion, shared-panel, path and ZIP-exit
checks passed. Final offline Windows portable checks passed for sticky ancestors,
double-clicks, connectors, expansion and shared panels; the 150% floating tree
was visually inspected. Native overflow-menu posting/dismissal was also checked;
the automated menu-content test bypasses Windows' blocking popup loop.
Matched portable SHA-256:
`a3bb6bc4fcdf66073c59128e53e2121b59c235ac18036505a74e4cbfc2ed426d`.

v0.17.26 validation: 201 unit tests passed (8 platform skips); an unrelated
Markdown worker shutdown exception observed in the test output is recorded in
[TODO](TODO.md), not claimed fixed by this release. The previous
connector function omitted all five ancestor guides in a sibling-free startup
fixture; the new function preserves them. The saved-path restart GUI test checks
all guides before any folder click, while ancestors remain unscanned. Source and
portable checks passed for startup, all ancestor labels/icons (including 20+
levels), themes/zoom, scrolling, double-clicks, connectors and bounded expansion.
Shared-panel checks passed three consecutive runs after fixing a geometry race:
notebook layout must settle before setting the tree divider, otherwise a late
size request can collapse the left pane and prevent keyboard focus.
The tree's requested size is isolated from its floating content so a deep
ancestor chain cannot push the bottom action bar out of view; the horizontal
scrollbar is reserved before allocating the tree's remaining height.
Final offline Windows checks passed for startup, all ancestors, double-clicks,
connectors, expansion and shared panels; the no-click 150% startup was inspected.
Matched portable SHA-256:
`d0ab926339f3cf5d70763594c920318367c457fd5f4a683cde6c4ba36cdde14a`.

## v0.17.29 hierarchy correction

The v0.17.26 startup workaround drew every ancestor continuation whether or not
a later sibling existed. At the same time, startup seeded only the saved path and
left its ancestor listings empty. Clicking an ancestor then appended its missing
siblings after the seeded child, changing the apparent topology and sort order.

Startup now queues one-level scans along the active path, using the same two-worker
pool, timeout, entry and cache limits. Rows retain IDs and open states while sibling
lists are merged in alphabetical order. Normal and pinned connectors share one
geometry function: only real following siblings get a continuing parent line,
including the expanded-last-child case. No recursive sibling/drive scan is added.

Background merges anchor the existing selection or viewport row. A bounded idle
layout check keeps a previously visible selection whole after pinned ancestors
resize the viewport; pointer, wheel, scrollbar or keyboard intent cancels it.

Validation: the old connector reproduced four phantom ancestor continuations in
the new last-child fixture, versus zero after the fix. The full headless suite
passed, followed by 222 unit tests (8 platform skips) and focused source/portable
regressions for final viewport handling. `folder_hierarchy_check.py` covers
startup without clicking, saturated worker queuing, sorted merges, real branch
topology, no recursion into siblings, unchanged selection, collapse and refresh.
The saved-INI startup test requires populated ancestors and a fully visible row.
Windows 11 offline portable checks passed for hierarchy, saved startup, real
double-clicks, floating ancestors, connectors at 100/150/300%, bounded Expand All
and shared-panel behavior. Tested portable SHA-256:
`2316d85df27e1e09a9faff9f9b3991728ad58e8eaec3c6b709e624ec2b695cdc`.
