# One-panel workspace — v0.17.25

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
Only the nearest ancestors fit in roughly one third of the available tree area
(2–6 rows depending on font/window size); an earlier-ancestors menu keeps the
remaining chain accessible for unusually deep paths. No filesystem scan, index
or recursive expansion is introduced: this reads cached parent relationships.
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
without scanning the ancestors. The active folder's immediate children load
automatically; unrelated descendants are not scanned recursively.

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
