# PFC 0.19.0 stabilization: reliability and performance evidence

## Verified scopes and remaining acceptance gaps

Campaign window: **2026-11-05 17:49:24–2026-11-06 03:49:24 +08:00**.
Baseline: v0.18.49, `00f4bd98caf9c5bc5b808c2293ebda7913f1e6e8`.
Private workflow trace: `0561e5ba068c481eb5d08b0557da8c2a`.

The final application candidate is frozen at source commit
`759f7691c87643656c5e63cb457a639f3de7861a` (Space Analyzer timer correction);
later test/report-only commits do not
change its portable bytes. Portable SHA-256:
`807f174cbb1f4ace5801eebd51fc92e128ec2c49e584f8c2b91355db82bf258e`.

This is a stabilization milestone, **not a zero-known-issues or 1.0 claim**.
In particular, the Windows tooltip suite is still failing. Earlier crashes,
failed experiments and environmental skips are retained below and in the trace.

| Scope | Observed result | Candidate boundary |
| --- | --- | --- |
| Complete Linux suite | Final 162 runner entries passed in 719.6 s; unit inventory 530 total, 521 passed / 9 platform skips | Final 807 candidate, current test definitions; earlier F66 162-entry suite took 793.5 s, separately scoped |
| Windows focused regression | Final four core checks passed each; the corrected paired interaction/diagnostic control also passed each | Core ARM64 154.7 s / x64 167.3 s; paired 91.4 s / 95.8 s; cleanup lists empty. Initial whole batches remain failed, not relabelled |
| Windows final endurance | ARM64 accepted: 901.5 s / 451 cycles, 41 Space cycles; x64 requested long run blocked by `stale-result`, **not accepted** | Final portable; ARM maximum heartbeat gap 0.976 s. x64 partial log reaches 902.1 s / 418 cycles but its parent result remains running; that is not complete exit/cleanup acceptance |
| Final Windows revalidation / evidence | Paired 30-second requests passed, ARM64 35.8 s / x64 36.7 s worker time; both runtime identities and cleanup verified | Nonce/path/length/SHA-256 checked recovery preserved both original logs. This does not replace missing x64 long-run acceptance |
| Linux final long-lived processes | Passed: source 3,002.4 s / 1,172 cycles, portable 3,001.6 s / 1,171 cycles; 107 Space cycles each | Final candidate; maximum heartbeat gaps 1.860 / 1.846 s; wide Review completed 12/12 each. Earlier F66 100-minute processes are historical controls |
| Broad Windows functional matrix | 52 unique scripts accepted in each runtime, with environmental subcase skips; tooltip suite excluded and still failed | Earlier C14 portable `6e713b489926d2fcac7eab2b58f155e283c3fc2e65c503d7072406d38a6b9516`, **not** final F66 bytes |
| Linux desktop matrix | Final 807 eight cases passed in 260.6 s; earlier F66 eight cases took 244.3 s | Source/portable at 1280×720, 1366×768, 1920×1080 and 3840×2160; actual Xvfb desktops, not Windows display transitions |
| Seeded file-operation integrity | 57,600 scenarios passed in each form; hashes and untouched sentinel checked | Earlier campaign candidate; disposable fixtures, not user files |
| Publication and updater/mirror | Release-gate result recorded separately in the maintenance trace | Tag, updater bytes and private mirror must match; no publication acceptance inferred from this local report |

Runner-entry totals are not counts of fully exercised Windows scenarios:
platform-only scripts/subcases may explicitly skip on Linux. The 719.6 versus
793.5-second suite timings have different definitions/load and are not a test
performance improvement claim.

Windows checks use explicit, separate Python 3.13.15 runtimes with Tk 8.6.15:
ARM64 and Windows-emulated x64. Tests are sequential through the existing leased
Win11-ARM64-VM workflow, with artifact identity and cleanup verification. The VM
remains 8 GiB / six vCPUs, offline, with its existing idle-hibernation policy.
Application emulation is **not native x64 Windows acceptance**.

The broad matrix covers preview/render/search, compare/review, workbook and
archive workflows, file actions, menus/settings, overlays, lifecycle and display
models. It is explicitly bound to C14. Later tooltip lifetime and Space Analyzer
timer changes have separately scoped full Linux suites, focused Windows reruns
and endurance instead of relabelling older results as final-artifact tests.
The last correction is eleven application lines consuming pending Space Analyzer
timers before synchronous redraw/Locate. It triggered a new artifact and a fresh
dual-runtime run. Remaining campaign time is explicitly split into 15-minute
Windows and 50-minute Linux final-artifact runs; it is not relabelled as the
superseded 45/100-minute plan or a ten-hour run of one unchanged executable.
The initial final-space native batch also omitted `interaction_soak_check.py`,
which is an explicit companion of `soak_diagnostics_check.py`. Four core scripts
passed, but the negative control failed because its child script was not staged.
The failed batch is retained; a correct paired request must pass in both runtimes.
This was an operator batch-definition error, not a new product failure or grounds
to call the entire failed batch passed. The proposed 20-minute final duration
was reduced to 15 minutes to leave publication time under the ten-hour cap.
The first final-807 full Linux run passed all GUI scripts but failed one unit
double that omitted the newly required `after_cancel` method. The real-Tk and
Windows cases had passed. The double now models that method and asserts its
invocation; additional unit cases cover pending redraw consumption and an
already-expired click timer. The complete suite is rerun rather than excluding
the failing test. These test-only changes do not alter the final application.

Final ARM64 endurance returned exit 0 after 905 worker seconds, but the first
host log transfer was empty. Acceptance required recovering the original guest
log, not trusting exit status alone. A further leased matrix request used a
read-only transfer envelope with fresh nonce, requested path, byte count and
SHA-256. The recovered 15,779-byte ARM log matches the final candidate and its
900-second target/terminal event; the original empty host artifact is preserved.
The requested x64 long run was blocked by a mismatched result identifier; it is
not reclassified as a pass. Short paired reruns and recovered partial telemetry
cannot replace that missing long-run acceptance. The transfer workaround is
per-run validation tooling, **not a claimed permanent repair of the VM runner**.

## Prioritized findings and implemented defenses

| Priority / reproducibility | Finding | Change and regression evidence |
| --- | --- | --- |
| Critical / deterministic fault injection | Failed cross-filesystem replacement could delete the last surviving moved children during rollback | Preserve a distinct recovery copy before restoring the old destination; partial source deletion and failed recovery rename cases retain recoverable data |
| High / real endurance failures plus deterministic lifetime cases | Repeated dialog teardown left Tk resources and deferred callbacks alive, including off-thread image finalizers and deleted native commands | Explicit UI-thread resource disposal, owned/coalesced callbacks and data-only workers; forced worker GC, rapid close and reentrant teardown regressions |
| High / both Windows runtimes | Settings styles grew approximately two GDI handles per interaction cycle, failing the unchanged guard near cycle 296 | Reuse three root-owned named style fonts; earlier C6 90-minute runs passed both runtimes with GDI roughly 390–400; final-candidate acceptance is separately scoped |
| High / deterministic callback reentry | Tooltip replacement or an earlier event handler could retire a command still needed by the current Tk dispatch | Popup identity checks and immediate logical retirement of stale bindings; physical unbind deferred to an owned timer after dispatch, including nested idle regression |
| High / deterministic after an intermittent discovery | Space Analyzer synchronous redraw and direct Locate cleared pending timer tokens without cancelling their callbacks | Consume pending redraw/click timers before clearing tokens; forced schedule→manual redraw→close and click→Locate regressions fail before/pass after in both forms; final soak includes Space every eleven cycles |
| Medium / deterministic | Cancelled/stale Space Analyzer work could strand a replacement scan; final-child cancellation was swallowed as an unreadable item | Token identity, data-only worker and InterruptedError propagation; final-child cancellation and overlapping scan cases |
| Medium / deterministic | Reopened dialogs retained variable traces; repeated space context menus retained commands | Owned-variable teardown and reusable menu with old entry-command cleanup; before/after counts below |
| Medium / deterministic | Malformed startup preferences failed before diagnostics; failed saves lacked durable warnings | Install diagnostics before INI parsing; retain original bytes and record failed save once per session, with version/time and redaction checks |
| Medium / measured task delay | F4 queued thousands of redundant progress snapshots; selective masks still performed unnecessary stats | Coalesce live progress while preserving exact final counts; mask before file stat; measured same-input comparisons below |
| Medium / visual inspection | Disabled actions looked enabled; guidance named a different action | Disabled/pressed state maps and localized actual action label; final Windows light/dark screenshots inspected in both runtimes |
| Medium / deterministic boundary | Extreme scale clipped footer recovery actions; invalid comparison timestamps raised | Wrap key-only actions only when needed; retain visible zoom recovery; safe date fallback preserves byte sizes |

The architecture work deliberately avoids a wholesale rewrite. Shared ownership
primitives replace scattered timer/trace cleanup, workers no longer retain Tk
windows, sizing uses per-operation caches, and progress no longer queues obsolete
snapshots. Regression coverage protects relative-path labels, sorting, selection,
counts, cancellation and safe recovery behavior.

The surface-walkthrough assertion had an input-sensitive fixture defect, not a
product-search defect: the query `Project 29` searches the description/path too,
so a temporary parent containing `29` legitimately matches all 30 records.
Forcing that parent reproduced the source/portable assertion. The original
intermittent failure did not retain its random parent, so attribution of that
particular occurrence remains an inference. The fixture now
uses a unique single-token name, asserts the exact selected record, separately
requires all records to match their common path, and deliberately keeps `29` in
the temporary prefix. Both forms pass the controlled collision case. Application
code and the final portable bytes are unchanged by this test repair.

Visual inspection is separate from the scripted assertions. Earlier F66 Windows
light/dark Search captures show a distinct enabled Search action, muted Stop and
result actions, and the ready hint above the results. Final Linux 1260×650 at
200% retains a single bottom action row, zoom and complete file rows; detail
columns use local horizontal scrolling. At 800×600 / 300% the two action rows
and zoom remain reachable but file content does not fit until scale is reduced:
this is explicitly recovery-only, not a successful full reading layout.

Large controller modules remain a maintainability concern (`app.py` about
6,400 lines, `compare.py` about 2,800). Splitting them merely to reduce line
counts was deferred: no measured task benefit or sufficiently narrow behavior
boundary justified a broad late-release rewrite. The changes instead target
reproduced ownership defects and measured repeated work, with regression tests.

## Measured engineering value

These are isolated same-task comparisons on a shared Linux host, not universal
or Windows performance guarantees. Inputs and preferences were separated. ABBA
order and failed fixture experiments are retained; overlapping test durations
are not added together as campaign elapsed time.

| Workflow / input | Before | After | Correctness boundary |
| --- | --- | --- | --- |
| Column sizing, 1,500 file rows | 6,000 Treeview item reads; ~14 ms sizing | 1,500 reads; ~2 ms sizing | Identical widths and preserved relative-path labels |
| Actual resize, same file fixture | ~204–205 ms frame medians | ~185–188 ms | No demonstrated folder-navigation speedup |
| F4 selective mask, 50,000 files / 500 hits | 50,000 stats; 0.60–0.64 s completion | 500 stats; ~0.38 s | Same 500-result set |
| F4, 12,000 folders + 12,000 nonmatching files | ~12,001 progress messages; ~10,000 peak backlog; 2.06–2.09 s visible completion | ~5 messages / peak queue 2; 0.38–0.42 s | Worker remained ~0.37–0.39 s; exact final counts unchanged |
| Ten Settings/Search reopen cycles | Tcl commands 1,567→1,936 | 1,527 throughout the fixture | Owned traces removed; not a whole-application memory guarantee |
| Forty Space Analyzer context menus | 40 retained menus; commands 244→345 | One reusable menu | Old entry commands explicitly deleted |

A F66-artifact ABBA repeat under the later, heavier shared load retained all
1,500 rows and widths `[378, 48, 44, 136]`: v0.18.49 sizing medians were
14.91/15.03 ms versus final 4.01/4.15 ms; actual resize medians were
274.7/278.6 ms versus 260.1/258.6 ms. Treeview reads remained 6,000 versus 1,500.
A preceding parallel source/portable snapshot observed resize medians about
259/267 ms; it was not an isolated before/after comparison and is not used to
claim a speedup. F66 selective-search verification retained exactly 500 hits
and 500 file stats over 50,000 files; visible-completion median was about
0.351 s. These later observations do not erase the earlier timings or establish
a general folder-navigation improvement.

Separate instrumented Python-allocation experiments are not native-memory
benchmarks: an earlier 32-cycle fixture changed about 8.70→1.87 MB; a later
900-second source run recorded about 1.126→1.150 MB collected allocations over
320 cycles. Neither establishes a plateau for Windows process-private memory.
Official token counters are unavailable; no token-saving or comparable whole-task
speedup is claimed.

## Known failures and unverified scenarios

Historical source controls C6/C7/C9/C10/C11/C12/C13/C14 completed their own
unchanged snapshots: respectively 25,330 / 23,283 / 22,481 / 22,082 / 21,602 /
19,502 / 18,844 / 12,542 seconds, with 10,684 / 9,835 / 9,388 / 9,204 / 8,998 /
7,827 / 7,491 / 4,880 cycles. Their maximum heartbeat gaps were about 1.92–2.05 s.
These overlapping 3.5–7-hour controls are not summed into elapsed time and are
not final 807-artifact endurance. In particular, the old stage label
`source-long-lived-c4` was reused for a C6 retry; its later success does not erase
the original C4 crash or mean the crashed artifact passed seven hours.

- **Windows tooltip acceptance remains unresolved.** On earlier F66, ARM64 completed
  the core fixture sections but failed native-menu hover help. x64 failed earlier
  when Escape/re-hover left no popup for the fixture to enter. These are actual
  failed checks, not passes or waived coverage. The owner-local tooltip fixture
  was preserved without publication; committed Linux fixture results do not
  replace it. Native HMENU visibility/containing-widget behavior differs from Tk
  widget menus. Focus/ghost-popup protections were not relaxed to force a pass.
  The final Space-only correction does not establish full tooltip acceptance;
  the earlier failed checks are not presented as final-artifact passes.
- **Earlier native crashes are evidence, not erased history.** Two intermediate
  Linux candidates crashed in Tk teardown after ~1,271 / ~1,324 seconds despite
  short-suite success. Both were recovered by automatic crash diagnostics with
  version, system time and sanitized frames. Later lifetime guards address
  reproduced defects; the precise native corruption root cause is not proven.
  The previously reported intermittent Windows Compare access violation also
  remains without a confirmed root cause. Crash capture alone is not a fix.
- **Windows private-memory trend remains unresolved.** Earlier C6 90-minute
  runs held GDI/font/image/command counts bounded, but warmed private-memory
  medians rose roughly 65→100 MiB (ARM64) and 80→115 MiB (x64). This is not a
  proven plateau or a proven Python leak; no guardrail was raised to hide it.
- **Cross-machine wall clocks are not aligned.** In both final paired runtime
  requests, the guest's timezone-aware start timestamp was about six hours ahead
  of the host-estimated test start (within a few seconds of setup overhead).
  The cause was not diagnosed and the guest clock was not changed during testing.
  Durations use monotonic clocks; do not subtract guest/host wall timestamps to
  infer latency or mistake this VM observation for a PFC timestamp-format bug.
- **Physical display coverage is unavailable.** The VM enumerates only one
  1920×1080 head. Windows client resizing/relaunch and modeled work areas,
  negative origins, gaps and mixed dimensions were tested separately from real
  Linux desktop sizes. No physical hotplug, native Windows resolution change,
  mixed-DPI multihead or native-x64 hardware acceptance is claimed.
- **Windows filesystem boundary cases skipped:** both runtimes lacked symbolic
  link privilege and a second physical filesystem. Linux real symlink and
  cross-device fixtures passed separately. No privilege/disk changes were made
  to conceal the gap. Offline overlay fixtures are not signed-in OneDrive
  provider-transition acceptance.
- **Soak scope is rapid interaction/cancellation.** It cycles settings, search,
  previews and comparisons and records wide Review completion. Cold Windows
  render workers often do not finish before rapid closure; semantic rendering
  success comes from the independent completion-waiting functional checks, not
  from claiming every soak cycle rendered fully.
- **A rejected tooltip defense is not shipped.** An extra post-show eligibility
  check appeared harmless in Linux but prevented valid hover help in both Windows
  profiles. It was removed; final code keeps popup identity and binding-lifetime
  guards. Earlier two-hour source/portable passes of that rejected candidate do
  not establish Windows usability or override the failing native hover checks.
- **800×600 at 300% is recovery-only.** Visible minus/zoom recovery is required;
  a zero-height content area is not counted as a usable full layout.

Reproduce the complete Linux suite with
`python3 tools/pfc_workflow.py test --run RUN_ID --profile full --jobs 4` after
starting the required maintenance trace. Native checks must use the project's
leased dual-runtime matrix, not ad-hoc desktop input. Private evidence remains
in the maintenance trace; no user document contents, raw cores or credentials
are published here.

<details>
<summary>Investigation diary — historical checkpoints, not current acceptance</summary>

The following notes were written during exploration. Their pending wording
describes that checkpoint; the acceptance snapshot above is authoritative for
current scope. Failed candidates and hypotheses remain visible.

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

A second bottleneck appeared in folder-heavy F4 searches with few/no matches.
For the same 12,000 folders and 12,000 nonmatching files, the worker took about
0.38 seconds, but one progress message per folder delayed visible completion to
2.08 seconds and accumulated roughly 10,000 queued snapshots. Coalescing progress
to live 100-ms snapshots plus an exact final count reduced measured completion
to 0.38 seconds, with about five progress messages and a peak queue of two.
An independent ABBA run without queue-count instrumentation confirmed completion
medians of 2.06–2.09 seconds before and 0.38–0.42 seconds after; worker medians
remained about 0.37–0.39 seconds. This is UI backlog removal, not a claim of faster
disk scanning or a native-Windows performance percentage. Inputs/preferences
were isolated; host load remained shared. Item/error/done messages are unchanged.
Regression coverage verifies exact final/cancelled folder counts, live updates
on slow scans, 2,999 retained matches plus one unreadable item, and visible
zero-result completion on a real 3,001-folder GUI fixture.

For a separate actual F4 search of 50,000 fixed files (500 name-mask hits), ABBA
completion medians were 0.60–0.64 seconds before and about 0.38 seconds after
checking the name mask before stat. Result sets stayed identical; file-stat calls
fell from 50,000 to 500. This is selective-mask evidence on Linux with shared
host load, not a general filesystem/Windows speed guarantee.

## Failures found by endurance, not covered by short-suite success

The first C4 source/portable suite passed 143 checks, but its separate source
long-lived process crashed after 1,270.8 seconds / roughly 592 cycles. The
automatic native-crash mechanism recovered the real SIGSEGV with version/time
and a sanitized Python stack. Core inspection locates Tk 8.6.14's pack-manager
unlink path during Settings preview destruction. The precise application-level
cause remains under investigation; teardown guards are a candidate defense,
not yet a claim that the native crash is fixed.

C4 Windows ARM64 and x64 endurance attempts both stopped near cycle 296 on the
same resource-growth guardrail: approximately two native GDI handles added per
cycle, exceeding a warmed baseline by 528 handles. Stage attribution showed
Settings reopen/close caused growth, while settled Preview/Search added none.
The next candidate reuses root-owned Settings style-font names, keeping them
valid for Ttk/readable-choice caches. Initial ARM64 stage tests are bounded;
x64 and renewed hour-long checks remain required. Guardrails were not raised.

Further regressions cover closed file-tab/Compare resource disposal, cancelled
Search workers retaining no Tk window, stale disk-space scans not stranding a
new scan, partial Search construction cleanup, real cross-filesystem movement
on Linux, and link-safe deletion of disposable fixtures. Full relevant suites,
dual-runtime validation and final release acceptance are still in progress.

A second pre-guard source probe failed after 1,323.8 seconds / over 624 cycles:
dead Search buttons were referenced by deferred toolbar sizing, followed by a
native Ttk font/world-change crash inside recursive Search activation idle
processing. This real crash was also recovered automatically with version/time.
The next source candidate closes toolbars before destroying children, consumes
pending callbacks on manual reflow, excludes deleted groups, and defers Settings
focus and Search activation work instead of recursively pumping Tk. Focus during
sibling teardown and toolbar lifetime regressions fail before/pass after. These
remain pending long-run and dual-runtime final-candidate acceptance.

Another deterministic exploration found three Space Analyzer defects: 40 context
menu openings retained 40 menus and grew Tcl commands from 244 to 345; scaling
then immediately closing left an invalid native callback; cancellation inside
the final child subtree was swallowed as an unreadable item. Local fixes reuse
one menu while deleting old entry commands, own/coalesce the scale callback, and
propagate InterruptedError before the best-effort OSError handler. Before-failing
regressions now pass in source; combined/portable/native acceptance is pending.

One hundred deterministic operation seeds passed separately in source and
portable form (57,600 operation scenarios per form), with byte hashes and an
untouched sentinel inside disposable roots. This is file-operation correctness
coverage, not a performance comparison or substitute for GUI endurance.

Extending immediate-close coverage from Markdown to static visual rendering and
nested folder-comparison tabs exposed additional orphaned raster/focus callbacks.
The pending focus now belongs to the actual target widget, so closing a detail
tab cancels it even while the comparison container remains open. Initial image
drawing uses the same owned-idle lifetime primitive. The new before-failing
regression is part of the existing early-close check in source/portable forms.

Startup diagnostics previously began after INI parsing, so malformed preference
files could abort before the automatic hook was installed. Diagnostics now start
before reading preferences; the original file is neither reset nor overwritten.
A failed atomic settings save now records one Warning per session instead of
only showing a temporary banner. Regression checks use a real failing child
startup and injected save denial, verify version/time and redaction, and preserve
the configuration bytes measured immediately before the failure.

Folder comparison also reused the file list's safe modified-date formatting:
non-finite or out-of-range timestamps previously raised from the UI formatter.
Before-failing boundary tests now preserve known byte sizes with an unavailable
date marker, while ordinary date formatting is unchanged. The native comparison
fixture attempts a real year-10000 timestamp only inside its disposable root and
explicitly distinguishes filesystem support/clamping from injected metadata.

The first complete C11 suite failed one obsolete smoke assertion that hardcoded
the last release-history group as v0.18.x. The actual Help menu correctly included
v0.19.x. The check now verifies grouping/order against history, requires the
current series first and preserves all legacy groups; the focused smoke rerun
passes. This was a test expectation repair, not a GUI menu defect.

Endurance additionally rotates real Text/Folder Compare opens/closes and rapid
nested-detail closure. Native GDI attribution includes comparison cycles as well
as Settings/Preview/Search. A real injected Tcl background error verifies that
the existing automatic diagnostics and endurance observer reject it; the
suspected observation gap was not reproduced, so no logging-hook change was
needed. The negative control uses its own temporary diagnostic directory.
The final endurance definition also periodically loads a multi-megabyte,
wide-line Markdown Review pair and records whether it completed before closure;
the native GDI fixture repeats Text, Folder and large Review in every cycle.
This is additional test coverage, not another application-code change.

Direct inspection of the final Windows screenshots found another usability gap
despite passing functional checks: disabled buttons looked enabled, and the ready
hint named Find while the visible action was Search. The global button map had
overridden the theme's disabled foreground and put hover before pressed state.
The next candidate restores distinct disabled text/background and prioritizes
disabled/pressed over hover in both themes. Search hints interpolate the actual
localized action label. A real-Tk regression fails before/pass after and covers
inherited Workflow/Compare styles; translation tests cover all four languages.
The earlier native batch was explicitly interrupted, with confirmed cleanup;
its partial passes are retained, not accepted as complete final verification.

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

</details>
