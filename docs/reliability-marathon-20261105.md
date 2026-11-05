# PFC 0.19.0 stabilization campaign — in progress

Owner-requested ten-hour campaign: 2026-11-05 17:49:24 to 2026-11-06 03:49:24
Asia/Singapore. Final-hour convergence begins 02:49:24. Trace:
`0561e5ba068c481eb5d08b0557da8c2a`. This is not a completion or release claim.

## Verified early findings / candidate changes

- Fault-injected failed cross-filesystem directory replacement could delete the
  only remaining copy of source children during rollback. Candidate retains a
  separate recovery copy before restoring the previous destination. Tests cover
  copy rollback, partially deleted source trees and failed recovery renames.
- At 800x600 / 300%, key-only actions could still run past the right edge.
  Candidate wraps only when even compact keys cannot fit. Extreme size/scale
  combinations may lack content space; tests distinguish recovery-only layouts
  and exercise the visible zoom control to restore a complete file row.
- Column sizing repeatedly fetched the same values, measured repeated strings,
  and rewrote all file labels. Candidate uses operation-local row/width caches,
  removes the legacy label rewrite and retains relative-path search labels.
  Exact width/hidden-column/font-scale and label checks cover semantics.
- Reopening Settings/Search leaked owned Tcl variable traces and retained old
  dialogs. A ten-cycle fixture grew from 1,567 to 1,936 Tcl commands; with explicit
  owned-variable and prefix-page cleanup it remained at 1,527 for every cycle.
  In a separate 32-cycle instrumented interaction run, final collected Python
  allocations fell from about 8.70 MB to 1.87 MB. These are fixture results, not
  a general application-memory guarantee.
- Immediate close after re-scaling Search/Preview left native Tcl idle callbacks
  targeting deleted commands. Candidate coalesces/cancels widget-owned idle work.
  Native Tcl background errors are now routed to automatic diagnostics with
  version/time and safe callback categories; document/message text is not logged.
- Child-widget Configure events no longer repeatedly reschedule main-window
  geometry saves. Root geometry and explicit requests retain their debounce.
- An uninstrumented x64 interaction run exposed a real Tk image-finalizer
  failure on a background thread. A deterministic worker-GC fixture reproduced
  retained Preview toolbar icons, Settings thumbnails and Preview variables.
  Explicit UI-thread cleanup passed source/portable and both Windows runtimes.
  A follow-up fixture also exposed four orphaned Settings named fonts; explicit
  owned-font cleanup passed the source/portable regression. Native endurance
  coverage of the newest combined candidate is still pending.
- Automatic diagnostics now also observe Python unraisable/finalizer failures,
  chain and restore the original hook, and retain safe exception frames plus
  version/time. No arbitrary finalizer object representation/message is logged.
  A known Tk thread-access error receives a safe explanatory reason.
- Endurance uses the existing leased Windows adapter with an explicit bounded
  duration, validated fixture arguments, progress watchdog and a task lifetime
  covering that duration. Default short-test limits remain unchanged. The matrix
  verifies hashes of selected checks/support files as well as the application;
  timing scopes include the requested duration. These are test-only extensions.

## Performance evidence boundaries

For an isolated 1,500-file fixture, sizing Treeview item calls changed from 6,000
to 1,500 with identical widths. ABBA stage medians were approximately 14 ms before
and 2 ms after. Actual window-resize frame medians in the same fixture were about
204–205 ms before and 185–188 ms after. Initial folder-navigation measurements
were noisy: no navigation speedup is established. The host was shared, so these
are measured observations rather than a universal percentage guarantee. Earlier
fixtures stored their INI beside data; the final comparison separates preferences
from the active folder to avoid configuration writes triggering folder refreshes.

## Display coverage boundaries

Win11-ARM64-VM currently enumerates only one head and 1920x1080 / 32bpp / 64Hz.
The inventory probe did not perform a real resolution transition. Other Windows
resolutions and physical multiple monitors are unavailable without separate VM
display/driver work. Actual Windows client resizing, monitor-work-area models,
negative origins/gaps/mixed monitor dimensions, application relaunch and Linux
Xvfb desktops at multiple resolutions are recorded separately. Neither ARM64 nor
Windows-emulated x64 Python establishes native-x64 Windows certification.

The long-lived source process, repeated source/portable regressions, seeded
file-integrity checks and dual-Python Windows batches must complete their recorded
scopes before final acceptance. Original failures are retained in the private
trace. Official token counters are unavailable; there is no comparable whole-task
baseline and no claimed token saving.
