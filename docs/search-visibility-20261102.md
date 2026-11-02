# F4 Search window recovery — v0.18.48

Run: `29eb0275fcda41ac98dad0ed66ed6d9e`.

## User tasks and diagnosis

1. Open F4 on a laptop after previously using an external monitor: title, query
   controls and results must be reachable on the current display without OS keys.
2. Keep Search open while its old monitor becomes unavailable: recover without
   losing results/selection or starting a new query.
3. Reopen/reuse Search or change UI font scale: fit the available work area,
   preserving ordinary user positioning and intentional minimize/maximize.

The owner's photograph reports an unreachable Search window. Source inspection
found that Search restored raw saved geometry without the main window's existing
visibility guard. The old v0.18.47 portable reproduces failure using synthetic
saved geometry `1800x1050+5000+120`. The corrected source passes the same flow.
This establishes an offscreen-recovery gap; the photograph alone does not prove
the laptop's exact saved geometry, DPI setting or native snap-key behavior.

## Implementation

Reuse `WindowVisibilityGuard` for Search, not a new global window manager.
Activation performs best-effort recovery immediately. Stable live observations
recover an unreachable title; changed monitor work areas also fit Search's full
frame, including the native title/borders and excluding the Windows taskbar.
Font-scale changes request a fit after layout. Failed display APIs are tolerated
during transitions; the timer remains available to retry later.

Full-frame fitting is specific to Search and occurs only on activation or a
changed monitor topology. Ordinary moves are not forced back. Main-window policy
is unchanged; connected negative-coordinate monitors and valid maximized resize
borders are preserved. Intentionally minimized windows are not reopened. No
search reset is performed by live recovery; existing close/reopen behavior and
saved corrected geometry remain intact.

## Validation

Pending final same-artifact Linux source/portable and leased Windows ARM64/x64
acceptance. New GUI tasks exercise saved offscreen/oversized geometry, live
recovery with 25 synthetic results and retained selection, reuse, 200% UI scale,
stable placement, close/reopen and native minimize/maximize. Pure tests cover
monitor work-area changes, negative monitors and transient API failure. Existing
main-window visibility and search/scaling regressions are included.

Windows tests move an actual native frame beyond the VM display; changing monitor
lists is additionally covered by deterministic unit fixtures. This is not a
physical laptop cable-unplug test or native-x64 Windows certification. Visual
captures use synthetic files only. Timing has no comparable overall-task baseline
and token counters are unavailable; no performance improvement is claimed.
