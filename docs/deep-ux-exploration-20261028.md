# Deep PFC product exploration — 2026-10-28

Run: `8184856fa7a345b88d8023bc3057540c`. Baseline: local v0.18.44 candidate
`6e656fc`; earlier compact-layout tests are **not** exhaustive product acceptance.
Initially the Windows VM was held for a separate maintenance conversation.
On 2026-10-28 the owner reported it repaired; leased dual-runtime PFC acceptance
has resumed. This task does not take over VM repair or lifecycle experiments.

Historical verification completed on 2026-10-29: code commit `a590c0e`, unpublished
v0.18.45 candidate. The final full suite and both Windows runtime matrices pass.
**Publication remains held pending the owner's risk decision**: one earlier x64
native Compare access violation remains unexplained; later passes do not prove
it fixed. At that checkpoint no GitHub/GitLab update or version tag was pushed.
**Subsequent owner decision:** publish after adding and validating automatic
native-crash capture for photographic reporting. The follow-up and its final
artifact/test evidence are recorded in
[native crash diagnostics](native-crash-diagnostics-20261029.md). This supersedes
the publication hold below, not the unresolved root cause or historical results.

## User tasks, not just widget bounds

1. Find a file in a busy project, inspect several formats, compare revisions,
   locate the source and return without losing tabs, focus, filter or selection.
2. Organize files safely: copy/move with conflicts, rename and undo, cancel when
   appropriate, understand partial failures and recover without implicit writes.
3. Change layout/reading preferences, work with unavailable folders or invalid
   input, and use the keyboard to complete or safely dismiss every kind of popup.

## Surface inventory and exploration contract

| Surface | Important states / actions | Evidence needed |
|---|---|---|
| Main panes / 1–4 panels | empty, many files, hidden, mixed types, sorting, filter, external changes | metadata reads, latency, content/selection correctness |
| Path bar / root folder tree | deep Unicode paths, unavailable paths, return, file location, locked tabs | path/history consistency, no execution on location |
| Tabs / workspaces | grouping, locking, switching, restore, missing saved path | complete state transitions and rollback |
| F3 document tabs | MD, JSON-family, CSV, notebook, HTML, SVG, patch, text | search/reveal/wrap/close/reopen and cancellation |
| F4 | real results, zero, partial, limit, canceled, failed, missing file | visible truthful state, bounded UI poll, no redundant UI disk I/O |
| Compare | text, folders, archives, workbook, nested tabs, review drafts | search scope, side identity, save/cancel semantics |
| Settings | all categories, Apply/Cancel, draft isolation, combinations | font/layout/language/theme consistency and focus |
| Conflicts / confirmations | long paths, all choices, focus, Enter/Escape, nested modal | safe default and chosen action, bounded work area |
| Text/numeric prompts | long label, invalid input, canceled input, nested modal | scaled readable controls and exact return types |
| Rename | invalid counters, paste, rapid edits, unchanged, collisions, undo | no fallback writes, coalesced preview, cleanup |
| Saved workflow picker / command palette | many/empty entries, find, keyboard, long context | discoverability, filtering identity, focus restoration |
| Operation progress / result | slow work, many updates, failures/skips, retry | UI heartbeat, bounded drain, recoverable full details |
| Space analyzer | scanning, cancel, empty, drill-down, locate | busy visibility and correct scope |
| Diagnostics / Help / versions | empty, many incidents, photo summary, clear/cancel | version/time, scrolling and scale |
| Prefix / Markdown workspace | long boundaries, modes, invalid scope, canceled scan | explicit scope, no unrequested indexing |
| Menus / context menus | blank, file, folder, multiple, archive, disabled | action availability and keyboard routing |

This inventory is a checklist, not a claim that every row has passed. The report
must distinguish new exploration from existing regression, real fixture I/O from
injected failure/latency, source from portable, and Linux from Windows.

Configuration exploration uses explicit representative combinations and targeted
state transitions, not a claim that all combinations were exhaustively tested.
Large fonts must stay readable; narrow toolbars wrap at semantic boundaries.
Essential status and destructive consequences remain visible. No wholesale GUI
framework migration, new dependency or cosmetic-only redesign is planned.

## Initial hypotheses to reproduce

- Repeated metadata calls in navigation, sorting, signatures and search delivery
  inflate work, especially on slow storage. Measure end-to-end phases and counts
  before changing code; compare the same fixtures and isolated state afterward.
- Missing or inaccessible child metadata can mix numeric/string sort keys.
- Folder navigation may commit path/history even if listing fails, and failed
  refresh may discard the previous list before it knows a replacement is valid.
- Quick filtering rereads the directory for every keystroke.
- Confirmation Enter handling may ignore the focused Cancel button.
- Fixed conflict and input dialogs may exceed the work area at large scale.
- Invalid rename counters may silently fall back to defaults; rapid edits may
  schedule duplicate previews and leave callbacks behind when closed.
- Saved workflow selection lacks direct filtering; long context relies on hover.

Results, failed experiments, implemented scope and unresolved areas will be
recorded below. Passing the old suite alone does not close this exploration.

## Reproduced findings, in priority order

| Severity / reproduction | Finding | Candidate correction |
|---|---|---|
| High / focused Cancel + Enter, deterministic | Confirmation accepted the default instead of the focused button | Invoke the focused choice; conflicts initially focus Cancel |
| Medium / real Tab/Shift+Tab, deterministic | Generic modal key guards swallowed focus traversal, including readonly details | Share a focus-traversal guard, retain main-shortcut isolation and test six dialog types |
| Medium / switch MD tabs during a background stat probe | Returning to the tab reloaded unchanged content and lost folds | Quietly cancel only the probe; keep the loaded model/folds and resume future automatic probes |
| High / send mixed-folder results to a tab, then sort/filter | Result tab silently became the originating folder's contents | Retain explicit result paths through sort, filter and refresh |
| High / injected directory read denial | Navigation changed path/history before reading succeeded; refresh discarded existing rows | Preflight listing before state mutation; retain the previous list on failure |
| Medium / slow copy, deterministic | General copy/move blocked Tk and repaint | Worker I/O, UI-thread conflict replies, synchronous result via Tk wait_window |
| Medium / broken child symlink, Linux fixture | Numeric sorting mixed a string fallback with numeric keys | Single typed listing snapshot, numeric unavailable key, unavailable count |
| Medium / 300% reading scale | Result contents pushed recovery buttons outside the window | Reserve actions before expanding content; selectable failure list and scrollable full detail |
| Medium / invalid rename counter | Invalid input silently fell back to a different rename plan | Inline range error, disabled Apply, no fallback write |
| Medium / closing panes and repeatedly opening roots | Pending timers retained deleted Tcl commands | Cancel owned pane/rename jobs and root Tcl timers without double-deleting child commands |
| Medium / heavy progress reporting | Every intermediate update was queued and redrawn | O(1) latest-progress slot; terminal result remains separate; actual rather than animated progress for ETA |
| Usability / saved entries and long context | Manual list search, hover-only full context, lost nested modal ownership | Direct filtering, keyboard selection, accessible Details and restored focus/grab |

New `deep_tasks_check.py` currently has 33 behavioral cases, in source and portable form.
It includes actual fixture file I/O, explicit injected permission failures and
slow I/O, conflict choices, cancellation boundaries, typed input validation,
result retry identity, watcher/filter freshness and a 100,000-update burst.
Injected failures are not evidence of a real storage outage.

General transfer cancellation is **between selected items**. A selected folder
is one item, including its contents: the current copy/move must finish safely
before stopping. The UI states this limitation. No byte-level percentage or ETA
is invented. Root close cannot abandon an active transfer or progress operation.
Existing transactional replacement and archive/compare safety rules remain.

Additional reliability exploration after the first complete passing suite:

- A resolver exception had looked like voluntary Cancel. General transfer and
  comparison Safe Sync now share UI-thread conflict/error handling: the failed
  item is a failure, not simultaneously a skipped item, and remaining items are
  left unchanged. Both paths have regression coverage.
- Unexpected worker/result-shape failures always publish a terminal result so
  the modal progress window cannot be stranded. Genuine cancellation is not
  logged as a fault.
- Handled operation failures now emit an automatic ERROR with operation/counts
  and a photo-friendly reason, without raw filenames, paths or error text.
  Resolver/worker exceptions retain the existing sanitized frame/errno capture.
- A directory read outage during watcher refresh shows a retained-list warning,
  logs the same outage once, and clears the warning when access returns even if
  the directory contents are unchanged. Cached filter/sort/font redraws cannot
  clear that warning or manufacture a recovery without a fresh successful read.
  Explicit navigation errors are logged.
- Root destruction closes its diagnostic hooks/handlers. VCS workers capture
  their result queue rather than retaining FilePane/Tk ownership. A repeated-root
  portable stress run emitted a Tk Variable finalizer warning; the harness now
  also collects retired interpreters on their owning thread. The warning recurred
  in later stress runs, so the earlier clean runs did not establish full recovery.
  An isolated closure probe independently confirmed folder-navigation workers
  still captured their Tk owner. Navigation/hint and transfer/Safe Sync workers
  now capture data, queues, cancellation events and semaphores instead of their
  widget owner. A recursive closure regression passed for source and portable.
  A later one-off creation/finalization trace identified the remaining warning:
  TransferProgress's destination StringVar was collected by the following Safe
  Sync worker after its modal had closed. Destroy now drops the owned variable
  explicitly on Tk's thread; a weak-reference assertion checks immediate release
  without waiting for GC. This is not a blanket claim about all worker lifecycles.
- A later weak-reference probe found CommandPalette, WorkflowPicker and
  MultiRenameWindow still alive after destroy and UI-thread GC. Removing only
  their owned variable traces released all three, isolating the retention cause.
  An explicit-name cleanup helper now removes owned traces/variables; it never
  sweeps shared preferences. Repeated-open/close source/portable regressions pass.
- Common confirmation choices are localized, readonly details can be reached
  and scrolled by keyboard, and confirmation minimum width preserves its actions.
- Command search measures shortcut/category columns at the actual font size,
  hides the secondary category only when necessary and supplies local horizontal
  scrolling when minimum readable widths cannot fit. Selection/query are retained.

The existing default Checkbutton/Radiobutton style already covers controls
created after a scale change (`settings.refresh_control_styles`); no competing
indicator system was added to the new dialogs.

A final isolated POSIX special-file probe confirmed that plain Preview reached
the normal blocking-open branch for a FIFO. The probe intercepted that call
rather than hanging the application or reading a device. Plain, unlinked Markdown
and structured preview readers now share `regular_preview_stream`: reject
non-ordinary metadata before opening, use nonblocking POSIX open, and verify the
opened descriptor to reject a regular-file → FIFO replacement race. Directory
preview and ordinary symlinks remain supported; linked Markdown retains its
additional boundary guard. Five new unit cases cover regular Unicode data,
descriptor cleanup, pre-open refusal, replacement and ordinary symlink access;
the GUI case checks that a real isolated FIFO returns a visible failure promptly.
POSIX cases do not certify Windows named-pipe/driver behavior.

The final boundary probe also reproduced a cross-folder search-result failure:
two identical basenames, one missing, caused tuple comparison of None and numeric
metadata in the listing signature. Signatures now retain full paths and sort
only by identity; unit and real GUI fixtures cover a disappearing duplicate.

## Measured engineering value

Same generated 2,000-file local fixture, three repetitions per task, one warmup,
same query and result assertions. The final comparison disables periodic refresh
in both versions so it cannot randomly enter a timed foreground task. Listing
and rendering/settle or search poll phases are recorded separately. The baseline
is a clean export of `6e656fc`, not the dirty worktree. This controls our test
processes, not all host background load; it is not a network-drive benchmark.
Input is 12,000 content bytes in 2,000 tiny files; refresh/search deliver 2,000
rows and the quick-filter query delivers 101. Search is filename-only metadata
delivery, not a benchmark of reading large file contents.

The initial timing experiment also instrumented every Path.stat call. Its
wrapper adds per-call overhead, so these latency differences must not be treated
as uninstrumented speedups. The separate final raw experiment below bypasses only
the test's stat wrapper, keeping real filesystem calls and result assertions.

| Instrumented user task | Before median | Candidate median | Observed change |
|---|---:|---:|---:|
| Refresh and settle 2,000 rows | 85.96 ms | 58.28 ms | −32.2% |
| Apply quick filter and settle | 28.57 ms | 16.96 ms | −40.7% |
| Search and deliver all 2,000 results | 563.97 ms | 536.52 ms | −4.9%; small, not a general speed claim |

Earlier lower-load portable raw timings (no concurrent tests from this task; host background
load is not controlled), same fixture and three trials. These final numbers
include the duplicate-result signature correction:

| User task | Before median | Final candidate median | Observed change |
|---|---:|---:|---:|
| Refresh and settle 2,000 rows | 70.50 ms | 57.28 ms | −18.7% |
| Apply quick filter and settle | 24.78 ms | 18.62 ms | −24.8% |
| Search and deliver all 2,000 results | 563.07 ms | 536.07 ms | −4.8%; no meaningful general speed claim |

Private trace logs: `b4312fdba29b445bb7f469a26f05cbf7.log` (before),
`225b947d7bfc4623b26cafd46c10ca99.log` (after). Raw runs do not collect
metadata counts; their unused zero count fields are **not** zero actual I/O.
Host one-minute load averages were 2.50 and 3.00 respectively. One sequential
comparison is evidence for this fixture, not a broad platform/storage guarantee.

Final-artifact high-load repeat (same 2,000-file fixture, three trials, still no
concurrent tests from this task) was mixed: refresh 81.85 → 76.36 ms (−6.7%),
filter 32.59 → 34.18 ms (**+4.9% slower**), search 698.47 → 660.80 ms (−5.4%).
One-minute host load was 6.20 / 4.51. Logs `8f5fe588e35145739cceea3d44326cc9.log`
and `d5cde6f436df42b38e989a13b7bbe169.log` retain these results. The lower-load
filter improvement is therefore **not a verified universal speedup**. Reduced
metadata reads and retained-list correctness are independently tested; latency
claims must keep the shared-host variation rather than choosing a favorable run.

After final correctness tests and VM cleanup, one predeclared **ABBA** repeat
used the exact final artifact: baseline A1 → candidate B1 → candidate B2 →
baseline A2, three raw trials per process, all six trials per version included.
Host one-minute load stayed between 1.64 and 1.91; no other tests from this task
were running. This controls task/data/order, not all activity on the shared host.

| Final ABBA task | Baseline median (6 trials) | Candidate median (6 trials) | Change |
|---|---:|---:|---:|
| Refresh and settle 2,000 rows | 67.03 ms | 55.36 ms | −17.4% |
| Filter and settle 101 matching rows | 25.72 ms | 18.82 ms | −26.8% |
| Search and deliver 2,000 rows | 568.49 ms | 547.23 ms | −3.7%; not a general speed claim |

Logs, in execution order: `de0478fcd35e48b180c88cae371b555d.log`,
`8b8912d67b6245ffa115b4c5c26f0b78.log`, `107ec01854594225912e1dddb29ced87.log`,
`0734419bbb4e404bb0cb2623a10ad8db.log`. The slower high-load filter result above
is retained; ABBA results do not erase it or certify network/cloud storage speed.

Refresh Path.stat calls: 12,000 → 2,000. Quick filter: 2,505 → 0.
Search fixture child stat calls: UI 6,000 → 0, worker about 10,000 → 2,000.
These count Path.stat calls, not all Windows attribute/cloud/shell API calls.
Snapshots are per-listing, not an indefinite disk cache; normal refresh/watch
paths obtain new metadata, and explicit result tabs retain their original scope.

A separate font-change probe (four panes, 1,000 files each, 100% → 150%, three
raw timing trials and one separate metadata-count pass) reduced child stat calls
from 4,000 to zero. Local median latency was 693.0 → 708.7 ms: **no measured
task-level speedup**. Retain the result rather than claiming that fewer calls
alone prove a faster interface. No network-drive benefit is certified.
Its before artifact is the earlier v0.18.45 listing-snapshot candidate
`5a2256c…`, before the presentation-only cache correction, not the v0.18.44
baseline used in the directory task table.

The slow-copy experiment copies five real 64 KiB fixture files with an explicitly
simulated 120 ms delay per selected item. Final repeat: before 0.604 s, zero UI
timer ticks, 604 ms maximum dispatch gap; candidate 0.613 s, 30 ticks, 20.9 ms
maximum gap. Trace logs: `818aeec1367f4876b411fa6a31424d8c.log` and
`cc151f19b76947209af88874b097c2ed.log`.
Bytes and OperationResult are checked. This demonstrates responsiveness, **not
faster disk transfer**; the small polling overhead is retained for usable input.

Earlier periodic-refresh-on measurements, shared-load observations, a failed
search-harness activation and the first invalid theme-variable probe remain in
the trace. They are not substituted for this controlled comparison. Actual
subscription token counters are unavailable: usage and savings remain unknown.

## Broader configuration and visual exploration

`surface_walkthrough_check.py` visits all six Settings categories for each of:

| Scale | Width | Language | Theme | Panels |
|---|---:|---|---|---:|
| 100% | 1500 | English | Light | 2 |
| 150% | 1280 | Traditional Chinese | Dark | 1 |
| 200% | 760 | English | Light | 2 |
| 300% | 900 | Simplified Chinese | Dark | 1 |
| 150% | 1500 | Korean | Light | 4 |
| 125% | 1000 | English | Dark | 3 |

It also exercises long Unicode paths, confirmations, conflicts, valid/invalid
typed prompts, 30 saved entries, failure/retry details, transfer cancellation,
empty command search and the diagnostics surface. These are representative
combinations, **not exhaustive pairwise coverage or an independent user study**.
The manual 1600×1000 Xvfb run preserves the wide cases; the default headless
inventory also runs source/portable checks on its normal display.

Actual-size synthetic-data images were inspected: the old operation report
duplicated its summary, had a mismatched light text area in dark mode and no
scrollbar. The candidate makes failures scannable and puts the selected full
path/reason in a matching, scrollable reading area. Saved workflows now expose
Find and Details without adding a second title row. Conflict paths remain
selectable and scrollable, while Cancel has the initial focus. Essential
consequences and active-operation status remain visible, not hover-only.
Natural-size Linux examples and the operation-report before/after pair are
retained in the run's private `ui-evidence/` directory; final Windows evidence
is under `windows-evidence/<request-id>/`. Only isolated synthetic fixtures are
shown. These captures are self-review, not independent user acceptance.
The Preview-tab diagnostics screenshot intentionally injects a known geometry
exception to verify the photo summary/incident grouping at 200% scale. Its ERROR
row is expected fixture output, not a newly observed production exception.

The broader walk-through itself exposed two candidate layout defects: toolbar
padding was omitted from its height budget, and at 300% the result body could
consume its action footer. Both were corrected and the walk-through rerun.
Prior failures remain in the trace rather than being erased.

Windows ARM64 GDI captures of the six new task surfaces were inspected at actual
size: full conflict paths and recovery detail remain scrollable, localized Cancel
and retry actions are visible, and the saved-workflow picker exposes Find/Details.
Some bounds-test windows are deliberately resized tall; they do not represent
the natural default. Separate Linux natural-size captures confirm the ordinary
transfer popup is compact rather than the 650-pixel-high stress fixture.

The final regression also exposed a test synchronization race in folder-leaf
cancellation: a nonempty cancellation handle could belong to an already-finished
probe awaiting result delivery. The fixture now waits for an explicit blocked
worker event before testing cancellation. All original assertions remain; five
source and five portable repetitions passed. Another new outage test originally
expected name order after explicitly selecting size order; its recovery assertion
now checks the retained size preference, not an unintended sort reset.

## Acceptance and remaining limits

- Candidate version: **0.18.45**, portable SHA-256
  `2e07a0fff40e3b7d0155cf82aa259d501da0d0e6c402c218100f11e55821635a`.
  Final clean-commit Linux full suite: **117 groups passed**, 1075.6523 seconds
  with two workers, including 476 unit tests (9 platform-conditional skips) and
  33 new behavioral cases in both source and portable form. Final outputs are
  clean after explicit owned-variable/trace disposal. Existing owner edits to
  four maintenance/test files were neither published nor substituted into this
  clean-worktree acceptance. The same portable hash was checked in both trees.
  Tab traversal, queued/in-flight Markdown probes and repeated owned-trace
  disposal all have regression assertions. The portable file reproduces exactly
  from source with its recorded build date, 2026/10/28; it was not rebuilt merely
  because final validation crossed midnight.
  On resumption no old test or VM lease was active. The final code worktree is
  `a590c0e`; Linux and sequential Windows profiles used the same frozen bytes.
  The long trace wall time includes a capacity-interruption gap; phases are not
  retroactively reconstructed and continuous active-work time is unknown. The
  two-worker suite is not compared as a speedup against earlier four-worker runs.
- New scenarios supplement the full existing renderer, search, Compare, archive,
  settings, workspace, menus, overlay and interaction regression inventory. An
  unchanged existing test is not described as a newly explored scenario.
- Windows ARM64 and emulated-x64 Python 3.13.15 / Tk 8.6.15: **all ten final
  checks passed per profile**, with verified PE architecture and separate native
  package sets. Deep tasks run 33 cases with two explicit Windows skips (POSIX
  stream and unavailable symlink fixtures), not 33 executed passes. All four
  leased invocations completed cleanup and the final lease queue was empty.
  Actual-size GDI captures were inspected. This is **not native x64 Windows**.
- Publication remains held pending the owner's decision on the intermittent
  native failure described below. No new tag, push, updater or mirror acceptance
  is claimed. Unrelated owner changes remain untouched.
- Remaining higher-risk environment cases: real UNC/disconnected drives,
  OneDrive/native shell overlays, Windows sharing/permissions, multi-monitor DPI
  and native modal/file-picker behavior. Linux fixtures cannot certify them.
- Directory preflight/list insertion still runs on Tk; very slow network storage
  and extremely large row counts need a separately measured asynchronous/virtual
  listing design. This work removes repeated metadata and bounded-drain problems,
  not every possible UI pause. Current-item transfer cannot be interrupted midway.
  Batch-rename commit I/O also remains synchronous; debounce improves planning,
  not the duration of a real network rename operation.
- The surface inventory above is not a claim that every nested path/configuration
  was manually exercised. Preserve that distinction in the delivery summary.

| Final Windows request | Runtime | Checks | Whole invocation |
|---|---|---|---:|
| `e97d5b9a47534341a674fb6903980fb9` | ARM64 | Deep tasks, surfaces, controls, settings/groups, folder leaves | 282.92 s |
| `e61ca56eb8b643c29b2c5faa17267c43` | x64 emulated | Same five checks | 296.84 s |
| `c2bf359dd12a428ea02efba0705ac20b` | ARM64 | Render, Preview tabs, Compare, search results, reliability | 306.24 s |
| `303989c925214613b87703a42639ad50` | x64 emulated | Same five checks | 381.87 s |

Times include readiness/staging/evidence/cleanup, not only GUI execution. These
invocations were sequential; Linux tests overlapped some of them. Token counters
were unavailable throughout: usage/savings remain unknown, not zero.

## Maintenance workflow observations

The final first Windows group took 251.10 s (ARM64) and 287.18 s (x64) including
lease/readiness, staging, tests, evidence and cleanup. The five check subprocess
times total about 142.28 s and 177.54 s respectively: roughly 109–110 s is other
workflow overhead, not PFC foreground latency. Repeated artifact transfer is a
future measured optimization target, not permission to reuse another task's
session/artifact or bypass lease, architecture, hash and cleanup gates. These
shared-host observations do not prove that one runtime is universally faster.

### Native validation failure retained

The second x64 group passed Render reliability and Preview tabs, then the large
Compare check exited with `0xC0000005` after 46.474 s. Its 45-second diagnostic
watchdog had begun dumping all Python threads; output stopped midway through a
worker stack. ARM64 passed the identical check. This timing supports a watchdog /
emulation interaction hypothesis, **not** a confirmed PFC root cause. The last
two x64 checks did not run in that failed group. Cleanup completed and the lease
was released. Serial same-artifact isolation is required before publication;
the crash is not silently treated as an ordinary assertion or a passing retry.

The unchanged-artifact isolated x64 Compare rerun passed in 80.476 s, including
its original 45-second watchdog dump. That falsifies a deterministic
"watchdog always crashes" explanation. The historical v0.18.23 reliability audit
also records a native Compare access violation with unconfirmed cause; identical
root cause is **not** inferred. Added fatal-thread faulthandler capture and phase
markers to the fixture without removing its watchdog, assertions or timeouts.
The diagnostic-enhanced Compare/search/reliability group passed ARM64 and x64
(`d521dc1e5fd04a1fa3cc33a87b901276`, `c1a8a75be766480ba33013e5a11aec32`).
The exact-order x64 repeat on that earlier artifact then exposed a different,
actionable Preview-tab fold-state assertion: switching during a background stat
probe forced a full reload. Queued/in-flight probe regressions now verify the
correction. The final artifact's complete original-order group passed on both
runtimes, including x64 Compare in 77.736 s. The intermittent native access
violation remains an open reliability issue, not a claimed application fix or a
reason to silently disable diagnostics. At completion the owner had not yet
answered the publication-risk question; the subsequent decision is linked above.
