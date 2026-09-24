# Folder-tree selection scroll correction — v0.18.7

The native-row correction and new Preview features ship as v0.18.7 following
the user's 2026-09-25 clarification. The original v0.18.6 tag and failed-attempt
evidence remain unchanged. Physical-laptop and live OneDrive acceptance remain open.

## Current candidate: native-row rendering (2026-09-24)

The user authorized TODO work to resume. The rendering mechanism is now changed,
not another timing adjustment: each Treeview item owns a transparent image prefix
containing its connector lines and folder icon. The native widget paints the
entire selection and its text in the same row. There are no row overlay child
windows. Shared prefix bitmaps are cached; ordinary drawing does no filesystem I/O.
Floating ancestors remain a separate contextual band; they no longer split any
selected row. Navigation schedules a bounded, cancelable visibility settlement
after the floating band changes geometry. Manual scrolling always cancels it.

### Windows negative control and candidate

`tools/windows_tree_visual_check.py` uses an offline synthetic tree, OS mouse-wheel
input (not Tk event generation), and GDI framebuffer captures. Identical 18-second
runs with 127 wheel inputs yielded:

| Build | Captured frames | Sampling rate | Split frames |
| --- | ---: | ---: | ---: |
| Published v0.18.6 | 652 | 36.2 fps | 32 |
| Native-row candidate | 691 | 38.4 fps | 0 |

Detection compares exact selection-color runs near the left and right row edges,
not the color of folder/PC icons. The baseline screenshot was visually inspected:
left highlight is on Folder 03 while right highlight is on selected Folder 04.
Candidate screenshot has the complete highlight on Folder 04. Captures are of a
synthetic tree only; no personal file paths or account data are needed.

Evidence: [baseline split](evidence/tree-0186-split.png),
[candidate aligned](evidence/tree-native-aligned.png),
[baseline measurements](evidence/tree-0186-result.json),
[candidate measurements](evidence/tree-native-result.json).

Additional Windows portable checks passed with exit code 0: real multi-select F3
tabs/text regressions, navigation between deep Downloads/home/OneDrive/Desktop
shaped local folders at 100/150/175/200%, and 432 immediate scroll/zoom checks.
These results reproduce and address the reported rendering mechanism; they are
not acceptance on the user's physical laptop or live OneDrive provider. Those
retests remain explicitly open in TODO.

## Historical status: failed user retest (2026-09-23)

The user reports that Tree View highlight tearing has not improved and remains
frequent during wheel scrolling. The test results below describe the attempted
fix, not successful user acceptance. They did not cover the remaining visual
failure adequately. Investigation is deferred until the usage allowance recovers;
the user explicitly requests reusing v0.18.6 when correcting it.

## Observed mechanism (not a complete diagnosis)

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

## Attempted repair

- A private bindtag runs after native Treeview wheel/key/pointer handling, before
  returning to the paint loop; it synchronizes the visible-row canvases directly.
- Scrollbar callbacks and Configure events use the same guarded redraw path,
  covering programmatic scrolling and floating-band layout changes too.
- Cancel redundant pending idle repairs. Do not call `update()` recursively,
  block Windows painting, alter wheel increments, or force periodic redraws.
- Full-size floating icons share the existing navigation images. Compressed deep
  ancestor bands still receive correctly sized independent images after zoom.

## Historical test results (2026-09-23; insufficient for acceptance)

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
