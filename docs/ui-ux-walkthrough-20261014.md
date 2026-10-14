# PFC UI/UX walkthrough — 2026-10-14

Scope: v0.18.28 baseline → v0.18.29. This is developer task-based review,
not independent user acceptance or proof that every OS/application integration
works. Fixtures are isolated; no live cloud accounts or user files are changed.

## User tasks and priorities

1. Start a search and tell immediately whether it is running, finished without
   matches, cancelled, limited, unreadable/partial or failed.
2. Open documents/comparisons and find loading, cancellation and failure states
   near the controls, without looking below a large content area.
3. Adjust preferences, navigate panels and review rename drafts at a readable
   font size, without unnecessary instructions displacing the content.

## Findings and implemented changes

| Priority | Observable problem | Change |
|---|---|---|
| High | F4 status and progress were below the results; empty results were ambiguous. | Persistent status immediately below Find/Cancel; contextual empty-result explanation. |
| High | Receiving any match replaced “Searching” with a bare count. | Running state retains “found so far”; terminal states are explicit. |
| High | Cancel/limit completion displayed 100% and zero time remaining. | Partial/cancel/failure states never pretend to be a full search. Activity disappears after stopping. |
| High | Folder discovery cannot establish a trustworthy total or ETA. | Indeterminate activity plus real elapsed time, folders scanned and unreadable count; no speculative percentage or ETA. |
| High | Unreadable traversal/stat/content could silently look like no matches. | Unreadable counts and incomplete status; unexpected worker exceptions also enter automatic diagnostics. |
| Medium | Query edits could describe different criteria from an active worker. | Freeze query controls while searching; Results actions remain usable for collected items. |
| Medium | Reopening during a pending cancellation left Find disabled without a reason. | “Stopping previous search” until the old worker returns; stale messages are drained. |
| High | Preview, text, workbook and folder comparison status was below content. | Compact top activity row with loading/cancelling/error text and animation only while busy. |
| Medium | Initial Markdown Preview accepted input before asynchronous loading finished. | Preview's text starts read-only; an actual insert attempt during loading is a regression case. |
| Medium | Folder Compare mixed find status with bottom sync actions. | Find feedback stays with Find; scan state stays beside Compare/Cancel. Idle scan Cancel is disabled. |
| Medium | Appearance explanation consumed several lines at 200%. | Short primary text; keyboard-accessible Auto Font Details retains the complete rules. |
| Low | Unchanged batch-rename items were emphasized green like actionable changes. | Neutral unchanged rows; proposed changes and errors remain distinguishable. |

Repeated identical search label/geometry updates are avoided, reducing needless
repainting. Full paths and stack details remain inspectable; the display changes
do not introduce automatic writes, uploads, commits, deletes or network activity.

## Whole-application route inventory

| Route | Review/verification route | Decision |
|---|---|---|
| Main 1–4 panels, tabs, tree, path/navigation, quick filter, zoom | Existing navigation/tree/tab/interaction checks and new walkthrough | Preserve stable browsing scale and established key behavior. |
| Files/Go/View/Tools/Help menus, column/context menus | Existing nested/context/column/header/menu checks; code inspection | Preserve native Explorer menu ownership; do not replace it with a duplicate. |
| F2 and batch rename; confirmation/conflict dialogs | Control scaling, workflow and rename checks; actual 200% screenshots | Keep action footer and collision validation; neutralize unchanged rows. |
| F3 and Markdown reading/workspaces/bookmarks | Preview/Markdown checks plus visible-status assertions | Put work state above the document; preserve tabs and reading state. |
| F4 Search and result navigation | Search checks plus controlled slow/failing/unreadable fixtures | Explicit top status and partial-result semantics. |
| Copy/Move/Delete/Compress/Extract/archive open | Existing reliability/archive/workflow checks; progress-dialog inspection | Existing dedicated progress dialogs already present near their controls; preserve confirmations. |
| F8 VCS and tool configuration | Existing VCS tests/code inspection | Preserve local-only status queries and explicit external GUI operations. |
| F9 text/workbook/folder/archive comparison, drafts and sync review | Review-compare checks, workflow visual matrix, status assertions | Move activity up; preserve read-only/draft/save boundaries. |
| Settings six pages and enlarged comparisons | Settings/scaling/preview/layout checks and walkthrough | Shorten Appearance copy without shrinking the user's font. |
| Command palette, workspaces, saved comparisons | Workflow visual checks at 100/150/300%, light/dark | Existing compact list + keyboard navigation retained. |
| Update, diagnostics/export/clear | Existing progress-dialog inspection and Preview/diagnostics tests | Preserve explicit version/session identity and confirmed destructive actions. |

## Evidence and limits

Before Search and control-dialog screenshots are retained privately outside Git.
After captures cover running/empty/failed search, 100/200% and narrow layouts,
English/Traditional/Simplified Chinese, light/dark, Preview and Folder Compare.
Text/workbook and other route evidence comes from their existing GUI fixtures.
The new check is `tools/ux_walkthrough_check.py`; regression cases include
cancel, result limit, unreadable content, stale-worker reopening and neutral rename.

Final test and release results are recorded in maintenance run
`68e3f0a3ce8244a597eeab0eb51e1190` rather than assumed from screenshots.
Windows acceptance requires the same candidate under both Python 3.13.15 runtimes
on Win11-ARM64-VM. The x64 runtime is Windows emulation, not native x64 Windows.

Remaining recommendations: inspect live OneDrive/network waits when specifically
authorized; validate third-party native Shell dialogs on a native x64 machine;
continue observing the previously reported transient native tooltip issue.
These are not claimed fixed by moving status rows. Filesystem/device stalls may
delay cancellation until the current OS read returns; that wait is now explained.
Larger workbook metadata may wrap at high scales because read-only/formula/date
limitations must remain visible; do not remove correctness warnings for density.

## Maintenance follow-up — 2026-10-15

The first full run found a stale Help-menu smoke-test label from before automatic
Error/Warning logging; its expectations were updated, including the new Search
idle/completed activity behavior. A subsequent 99-check full run passed.

The first x64 Windows attempt timed out after its first two checks had passed.
Leased read-only inspection found `result.json` one check behind `result.tmp`;
an I/O failure had also been mislabeled as a display failure. This supports a
Windows report-replacement/sharing conflict rather than a PFC Search failure.
The test worker now retries bounded transient PermissionError replacement and
separates display errors from file I/O. Unit regressions cover transient/permanent
failures and classification. The native walkthrough creates a real deny-delete
Windows reader handle, demonstrates the old replacement failure, then releases
it and verifies successful publication. Final matched dual-runtime and full-suite
results remain in the maintenance trace; an earlier timeout is not acceptance.

## Final verification — 2026-10-15

- Final portable SHA256: `2bf6ff4b0879425ac218bb0767850b9ca71f239f4fc37d60c2f09513419c900a`.
- Full inventory: 403 unit tests completed (9 platform skips), plus all 98 GUI
  checks passed across the declared source/portable routes (99 runner checks).
- Windows Python 3.13.15 ARM64 and Windows-emulated x64 each passed the same five
  checks: UX walkthrough, Search results, Preview tabs, review comparison and
  control scaling. The native sharing-lock and loading-read-only regressions
  passed in both environments. Cleanup confirmed; guest networking not enabled.
- Check execution totals: ARM64 112.341 s, emulated x64 140.605 s, excluding lease,
  readiness, staging and evidence transfer. These are observations, not a native
  x64 benchmark or proof of token savings.
- Actual-size screenshot review covered visible wait/empty/failure distinctions,
  100/200% and narrow layouts, Chinese/English and light/dark. Appearance's font
  scale control is visible initially at 200%; its Details button retains full
  rules. Loading Preview no longer accepts text input.
- Complete task timing and earlier failed attempts remain in the trace. Token
  counters are unavailable and no comparable whole-task baseline exists.
