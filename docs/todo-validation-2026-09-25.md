# TODO correction and UI/UX validation — v0.18.7

## Implemented

- Native folder-tree row image prefixes replace per-row overlay windows. Native
  selection now shares the text/icon painting surface. Fine dotted connectors,
  plus indicators, theme/zoom, keyboard interaction and all sticky ancestors remain.
- Navigation reveals/focuses the current node after sticky geometry settles;
  bounded retries stop when the user scrolls or selects elsewhere.
- Syntax Preview's blank YAML/code root cause is a translation argument collision,
  reproduced with a three-line non-private YAML file. Positional-only locale
  parameters allow a `{language}` display placeholder without an exception.
- One F3 window contains independent, lazy-loaded documents, including main-list
  and search-result multiselect. Repeat F3 deduplicates exact normalized paths.
  Scroll, search, wrap, modes, Markdown folds/history stay per document. Inactive
  pages do not auto-refresh; a tab limit and active-worker cancellation bound use.
- Compact document tabs preserve filename suffixes; a full-path menu handles
  duplicate filenames and overflow. Close-tab button, middle click, Ctrl+W and
  Ctrl+Tab/Shift+Ctrl+Tab support mouse/keyboard navigation. Window Esc still closes.

## Evidence and limitations

- Unit suite: 248 tests, 8 platform skips.
- The headless runner covers 76 package/portable GUI invocations. Legacy Canvas
  assertions were updated to inspect actual native image pixels, branch geometry,
  hit targets and the absence of separate row surfaces. After correcting the test's
  old center-of-icon expansion target to the plus badge, the remaining suite was
  resumed from the tree checks. Focus is settled before native keyboard simulation.
- Windows portable: Preview tabs/text checks, deep-folder navigation checks and
  432 immediate scroll checks passed, all exit 0. A Traditional Chinese Preview
  screenshot was visually reviewed for tab/toolbar/content visibility.
- Independent native OS wheel/GDI A/B: published build 32 split frames / 652;
  candidate 0 / 691, both 127 wheel events. See [images and raw measurements](folder-scroll-validation.md).
  This is evidence against the old mechanism, not a promise about every compositor
  frame or acceptance on the reporter's laptop.
- Final search-result multiselect and active-tab wrap persistence adjustments were
  rechecked in Linux package/portable Preview tests; Windows checks predate those
  two small refinements. No claim of full Windows coverage for every adjustment.
- VM network remained disabled and the lease was released. Offline OneDrive
  readiness found a running process, one configured/present root and one sampled
  entry with unknown metadata. No content was downloaded or state changed. Real
  provider transitions remain open. No Git/SVN CLI or Tortoise clients installed;
  real confirmation-dialog acceptance remains open.

## Delivery

The user clarified that the earlier same-version exception covered the failed
repair only; the new features and corrections are released as v0.18.7. Rebuild
the portable on main and publish a new v0.18.7 tag for Check for Updates discovery.
Preserve the original v0.18.6 tag. The private GitLab mirror must match main and
both version tags. This version-only release does not expand the test claims above.

Deferred cloud links and larger Obsidian-style extensions are not silently enabled:
their bounded workspace, provider no-recall, renderer and execution-policy decisions
remain in [TODO](TODO.md) and the [Markdown safety plan](markdown-preview-safety-plan.md).
