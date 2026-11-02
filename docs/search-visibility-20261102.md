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

Verified application candidate `e73ad0d`; portable SHA-256
`30c73806ce700bd81261a98f9d4782f4f7da42b057a8045ec9fc788102b46b3f`.
The subsequent laptop-size fixture commit `2fe5a03` changes tests only. Both
Windows profiles were rerun with that same fixture and unchanged application.

New GUI tasks exercise saved offscreen/oversized geometry, live
recovery with 25 synthetic results and retained selection, reuse, 200% UI scale,
stable placement, close/reopen and native minimize/maximize. Pure tests cover
monitor work-area changes, negative monitors and transient API failure. Existing
main-window visibility and search/scaling regressions are included.

Visual self-review of actual GDI captures from both final profiles: the restored
results view retained its selected row and 25 results. At 200% UI font scale the
native window fitted within a simulated 1280x680 laptop work area; query fields,
Search/Stop, action buttons, results viewport, scrollbars and bottom filter/status
line remained visible. Native frame bounds (including title) were also asserted,
not inferred from the client-area screenshot. No new recovery button or toolbar
was introduced: UI/UX review prioritized automatic recovery and an operable
results area rather than merely checking that the Toplevel existed.

- Linux clean-worktree search profile: all 13 groups passed in 127.258 seconds;
  unit suite 500 cases, nine platform-conditional skips. Main-window visibility
  source/portable checks also passed (10.516 / 10.568 seconds).
- Windows ARM64 Python 3.13.15 / Tk 8.6.15: request
  `d5dab785fc054591b7af0d982751ebae`; Search visibility, search results and control
  scaling passed. Visibility check 13.688 seconds; complete stage 158.189 seconds
  including environment and staging.
- Windows emulated-x64 Python 3.13.15 / Tk 8.6.15: request
  `97fa03290a2d41198a7420be571a91c5`; the same three checks passed. Visibility
  15.297 seconds; complete stage 167.725 seconds. Both artifact hashes matched,
  cleanup errors were empty, and the lease pool was empty afterward.
- The first dual-profile group also passed on the VM's real larger work area;
  final groups add the smaller-area native-frame test without changing the VM's
  shared display settings. Private evidence is retained under the run's
  `windows-evidence/` directory. Only synthetic files were searched.
- Early test assumptions about centered versus clamped placement and Search
  close destroying (not withdrawing) its window were corrected; original failed
  records remain in the trace. No acceptance failure is hidden or counted passed.

Windows tests move an actual native frame beyond the VM display; changing monitor
lists is additionally covered by deterministic unit fixtures. This is not a
physical laptop cable-unplug test or native-x64 Windows certification. Visual
captures use synthetic files only. Timing has no comparable overall-task baseline
and token counters are unavailable; no performance improvement is claimed.
