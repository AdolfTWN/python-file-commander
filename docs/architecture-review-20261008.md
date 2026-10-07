# PFC architecture review and measured improvements

PFC v0.18.22 reduces repeated ZIP metadata queries and merges duplicate folder
notifications before the interface processes them. The portable builder now
uses one explicit module list and syntax-aware import handling. Existing UI
commands, layout, font fitting, archive safeguards and dependencies are retained.
These are targeted improvements, not a wholesale architecture rewrite.

## Prioritized findings and decisions

Priorities below describe engineering impact, not an allegation of data loss.
P2 means responsiveness or build-reliability risk; P3 means maintainability or
avoidable operation cost.

| Priority | Finding and reproducibility | Implemented improvement | Engineering value |
| --- | --- | --- | --- |
| P2 | Folder watchers queued every notification; deduplication occurred only when the GUI drained the queue. A 100,000-event same-directory fixture reproduces the backlog deterministically. Continuous arrivals could prolong a drain indefinitely. | Keep one pending invalidation per canonical directory; use the queue mutex for producer/consumer transitions. Drain only the current queue snapshot, retaining later events for the next tick. | 100,000 pending records become one. GUI drain latency falls from approximately 78 ms to 0.0024 ms in the fixture. |
| P2 | Portable assembly repeated module-specific textual import stripping. Multiline imports, aliases or additional statements on an import line could silently break the generated application. | One ordered manifest covers all 54 application modules. Parse imports structurally, preserve nested fallback imports, reject unsupported aliases/star imports and validate syntax before writing. | Builder decreases from 130 to 91 lines; new modules have one manifest entry instead of another special-case assembly sequence. Coverage, determinism and unsupported syntax have regression tests. |
| P3 | ZIP creation repeatedly classified and measured the same descendants during validation, progress calculation and writing. A fixed 5,000-file workload reproduces 31,516 `os.stat` calls. | Reuse operation-local metadata and archive names. Keep fresh ZIP file reads and use the number of bytes actually written for progress. | Metadata calls decrease 66.6%; elapsed compression time decreases 25.7% in the measured workload. |
| P3 | Windows extended-path conversion was independently defined in file operations and archives, with one definition silently shadowing the other in portable builds. | Archive operations re-export the existing file-operation helper. | One implementation instead of two; the call signature and existing import location remain available. |

## Before and after measurements

Measurements use the same Linux host, Python, fixture generator and repeat count.
Archive timings exclude fixture creation and are collected without instrumentation;
metadata counters use a separate pass. Medians are not promises of equivalent
Windows, network-share or large-file throughput.

| Fixed workload | Before | After | Difference |
| --- | ---: | ---: | ---: |
| ZIP creation, 5,000 files, 500 descendant directories, seven timed repetitions | 375.84 ms | 279.38 ms | 25.7% less time |
| `os.stat` calls in that ZIP operation | 31,516 | 10,513 | 66.6% fewer calls |
| ZIP members in that operation | 5,250 | 5,250 | Unchanged |
| 100,000 notifications for one directory, five repetitions, queued records | 100,000 | 1 | Duplicate backlog eliminated |
| GUI notification drain median | 78.046 ms | 0.002416 ms | Smaller GUI processing burst |
| Background notification enqueue median | 37.712 ms | 58.920 ms | Additional normalization and deduplication work |
| Notification enqueue plus drain median | 115.301 ms | 58.922 ms | 48.9% less total time |
| Portable builder source lines | 130 | 91 | 30.0% fewer lines |

Each benchmark archive contains selected-root-relative names, explicit empty
directories and fixed timestamps. Member order, uncompressed sizes, CRCs,
external attributes and every progress callback produce identical fingerprints
before and after. A second 2,000-file fixture also preserves both fingerprints
and decreases median compression time from 153.23 to 112.91 ms. The portable
edition runs the same workload and invariants.

The builder refactor, before the archive and watcher changes, produced an AST
identical to the previously released portable artifact. AST equality covers
statement ordering and executable expressions; whitespace and new source-marker
comments are intentionally different. Generated source markers identify module
boundaries for debugging.

Syntax validation adds developer build cost. The traced build takes about
0.42 seconds, versus a previous matching-build median of 0.09 seconds. That
historical comparison is not a controlled startup benchmark; the added fraction
of a second is accepted for explicit import failure and compile validation.
There is no claim that application startup improved.

## Preserved behavior and limits

ZIP manifests exist only for one operation, not as a persistent filesystem cache.
Every new compression operation re-enumerates the inputs. ZIP writing still reads
files freshly, and existing destination-change checks, staging and failure cleanup
remain in place. This is not an atomic snapshot of concurrently edited source
directories and does not introduce a directory-link policy change.

Folder notifications request a rescan rather than replaying individual file
events. Repeated pending notifications for the same directory are therefore
interchangeable. A notification after consumption is retained, and a notification
during draining remains for the next tick. Existing polling fallback, refresh
cadence, selection preservation and edit-in-progress deferral remain unchanged.
Queue growth is bounded by distinct pending directories, not by a fixed byte cap.

The portable edition still has its established shared global namespace. This
release preserves dependency order instead of introducing a custom runtime
module loader. Two existing duplicate COM helper names have equivalent behavior
but remain a reason not to treat arbitrary aliased imports as safe to flatten.

## Further opportunities not justified for this release

- `app.py` has about 6,000 lines and 34 direct package import dependencies;
  `compare.py` has 2,719 lines. Extracting controllers may reduce change coupling,
  but splitting files alone supplies no measured user benefit. A future extraction
  should be tied to a concrete repeated operation and characterize UI state first.
- Preview, search and editable comparison have different text-decoding and
  invalid-encoding policies. Preview's BOM handling also differs from search for
  UTF-32. A single generic loader would change fallback and editing behavior;
  define explicit read-only versus lossless-edit policies and add an encoding
  matrix before consolidation.
- VCS limits physical work per pane, not across all tabs. A repository-wide worker
  budget needs a measured multi-tab workload and starvation/cancellation tests;
  replacing every thread with a general scheduler is not warranted by the present
  compression and refresh measurements.
- Markdown uses a persistent process, while comparison uses request-specific
  processes with different budgets and protocols. Merging their lifecycle managers
  without failure-isolation tests would enlarge the failure surface.
- Archive browsing capacity limits, native watcher shutdown races and live cloud
  transitions retain the limitations listed in the reliability audit. Offline
  architecture tests are not cloud synchronization acceptance.

## Repeating the measurements

Use the mandatory maintenance runner to record these commands under the current
task's run identifier:

```sh
python3 tools/architecture_benchmark.py --folders 250 --files 20 --repeats 7
python3 tools/architecture_benchmark.py --module pfc --folders 250 --files 20 --repeats 7
python3 tools/architecture_benchmark.py --module pycommander.dirwatch --notifications
python3 tools/architecture_benchmark.py --module pfc --notifications
python3 tools/architecture_check.py
python3 tools/architecture_check.py pfc
```

Raw timing logs and baseline snapshots remain outside the repository. Official
token counters are unavailable, so token usage and savings are unknown.

## Validation results

- Unit discovery passes **385 tests**, with nine platform-specific skips on
  Linux. This adds 23 cases to the previously released 362-test suite, including
  shared source/portable archive and notification fixtures.
- All **95 complete headless checks pass** in **415.01 seconds** with four
  isolated workers. The suite's before/after source fingerprint agrees; no
  application or test code changed during the run.
- The portable builder's syntax, deterministic output and checked-in artifact
  parity pass, including multiline imports, strings, nested fallback imports,
  alias rejection and failure before artifact replacement.
- The native Windows attempt is **blocked before guest staging**, not passed.
  VM1 never started within the manager's readiness window and QGA was unavailable.
  The host had approximately 28 GiB available, below the protected 30 GiB startup
  gate. The lease was released and the queue is empty. Guest networking was not
  enabled; a NIC-disable command could not be confirmed against a non-running
  VM. No VM configuration, account or disk was changed.
- The previous 93-check suite took 423.57 seconds. This release has a different
  95-check scope, so the smaller total is **not** a controlled test-runner speed
  improvement. Only the fixed workloads above support optimization claims.
