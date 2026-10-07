# PFC reliability audit — 2026-10-08 / v0.18.21

This is a focused reliability audit, not proof that every latent defect is gone.
Reproductions use disposable fixtures; no user files are intentionally modified.
P1 denotes potential data loss, wrong operation target or unsafe execution;
P2 denotes boundedness, availability or state-consistency defects.

## Findings, ordered by severity and reproducibility

| Priority | Reproducible defect | Mitigation and regression |
| --- | --- | --- |
| P1 | Python 3.11 lacks `os.path.isjunction`; progress deletion could traverse Windows junction targets. | Read the reparse tag on older Python; remove junctions as leaves. Mock 3.11 plus a native `mklink /J` sentinel fixture; disk-space scans also avoid following links. |
| P1 | Shell menu, cut/drag and Windows recycling resolved selected links to their targets. | Preserve lexical absolute selected paths, including dangling links. Shell/clipboard and mocked Shell recycle regressions; native junction path assertion. |
| P1 | A dangling destination link was treated as a free filename, allowing copy to write outside its destination. | Count links as existing conflicts; replace the link itself or select an unused name. External-target sentinel regression. |
| P1 | Virtual attachments tried only one alternate name; provider failure could delete an existing collision, and success could overwrite it. | Owned staging, exclusive filename reservation, repeat collision probing, size validation and cleanup of only owned files. Test collisions, duplicates, provider failure and partial streams. Reject device names, controls and alternate-data-stream names. |
| P1 | ZIP creation could truncate selected input, include its own output, or destroy previous output on failure. | Validate inputs/output and duplicate archive names before writing; stage and atomically publish after destination-state checks. Inject write failure and external destination creation. |
| P1 | An ordinary archive workspace could silently overwrite changes made after it opened. | Identity and content fingerprint checks on opening and before/after building a save; refresh after successful save. Two-session and during-save external-change regressions. Linked/special draft entries are rejected. |
| P1 | Failed ZIP extraction could leave an existing file partially overwritten. Unsafe later members could be detected after earlier files had changed. | Preflight all names, types and collisions; stage each file before publication. Test read/CRC failure and self-overwrite. 7z extracts into owned staging after link/name validation, with bounded subprocess waits and cleanup. |
| P1 | Background VCS overlays used bare executable names, permitting Windows working-directory executable lookup. | Reuse the existing trusted CLI lookup, disable prompts/index updates, and test selected command/environment. 7z lookup also excludes relative Windows PATH entries. |
| P2 | Simultaneous INI saves shared a fixed temporary path. | Unique temporary files, flush/sync and cleanup even after serialization failure. Barrier-coordinated writers verify complete valid output. Last complete writer wins; this is not preference merging. |
| P2 | Invalid batch names reached `Path.with_name` before validation; single rename could overwrite an unselected existing target. | Validate before constructing paths, recheck batch targets, reject invalid/device/control names, preserve recovery files on conflicts. Single rename/new-folder callbacks use the same validation. |
| P2 | Office search decompressed whole XML entries before applying its cap; encrypted/read failures aborted searches. Result limits stopped only the inner loop. | Bounded aggregate XML stream reads, unreadable-content handling and outer traversal stop. Validate finite nonnegative numeric filters. Tests inspect actual read sizes and limit termination. |
| P2 | Rapid folder changes started multiple VCS workers per pane and stale callbacks/cache writes survived invalidation. Expired cache entries accumulated. SVN query failure could appear clean; direct child repositories were queried twice. | One in-flight worker per pane with latest-path coalescing, stale result rejection, cache epochs, expiry pruning and a 128-entry cap, thread-start failure recovery, one child scan and an 8-second child-query scheduling budget. Failed/unqueried status stays unknown. |

The junction compatibility facts are documented by
[Python 3.12 `isjunction`](https://docs.python.org/3.12/library/os.path.html#os.path.isjunction)
and [Python 3.11 reparse tags](https://docs.python.org/3.11/library/os.html#os.stat_result.st_reparse_tag).
ZIP staging uses a writable handle for synchronization, as required by
[Windows buffer flushing](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers).
A success-path regression verifies the handle mode and compression/extraction
round trip. Search also tests BOM-marked UTF-32 in both byte orders.

## Validation and acceptance

- Baseline full inventory: 91 checks, one existing failure in the Help-menu smoke
  test, which still expected the pre-diagnostics menu. Its exact expectation is
  updated; the assertion has not been removed.
- New `tools/reliability_check.py` runs the same disposable fixtures against
  source and generated portable code. Unit discovery imports that fixture set.
- Added 37 shared regression cases. Final unit discovery: **362 tests, OK,
  nine platform-specific skips**. Source/portable fixture runs each pass with
  the Windows-only junction case skipped on Linux.
- Complete headless inventory: **93 checks, passed twice after fixes**. The
  final immutable candidate passed with four isolated workers in **423.57 s**;
  the preceding two-worker candidate took **826.01 s**. Fixture definitions and
  concurrency differ, so this is not a controlled optimization or token-saving
  claim. Source-fingerprint checks passed; no code changed during either suite.
- Real installed 7z source/portable open → edit → save → extraction also passed.
  Leased Windows results are recorded in the maintenance trace. Windows-only
  fixtures must not be counted as Linux acceptance.
- The leased native attempt stopped before guest staging: VM1 startup was
  deferred because host available memory was below its protected 30 GiB gate.
  The lease was released. No guest file writes or network enablement occurred;
  the runner could not confirm a NIC-disable operation because QEMU never
  started. This is **blocked native validation**, not Windows acceptance.
- Run ID: `d6c9bd4c07454e84a389b5dd62ec5b09`. Logs remain private outside Git.
  Timing comparisons come from the tracker; token counters are unavailable.

## Remaining risks / deliberately unclaimed coverage

- Live OneDrive hydration, concurrent provider transitions and real account sync
  remain unverified; this offline audit does not require or claim account access.
- Per-file atomic extraction is not an all-or-nothing transaction for an entire
  archive. Earlier successful members remain if a later unrelated I/O failure
  occurs. A 7z extract also needs temporary disk space before publication.
- Identity/hash checks greatly reduce lost-update risk but cannot provide an OS
  compare-and-swap against a hostile process replacing a path in the final
  check-to-replace interval. Rename rollback preserves recovery copies if an
  external file occupies the original name; manual reconciliation may be needed.
- Normal archive browsing has no product-wide expanded-size/member budget yet;
  comparison retains its existing safety budget. Disk exhaustion and very large
  ZIP workspaces need a separately specified cancellable capacity policy.
- Folder copy semantics for nested reparse points, filesystem races during
  traversal, ACL/alternate-stream preservation and multi-volume rollback need
  additional native fixtures; the current fixes are not a universal filesystem
  transaction layer.
- Workspace restore rollback and directory-watcher shutdown races merit further
  fault injection. No speculative change is made without a reliable fixture.
- The child-repository scheduling budget is checked between queries; an already
  started command can consume its existing four-second timeout. Four panels can
  contain many FilePane tabs, each with its own in-flight limit; no global VCS
  worker queue is claimed.
