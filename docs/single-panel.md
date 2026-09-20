# One-panel workspace — v0.17.21

Select **View → Panel Counts → 1 Panel**, also available through the background
context menu. This is one navigation workspace, not a second transfer panel.

- One full-width tab strip sits above the whole workspace. It presents the tabs
  from the previously visible 2/3/4 panel groups without copying or reparenting
  FilePanes. Existing paths, selection, ZIP sessions, filters, colors and lock
  modes remain with their original owners.
- The left third is a folder tree rooted at **This PC**, showing drive letters
  on Windows (`/` on Linux). The right two thirds display the active file pane.
  The sash is adjustable; its ratio is saved (15–65% tree width).
- Solid vertical and horizontal connector strokes distinguish parents, siblings
  and last-child corners. Visible indentation cells are painted without covering
  native folder names; lines follow scrolling, font zoom and light/dark colors.
  Expand/collapse, selection, context menus and native keyboard navigation remain
  available. Rendering reads cached tree items only, with no filesystem queries.
- Clicking a folder navigates the active tab; tab/path changes synchronize the
  tree. ZIP previews synchronize to their containing persistent folder, never
  exposing an extraction temp path as the logical root.
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

## Operations have explicit targets

In one-panel mode, F5/F6 ask for a destination folder. Cancelling does nothing.
F9 with one file/folder (or no selection, meaning the current folder) asks for a
matching comparison target. Two selected items can be compared directly.
Hidden panels are never used as implicit copy/move/compare destinations.

## No drive-wide scanning

Drive enumeration uses the Windows drive-letter bitmask rather than probing all
drives. Expanding a tree node reads only that directory's immediate entries on
background workers. Selecting a tab inserts its already-known ancestor path
without scanning the ancestors or their descendants.

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
