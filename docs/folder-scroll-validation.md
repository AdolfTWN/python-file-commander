# Folder-tree selection scroll repair — v0.18.6

## Cause

The native Treeview paints the row text while child canvases paint its indentation,
selection background, dotted connectors and folder icon. The old wheel binding
let native text move first; the canvases were repaired by `after_idle` (or the
80 ms polling pass). Creating/removing the floating ancestor band also scheduled
geometry changes and another deferred repaint. The two parts could temporarily
belong to adjacent rows. Selection itself did not change.

The original 30 fps user recording contains separate visible one-row splits of
roughly 33–100 ms. The offline Windows timing fixture independently measured a
44 px difference between the native selected row and its canvas at 175% zoom.
These are observations, not a claim that every machine has identical timing.

## Repair

- A private bindtag runs after native Treeview wheel/key/pointer handling, before
  returning to the paint loop; it synchronizes the visible-row canvases directly.
- Scrollbar callbacks and Configure events use the same guarded redraw path,
  covering programmatic scrolling and floating-band layout changes too.
- Cancel redundant pending idle repairs. Do not call `update()` recursively,
  block Windows painting, alter wheel increments, or force periodic redraws.
- Full-size floating icons share the existing navigation images. Compressed deep
  ancestor bands still receive correctly sized independent images after zoom.

## Validation (2026-09-23)

- New `tools/folder_scroll_check.py`: 432 checks per run, three themes,
  100/150/175/200%, wheel over text/icons/sticky rows, upward/downward boundary
  crossings, scrollbars, horizontal clipping and Ctrl+wheel zoom. The core
  assertions run immediately after wheel dispatch, with no sleep/update first
  and no periodic tree poll. Also check after geometry/idle work.
- Negative control: unchanged v0.18.5 portable fails this check with a stale
  visible canvas. Fixed package and portable pass; Windows 11 ARM64 portable
  passes all 432 checks with exit code 0, offline.
- Windows screen sampling during the independent 24-wheel timing fixture:
  129 frames with a detectable selection band show no left/right split. This is
  sampled visual evidence, not a guarantee about every compositor frame/device.
- Existing sticky-ancestor, branch-line, startup, hierarchy, leaf-discovery,
  double-click, one-panel and zoom checks pass. Unit suite: 247 tests, 8 skips.

No files were committed, pushed, moved or deleted by the Windows fixture. It uses
a synthetic cached folder tree and a temporary INI; no network access is needed.
