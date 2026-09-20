# PFC follow-ups

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
7. [x] **Top-area typography and layout standards — planning complete** — Relative font sizes, two weights, spacing, alignment and emphasis specified for review. Existing header/tab visual design remains unchanged.

- [x] **Tab-lock design decision** — User selected C with matching neutral tile colors and distinct compact silhouettes; see the selected-design section above.
- [ ] **Top-area design decision** — Review typography/layout proposal before applying its broader visual redesign.

## Existing follow-ups

- [x] **File Columns third-level submenu (v0.17.18)** — Fixed a confirmed return/re-entry path: Left/Escape removed the child but retained its parent's selection; hovering that same row returned early without reopening. Added screen-coordinate grab routing and prevented a stationary pointer from overriding keyboard navigation as cascades appear. Native Windows tests pass all four columns at 100/150/300%, both window edges, same-row re-entry and keyboard traversal. Initial direct opening on the offline VM already worked in v0.17.17; this establishes a reproducible failure path, not proof of the exact original screenshot sequence.

- [x] **OneDrive sync status overlay — implementation (v0.17.17)**: background, bounded visible-row queries of fast local Windows properties; online/local/pinned/pending/error/paused/warning badges, separate from Git overlays, with a preference and status tooltip. No content reads or hydration request. Missing metadata remains unknown.
- [ ] **OneDrive live-provider acceptance**: verify actual transitions (online-only → local, pin/unpin, pending/error/recovery) on an authorized signed-in Windows OneDrive installation. Offline fixtures and native ordinary-file checks do not establish this. Do not enable VM networking or sign in without authorization.

- [x] **Path bar long-lock font protection (v0.17.17)**: pin named and derived fonts to the selected zoom's pixel sizes, preserve negative sizes instead of copying point-converted `Font.actual()`, and restore intended sizes on breadcrumb redraw. Windows 11 test locked for **667.1 seconds** at 150%; after unlocking the font remained **-18 pixels**, layout assertions and underline checks passed. Injected shared-font and Tk-scaling changes also pass. This is a validated mitigation; the original machine's exact DPI/lock trigger was not reproduced in the offline VM.
