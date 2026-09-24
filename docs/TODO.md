# PFC follow-ups

## Current completion boundary — 2026-09-25

The actionable offline defects and Preview-tab request below are implemented and
validated. This is not a declaration that all TODOs are closed.
External acceptance and explicitly deferred Markdown features remain open:

- Windows test account readiness: OneDrive process running; one configured,
  present root; one sampled entry returned unknown metadata. No network enabled,
  content downloaded, pin state changed or account login attempted. This supports
  readiness only, not online/local/pinned/pending/error transition acceptance.
- TortoiseGit, TortoiseSVN, Git CLI and SVN CLI absent on the leased VM. Real
  external-dialog tests require installed clients; no automatic installation.
- Cloud-link support still requires a provider-specific no-recall implementation
  and live-provider proof. Manual F3 remains explicit and separate from link following.
- Deferred Markdown scope is a design gate, not a hidden automatic index: explicit
  bounded workspace selection is required before basename links/backlinks/scoped
  search; media needs path/size/format limits; Mermaid/math needs a renderer choice;
  plugins/executable queries require a separate execution/security decision.
  These were not silently enabled by a generic UI polish change.

The user clarified on 2026-09-25 that the earlier same-version exception applied
to the failed repair only. These new features and corrections ship as v0.18.7,
with a rebuilt portable and new tag so Check for Updates can discover the release.
Preserve the original v0.18.6 tag and its failed-retest evidence.

## F3 Preview — readable text files appear blank (v0.18.7)

- [x] Investigate and fix files that display text normally in an external editor
  but show no text in PFC Preview. Photo 38905.jpg shows `skill.yaml` readable in
  Notepad++ while PFC Preview has View set to Auto and an empty content area.
  This is a reported example, not proof that every YAML file is affected.
- [x] Build a non-confidential reproducer and
  distinguish file-type detection, encoding/decoding, loading errors and rendering
  issues. A three-line YAML reproduces a `TypeError`: the translated
  `{language} syntax` placeholder collided with `tr_for_language`'s locale
  parameter, before text insertion. Make locale parameters positional-only;
  regression covers all four UI languages and multiple syntax formats.
- [x] Acceptance: readable text appears in Auto and plain-text preview; switching
  files does not leave an unexplained blank area. Unreadable/unsupported files
  show an explicit explanation rather than silently displaying nothing.

Linux package and Windows portable GUI checks cover YAML, Python, JSON, XML,
PowerShell, plain text, UTF-16, Auto/Text and explicit missing-file errors.

## F3 Preview — multiple file tabs (v0.18.7)

- [x] Support multiple file tabs within one Preview window, especially for
  quickly switching between several Markdown documents.
- [x] Selecting multiple files and pressing F3 opens those files as separate
  preview tabs in that window.
- [x] Pressing F3 on additional files later adds tabs to the existing Preview
  window instead of replacing the currently previewed document.
- [x] Verify that switching tabs retains each document's preview state and
  reading position, so comparing several MD files does not require reopening
  them or repeatedly finding the same passage.

Each tab owns its widgets/state, rather than reconstructing one document view
on each switch. Deferred loading, active-tab-only refresh, one active Markdown
worker, and an explicit 32-tab limit bound resource use. Ctrl+Tab, Ctrl+Shift+Tab,
Ctrl+W, middle-click close and a full-path Open documents list support navigation.
Linux and Windows tests exercise real file-list multiselect F3 and repeated opens.
Search-result multiselect uses the same tabs, covered by Linux package/portable checks.

## Folder-tree scroll painting — REOPENED, v0.18.6

User retest on 2026-09-23: selection/highlight tearing during Tree View wheel
scrolling is unchanged and still frequent. The v0.18.6 attempt is NOT an accepted
fix. Defer investigation and implementation until the usage allowance recovers;
reuse v0.18.6 for the eventual correction, per the user's explicit instruction.
Work resumed on 2026-09-24. The candidate replaces the split renderer itself:
transparent native item images contain the lines/icons, and Treeview owns the
entire selected row. No independent row Canvas remains. The old attempted fix
and its failed user retest remain recorded below. On 2026-09-25 the user clarified
that this correction plus new features should ship as v0.18.7. The original
v0.18.6 tag remains unchanged; real-laptop acceptance is still pending.

- [ ] Navigation-triggered tearing: from the user folder, enter OneDrive in the
  file list. The left tree highlight becomes split/clipped (photo 38854.jpg;
  38850.jpg is the starting state). Cover folder navigation as well as scrolling.
- [x] Tree/current-folder synchronization: enter Desktop inside OneDrive. The
  file list and active tab show Desktop, but the left tree does not visibly
  locate/highlight its corresponding node (photo 38857.jpg). Check selection,
  ancestor expansion and viewport positioning separately. Navigation now settles
  visibility after floating-header geometry, not only after background scans.
  Local OneDrive-shaped fixtures pass on Linux and Windows; live provider retest
  remains alongside the navigation-triggered tearing item above.
  Acceptance: the correct Desktop node is selected and fully visible,
  with an intact highlight, after navigation and background folder loading settle.
- [x] Replace the independent selection/icon/text rendering during continuous
  wheel scrolling, including floating-ancestor entry/exit. Do not mark complete
  solely because internal coordinates or synthetic wheel tests pass.
- [x] Reproduce Windows OS-level wheel interaction and capture transient frames
  with GDI. Same fixture and 127 real wheel events: released v0.18.6 has 32 split
  frames / 652 (36.2 fps); candidate has 0 / 691 (38.4 fps). The old split screenshot
  confirms the mismatch visually. This is controlled Windows evidence, not the
  user's physical laptop / OneDrive acceptance. Preserve failed-attempt evidence.
- [ ] User retest on the affected laptop, including actual OneDrive navigation.
- [x] Preserve platform wheel behaviour, Ctrl+wheel zoom, keyboard navigation,
  scrollbar movement, dotted lines and all floating ancestors.
- [x] Reuse normal-size navigation icons in floating rows instead of generating
  a second set during the first scrolling transition.
- [x] Add immediate-dispatch regression checks: the old portable fails, while
  package, portable and offline Windows pass 432 checks each across three themes,
  100/150/175/200% and text/icon/sticky wheel targets. Periodic repaint is disabled
  in this test so delayed repairs cannot hide a failure.
- See [diagnosis and validation](folder-scroll-validation.md).

## F8 version control — v0.18.5

- [x] Fit F8 into the measured-width single-row action bar without shrinking fonts
  or sacrificing zoom/transfer destination labels.
- [x] Shared selection-scoped Git/SVN menus, local-only asynchronous status,
  explicit unknown/upstream cache states, Tortoise dialog hand-off and saved paths.
- [x] Guard mixed repositories, metadata/archive locations and child-window F8;
  test package/portable layouts and Windows native UI offline.
- [ ] End-to-end real TortoiseGit/TortoiseSVN dialog verification on a Windows
  installation with those clients. The shared VM has neither installed; this
  release validates command construction/dispatch without committing or pushing.
- See [F8 guide and safety boundaries](vcs-actions.md).

## Understandable panel layout comparison — v0.18.4

- [x] Replace duplicated single-pane screenshots and tiny diagrams on Layout &
  Tabs with whole-workspace Before/After illustrations for all 1–4 panel modes.
- [x] Distinguish the 1-panel folder tree from its file list and show a shared
  tab strip; show independent tab strips and numbered file lists in 2–4 panels.
- [x] Label current/draft counts, reflect tab shape, keep Before unchanged until
  Apply and use the same renderer for enlarged comparison. No live file access.
- [x] Remove duplicate explanatory blocks to keep compact settings usable.

## Preview on every Settings page — v0.18.3

- [x] Keep a fixed-top preview on all six pages, not just Appearance and Layout.
- [x] Live file-column example uses shared date/size formatting, visibility,
  sorting and independent cloud/VCS badges; safe sample data only.
- [x] Show menu/deletion/error policy and three prefix examples, formatted/plain
  Markdown, draft language and Windows sign-in behavior without executing them.
- [x] Stable sample heights and unchanged-draft image reuse; explicitly release
  preview images/fonts on the UI thread when switching pages.
- See [Settings design and validation](settings-design.md).

## Settings visibility and clarity — v0.18.1

- [x] Keep larger current/draft style previews above the scrolling controls;
  compare both original demo screenshots together in a screen-bounded window.
- [x] Label the font sample with its actual percentage and distinguish fixed
  scale from the auto-size reference. Keep Settings and sample layout stable.
- [x] Review all six pages: nearby scope/safety explanations, paired panel
  diagrams, dependent column controls and protection from accidental wheel edits.
- [x] Replace Settings checkbox crosses with crisp ticks; preserve off/disabled
  states, keyboard focus and Space-key toggling, without changing other dialogs.
- Validation details: [Settings design](settings-design.md).

## Folder icon cache — v0.18.2

- [x] Replace the shared directory key with lexical absolute paths, retaining
  per-file shortcut icons and safe generic executable lookups. The first folder
  (often Downloads) can no longer override other folders after navigation/zoom.
- [x] Bound each provider to 512 recent entries. File rows pin displayed images
  separately, releasing them after navigation, search/result replacement or
  preview; eviction and font resizing must not blank existing rows.
- [x] Add order-independent identity, LRU eviction and overlay unit regressions;
  `tools/folder_icon_check.py` covers navigation, zoom, retained Tcl images,
  preview/search transitions and native Windows Shell pixel comparisons.
- Validation details: [folder icon identity](folder-icons.md).

## Truthful folder expansion hints — v0.18.0

- [x] Replace placeholder-based plus indicators with confirmed child-directory
  hints. Empty and files-only folders are plain leaves before the first click.
- [x] Single bounded background hint worker; visible rows only, early exit,
  no recursive index or file reads, guarded cloud/link/share probing.
- [x] Preserve unknown-state manual discovery; ignore stale refresh results and
  prevent late hints from replacing children discovered by actual navigation.
- [x] Add leaf/branch/unknown, keyboard, zoom/contrast, stable redraw and refresh
  regressions; see [single-panel behavior](single-panel.md) for scope and limits.

## Folder hierarchy follow-up — v0.17.29

- [x] Fix startup-only ancestor chains: complete immediate sibling lists along
  the active path through the bounded background pool, not only after a click.
- [x] Remove unconditional vertical guide continuations. Normal and floating
  tree rows now join actual sibling branches and end at the last child.
- [x] Merge seeded path nodes and discovered siblings in sorted order, preserving
  selection, expanded IDs and viewport context; unrelated descendants stay lazy.
- Validation details are recorded in [single-panel behavior](single-panel.md).

## Regression follow-up — 2026-09-22

- [x] Markdown worker shutdown (v0.17.28): full unit runs could emit a background
  `BrokenPipeError` from `mdjobs.py`'s sender `finally: process.stdin.close()`
  although all 201 baseline test assertions completed successfully. Cancellation
  cleanup now tolerates a closed worker pipe; an explicit thread-exception
  regression verifies cancellation cleanup.

## Approved workflow expansion — v0.17.28

- [x] Safe original-source text editor: preserve encoding/BOM/EOL, reject external
  changes, do not save synthetic aligned rows; archive sides remain read-only.
- [x] Named comparison sessions and exclusion rules, persisted locally.
- [x] Command/Settings search (Ctrl+Shift+P), with modal shortcut isolation.
- [x] Markdown bookmarks and reading resume, bounded exact paths and no index.
- [x] Escaped HTML/text comparison reports and bounded inline character differences.
- [x] Named workspaces with path validation and reversible pre-switch snapshot.
- [x] Scanned-file-only copy plans honor excludes and child Skip. Worker copying,
  UI-thread conflict prompts, visible progress and file-boundary cancellation.
- [x] Compact top-area typography, stable-width bold active tabs, responsive
  comparison columns and keyboard-accessible pickers.
- See [workflow guide](workflow-upgrade.md) for scope and deliberate exclusions;
  [three-round validation](workflow-validation-2026-09-22.md) records evidence and
  release checks.

## Single-panel workspace — v0.17.21

- [x] Approved: all-drive lazy tree, shared visible-group tabs with owner restore,
  new tabs in P1 and explicit operation destinations.
- [x] Full-width tab strip, adjustable/saved 1/3 tree–2/3 file-list layout,
  shared settings, cross-group reset locks, saved mode/order and restart behavior.
- [x] Bounded background one-level scans, cancel/timeout/error handling, no index.
- [x] Source/portable focused checks and unit tests. See [single-panel design](single-panel.md).
- [x] Full headless regression suite passed before release preparation (186 unit tests, 8 platform skips,
  source/portable UI checks); closing tabs and combined Ctrl+Tab additionally checked.
- [x] Offline Windows portable regression and 150% visual check; tested artifact
  SHA-256 `35f31a50d7ba8e5de65f3f56fdc2d7dceabfaec97d91c4e35596cf2642c4642f`.
  VM lease released; this records the original pre-release validation artifact.
- [x] Solid hierarchy connectors, last-child corners and expanded-parent lines;
  clipped to indentation cells, theme/zoom-aware, native text and keyboard retained.
- [x] v0.17.21 offline Windows connector/scroll tests at 100/150/300%, shared-panel
  and Tab Lock regression passed; final artifact hash recorded in the design doc.
- [x] Final v0.17.21 full headless suite passed (187 unit tests, 8 platform skips,
  plus all source/portable GUI regressions).

## Selected Tab Lock design — v0.17.21

- [x] Apply selected C variant with same neutral tile color for both modes:
  dark grey on light themes; light grey on dark theme.
- [x] Distinct lock / large return-arrow silhouettes, edge-aligned compact layout,
  antialiased font-sized rendering; preserve lock behavior and custom tab colors.
- [x] Source and portable GUI regression for themes, shapes, zoom, image reuse,
  hit testing and navigation. See [design specification](tab-lock-design.md).
- [x] Offline Windows portable check passed at 100/150/300%; VM lease released.

## Contextual settings — v0.17.20

- [x] Blank file-list area: Panel Counts and Right Click Menu, plus relevant view,
  column, refresh, font and color settings; no destructive file operations.
- [x] Tab and empty tab bar: shared Tab Style; group Tab Color, preserve locks.
- [x] View-mode and zoom controls: mouse/keyboard context access to their settings.
- [x] Shared main-menu preferences and persistence; Linux/Windows regression and
  scaled cascade validation. See [context settings](context-settings.md).

## Markdown reading expansion — v0.17.19

- [x] Document risks and scope in [the safety plan](markdown-preview-safety-plan.md).
- [x] User subsequently authorized implementation within a two-hour work window.
- [x] Move Markdown read/parse/probe to one isolated worker: cancel, five-second
  deadline, stale-result rejection, 512 MiB OS memory limit, bounded output and
  chunked insertion. Rich rendering falls back to labeled source when limited.
- [x] Exact local Markdown paths within a fixed boundary; zero link indexing,
  search, hover I/O or prefetch. In-memory Back, no source writes.
- [x] Read-only tasks and expanded labeled callouts; heading/property navigation
  and folding. Search and Copy include folded content. Unicode offsets tested.
- [x] Linux source/portable and Windows portable GUI checks; Windows pythonw,
  junction/offline-attribute rejection, cancellation/timeout and ZIP boundaries.
- [ ] **Cloud links** — Intentionally refuse all Windows reparse-linked paths,
  including resident OneDrive cases, until a provider-specific no-recall path is
  authorized and validated. This does not prevent explicit manual F3 preview.
- [ ] **Deferred, not automatic fallbacks** — Vault/basename wikilinks, backlink
  graphs, scoped search, embedded media, Mermaid/math, plugins and executable
  queries. No whole-drive index is introduced.

## Requested UI / UX backlog — 2026-09-19

Implementation and research authorized by “進行Todo 項目”. Results and boundaries
are in [the UI/UX review](ui-ux-review-2026-09-19.md). Research tasks are complete
as proposals, not unapproved visual changes or full Obsidian compatibility.

1. [x] **Simplify column right-click menus (v0.17.18)** — Removed duplicated ascending/descending commands; heading-click sorting remains.
2. [x] **SVN / Git overlay visibility switch (v0.17.18)** — One saved VCS switch in Name settings, independent of OneDrive. Disabling prevents new scans and refreshes icons without recreating rows.
3. [x] **OneDrive online/local icon comprehension (v0.17.18)** — Documented cloud/outlined-check/filled-check meanings and separate placement from VCS badges. Added localized consequence explanations to hover tooltips. Live-provider acceptance remains pending below.
4. [x] **Tab lock-mode visual options — research complete** — Compared lock glyph, text badge and heavy edges. The subsequently selected C variant is implemented in v0.17.21 (see above).
5. [x] **Compact zoom control (v0.17.18)** — Removed down arrow only; percentage menu, keyboard access and plus/minus remain.
6. [x] **Markdown rendering and Obsidian research (v0.17.18)** — Read-only tables and literal property values, cell wrapping/horizontal scrolling, search/source view, safe handling of nested/unknown syntax. Obsidian candidates and limits documented separately, not implemented implicitly.
7. [x] **Top-area typography and layout standards** — Approved in the subsequent workflow batch and implemented in v0.17.28: compact menu/version text, bold headings and active tab, no extra permanent toolbar and no tab-width jump.

- [x] **Tab-lock design decision** — User selected C with matching neutral tile colors and distinct compact silhouettes; see the selected-design section above.
- [x] **Top-area design decision** — User authorized the full priority batch, emphasizing compact, useful and stable UI; applied in v0.17.28.

## Existing follow-ups

- [x] **File Columns third-level submenu (v0.17.18)** — Fixed a confirmed return/re-entry path: Left/Escape removed the child but retained its parent's selection; hovering that same row returned early without reopening. Added screen-coordinate grab routing and prevented a stationary pointer from overriding keyboard navigation as cascades appear. Native Windows tests pass all four columns at 100/150/300%, both window edges, same-row re-entry and keyboard traversal. Initial direct opening on the offline VM already worked in v0.17.17; this establishes a reproducible failure path, not proof of the exact original screenshot sequence.

- [x] **OneDrive sync status overlay — implementation (v0.17.17)**: background, bounded visible-row queries of fast local Windows properties; online/local/pinned/pending/error/paused/warning badges, separate from Git overlays, with a preference and status tooltip. No content reads or hydration request. Missing metadata remains unknown.
- [ ] **OneDrive live-provider acceptance**: verify actual transitions (online-only → local, pin/unpin, pending/error/recovery) on an authorized signed-in Windows OneDrive installation. Offline fixtures and native ordinary-file checks do not establish this. Do not enable VM networking or sign in without authorization.

- [x] **Path bar long-lock font protection (v0.17.17)**: pin named and derived fonts to the selected zoom's pixel sizes, preserve negative sizes instead of copying point-converted `Font.actual()`, and restore intended sizes on breadcrumb redraw. Windows 11 test locked for **667.1 seconds** at 150%; after unlocking the font remained **-18 pixels**, layout assertions and underline checks passed. Injected shared-font and Tk-scaling changes also pass. This is a validated mitigation; the original machine's exact DPI/lock trigger was not reproduced in the offline VM.
