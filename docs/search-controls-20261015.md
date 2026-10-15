# F4 Search controls — v0.18.30

User task: enter folder/name/content/size/date criteria without opening a hidden
filter panel, observe running versus terminal states, then act on results without
finding a separate menu. Layout follows the owner's supplied four-row sketch.

## Layout and behavior

- Folder + depth; filename + Files/Folders + right-aligned Search; content +
  case sensitivity + right-aligned Stop; size range + kB/MB/GB + modified days.
- Size and date criteria are always visible. Size defaults to kB, using binary
  factors consistent with the pre-existing size filter (1024 bytes per kB).
- Progress/status and elapsed/scanned/unreadable counts remain above results.
  Traversal has no known total in advance, so running activity is indeterminate,
  not a fabricated percentage. Cancel/limit/unreadable/failure are not “complete”.
- Six visible result actions distribute across the available width; large fonts
  and narrow windows wrap actions without shrinking the selected font. No matches
  or no selection disables actions that cannot run. Compare needs two selections.
- Right-click a result to select it; clicking inside a multi-selection preserves
  the selection. Headers/blank space do not operate on a stale selected item.
  Shift+F10 opens the same menu for the focused result.
- F2 renames one selected result after confirmation through an input dialog.
  It reuses existing rename validation/rollback and never overwrites a collision.
  Folder renames retarget listed descendants. Renaming is disabled while scanning
  to prevent queued worker paths referring to the old folder name.
- F3 previews, F9 compares, F11 copies paths. Double-click still locates/closes
  Search; Go to File/Enter still keep Search open. No new automatic file actions.
  Search-specific keys stop event propagation, preventing the main file list's
  global shortcuts from also running behind Search.

## Review and verification

Developer review, not independent user acceptance. Isolated fixtures cover real
hidden/system traversal, units/invalid numbers, result menu selection, keyboard
menu access, rename cancellation/collision/folder descendants, navigation and
window lifetime. Existing UX checks cover running/empty/cancelled/failed/partial
states, 100/175/200% fonts, English/Traditional/Simplified Chinese and narrow views.

Before evidence is retained in the v0.18.29 private workflow captures. After
captures are retained in the current trace and `/tmp/pfc-search-*.png` /
`/tmp/pfc-ux-search-*.png`. A narrow-view review found the original translated
send-list label too long; delivery requires the shortened label to remain fully
readable. Technical containment alone is not accepted as readable labeling.

Maintenance trace: `2ab9f97c7e114921830b3a97da77f0b5`.
Final results must be recorded from this trace, not inferred from the design.
Windows coverage requires both ARM64 and Windows-emulated x64 Python 3.13.15/Tk
against the same candidate; neither establishes native x64 Windows acceptance.
No guest networking or live cloud data is needed for these checks.

## Windows evidence

- Final portable SHA256:
  `c2e932f1b45173aafd5b815c7b1a16a7a6570b093adadb9e718fc75d11031908`.
- Python 3.13.15 ARM64: Search results, UX walkthrough and control scaling passed
  in 5.855 / 12.879 / 26.763 seconds (45.497 seconds check execution only).
  Request: `8243b3efdcbc4cc781ebe84602d29a6c`.
- Python 3.13.15 Windows-emulated x64: the same checks passed in
  7.484 / 15.305 / 30.624 seconds (53.413 seconds check execution only).
  Request: `cf79161fcda548cd85751a4d5c8ecd02`.
- Both reports match the final hash and confirm cleanup; no guest networking.
  Native screenshots were inspected at 200% and narrow 175%: Search/Stop remain
  beside criteria, activity stays above results, and action labels fit fully.
- An earlier native run exposed a real layout defect: equal-width columns were
  selected using the sum of unequal button widths. The layout now checks the
  widest requested width against each candidate column count (6/3/2/1).
  That failed run and an interrupted earlier candidate remain in the trace;
  only the final matched passes above are Windows acceptance for this release.

Whole-task time includes analysis, cancelled outdated candidates, staging and
waiting. These check timings are not whole-task speedups. Token counters are
unavailable and no comparable whole-task baseline is established.

Final full inventory passed: 404 unit tests completed (9 platform skips) and
all 98 GUI checks across source/portable routes (99 runner checks). Prior
incomplete full runs were stopped before changing candidates and are not
counted as complete verification. The Windows acceptance above uses the same
final artifact, not an earlier passing candidate.
