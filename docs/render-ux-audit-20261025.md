# Cross-format F3 Preview UX and reliability audit

Version v0.18.43; maintenance run `31b785db34454224b48dc17d047435b6`.
This is a developer-operated review with isolated fixtures, not user acceptance.

## Observable tasks and coverage

1. Find a late value without losing the rendered view or earlier matched paths.
2. Read a long/multiline cell, resize its column, switch header mode and copy it
   without losing content or the selected data row.
3. Interrupt expensive work, retry or change tabs, and continue manual scrolling
   without stale callbacks or a search repeatedly taking over the viewport.

| Formats | Shared behavior / scope |
| --- | --- |
| JSON, JSONL, NDJSON, YAML, YML, TOML | Same structured search/reveal worker, retained visited branches, Find All Matched, scalable expand/collapse, complete wrapped values, stable key widths, cancellable expansion and explicit bounds. These optimizations were already shared, not JSON-only. |
| CSV, TSV | Added complete multiline cells through Wrap, the same bounded/batched row-layout engine, stable widths through font changes/reload/header-mode switching, retained selected data row and late-cell search visibility. Header and content searches remain lossless. No hierarchy-only actions are shown. |
| HTML, HTM, SVG, Mermaid/MMD, Notebook | Static isolated raster previews; searchable rendered text where indexed, zoom, Copy, explicit partial-search scope. Fixed redraws repeatedly recentering an existing search hit after manual pan. No document scripts, notebook cells or external resources are executed. |
| Diff, patch, Source fallbacks | Existing bounded text insertion, text search, wrap where safe, lossless Copy, hunk navigation. Pathological single lines retain bounded display windows and explicit notices. |
| Markdown | Separate existing reading pipeline, folds, links, reading positions and search; retained and included in the complete Preview regression profile. |

All input, node, match, image and display bounds remain in place. A partial
preview is not represented as a full-file search. The review does not add
renderers for unsupported extensions or make native x64 Windows claims.

## Reproduced before / implemented after

- A manually set CSV column width of 135 pixels became 117 after `rescale()`.
  Table widths now initialize once and survive rescale, reload and header mode.
- Table rows previously used fixed-height native cells; Wrap was disabled and
  cells displayed at most 500 characters. They now reuse variable-height canvas
  layout when Wrap is enabled. Unwrapped cells remain visually clipped; Copy
  keeps original text. Header-mode changes preserve corresponding row/cell.
- Image redraw previously always revealed the old search hit. Revealing now
  occurs on Find, while repaint retains the user's pan and the match outline.
- Full-value popups previously inserted entire pathological unbroken lines into
  Tk Text. They now clearly label a first-16K display window, provide horizontal
  scrolling and lossless Copy value. Ordinary values remain fully displayed;
  selected text can still be copied separately.
- Cancel during table layout retains the prior view, stops scheduled layout and
  reports layout cancellation rather than incorrectly claiming a search stopped.
- Preview page destruction now cancels its polling/refresh callbacks and stops
  ttk's Tcl-side progress timer before widgets disappear, including direct parent
  destruction and partial-construction failure paths.
- An additional CRLF stress case reproduced a real search-position error in both
  structured and table cells: original search offsets included CRs, while the
  painted lines did not. Normalize the offset as well as the displayed text. The
  regression asserts that the actual matching line lies inside the viewport,
  rather than accepting just a correct match count or selected row.

## Acceptance evidence

The regression suite adds real-Tk coverage of six structured suffixes with late
matches beyond the initial 3,000-node tree, retained branches, bulk reveal,
case-sensitive misses, stable widths, cancel/restore and unchanged sources.
CSV/TSV tests cover Wrap toggles around a late hit, reload, empty/wide tables,
header changes, 200% font controls, cancellation/recovery and lossless copying.
Further checks cover image pan retention and bounded long-value popups.
Initial validation caught Tcl option members needing string normalization,
and a long-cell test fixture that fit entirely at Windows' smaller font metrics.
Those failures are retained; the corrected fixture requires real scrolling on
both systems. Isolated multi-root tests explicitly reclaim old Tk cycles on the
GUI thread and cancel their own heartbeat timer.

Final candidate SHA-256:
`4ddcb295b7b21eca4662be29e5fa1aec2fe96d353bcce5902c11e0faec8b5110`.

- Final full source/portable suite: 111 groups passed in 514.8713 seconds;
  unit inventory 460 tests, nine existing skips.
- Final Windows ARM64: Render reliability 103.486 s, structure wrapping 7.453 s,
  actual F3/tabs/diagnostics 35.782 s. The reliability script has 21 cases plus
  structured-extension subcases, including real CRLF viewport assertions.
- Final Windows-emulated x64: the same checks passed in 146.407 s, 10.487 s
  and 54.171 s, against identical portable bytes.
- Both final runtime runs reported clean task/network/lease cleanup. Native
  200% screenshots show complete wrapped table text, the retained 155-pixel ID
  column and an unclipped single-row search toolbar. The checked logs contain
  no ignored Tk finalizer, stale timer or destroyed-application warnings.
- The table reflow/cancel/reload heartbeat maximum gap in the fixture was
  0.0683 s on ARM64 and 0.0517 s on emulated x64, below the one-second guard.
  This is an observed fixture bound, not a guarantee for every document.
- Before the last CRLF-only fix, broader five-group matrices also passed both
  runtimes (artifact `ea89d73587c6097d96bc34117d26cbe155c79bca53d1aca6ad99074a8707e561`),
  including the offline format/security matrix and bulk expansion. These are
  supplementary evidence, not falsely attributed to the final artifact.

Native screenshots and detailed timings remain in the private maintenance trace;
fixtures contain no user documents. Windows is ARM64 with x64 application
emulation, not native x64 Windows acceptance. No comparable end-to-end baseline
or official token counters are available; no speed/token savings are claimed.
