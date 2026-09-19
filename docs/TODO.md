# PFC follow-ups

## Requested UI / UX backlog — 2026-09-19

Implementation and research authorized by “進行Todo 項目”. Results and boundaries
are in [the UI/UX review](ui-ux-review-2026-09-19.md). Research tasks are complete
as proposals, not unapproved visual changes or full Obsidian compatibility.

1. [x] **Simplify column right-click menus (v0.17.18)** — Removed duplicated ascending/descending commands; heading-click sorting remains.
2. [x] **SVN / Git overlay visibility switch (v0.17.18)** — One saved VCS switch in Name settings, independent of OneDrive. Disabling prevents new scans and refreshes icons without recreating rows.
3. [x] **OneDrive online/local icon comprehension (v0.17.18)** — Documented cloud/outlined-check/filled-check meanings and separate placement from VCS badges. Added localized consequence explanations to hover tooltips. Live-provider acceptance remains pending below.
4. [x] **Tab lock-mode visual options — research complete** — Compared lock glyph, text badge and heavy edges. Proposed compact padlock/return-arrow variants; no visual design has been selected or applied.
5. [x] **Compact zoom control (v0.17.18)** — Removed down arrow only; percentage menu, keyboard access and plus/minus remain.
6. [x] **Markdown rendering and Obsidian research (v0.17.18)** — Read-only tables and literal property values, cell wrapping/horizontal scrolling, search/source view, safe handling of nested/unknown syntax. Obsidian candidates and limits documented separately, not implemented implicitly.
7. [x] **Top-area typography and layout standards — planning complete** — Relative font sizes, two weights, spacing, alignment and emphasis specified for review. Existing header/tab visual design remains unchanged.

- [ ] **Design decision** — Review tab-lock and top-area proposals before applying a visual redesign; choose any additional Obsidian preview features separately.

## Existing follow-ups

- [x] **File Columns third-level submenu (v0.17.18)** — Fixed a confirmed return/re-entry path: Left/Escape removed the child but retained its parent's selection; hovering that same row returned early without reopening. Added screen-coordinate grab routing and prevented a stationary pointer from overriding keyboard navigation as cascades appear. Native Windows tests pass all four columns at 100/150/300%, both window edges, same-row re-entry and keyboard traversal. Initial direct opening on the offline VM already worked in v0.17.17; this establishes a reproducible failure path, not proof of the exact original screenshot sequence.

- [x] **OneDrive sync status overlay — implementation (v0.17.17)**: background, bounded visible-row queries of fast local Windows properties; online/local/pinned/pending/error/paused/warning badges, separate from Git overlays, with a preference and status tooltip. No content reads or hydration request. Missing metadata remains unknown.
- [ ] **OneDrive live-provider acceptance**: verify actual transitions (online-only → local, pin/unpin, pending/error/recovery) on an authorized signed-in Windows OneDrive installation. Offline fixtures and native ordinary-file checks do not establish this. Do not enable VM networking or sign in without authorization.

- [x] **Path bar long-lock font protection (v0.17.17)**: pin named and derived fonts to the selected zoom's pixel sizes, preserve negative sizes instead of copying point-converted `Font.actual()`, and restore intended sizes on breadcrumb redraw. Windows 11 test locked for **667.1 seconds** at 150%; after unlocking the font remained **-18 pixels**, layout assertions and underline checks passed. Injected shared-font and Tk-scaling changes also pass. This is a validated mitigation; the original machine's exact DPI/lock trigger was not reproduced in the offline VM.
