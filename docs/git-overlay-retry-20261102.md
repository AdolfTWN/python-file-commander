# Git overlay timeout recovery — v0.18.47

Run: `61679877271a4722a536791eb404f27e`.

## Evidence and scope

The owner's v0.18.46 photographs show `vcs.overlay.unavailable` with
`tracked-files-timeout`, while another directory of the reported same clone
does show Git badges. This establishes that a tracked-index listing exceeded
PFC's four-second command limit. It does not establish why Git was slow on that
computer: index size, storage, endpoint protection and process startup remain
unverified possibilities. No private repository or log export was available.

Code inspection and a controlled regression reproduce an additional PFC issue:
the failed background query leaves unknown clean entries without badges, but
the idle pane does not itself arrange a retry. The old implementation fails the
new automatic-recovery regression; it starts one query, not the required second.

## Changes

- Preserve the ordinary four-second per-command budget and asynchronous UI.
- Only Git status/index **timeouts** schedule one retry after a one-second
  delay. That retry has an eight-second **per-command**, not total-query, budget.
- Use the existing one-worker-per-pane mechanism; do not create a retry loop.
  Navigation, archive views and disabling overlays discard a pending retry;
  existing generation/path guards discard obsolete in-flight results.
- Retain valid last-known snapshots and confirmed changes. Never fabricate a
  green badge for an entry whose tracked state could not be obtained.
- Include attempt (1/2), command timeout and elapsed query seconds in bounded
  warning diagnostics without command stderr or filenames.

This is timeout **recovery**, not proof that the owner's underlying Git command
is faster or that every slow query will succeed. A second timeout still leaves
unknown entries unbadged and records a warning; there is no unlimited retry.
The longer budget is not used for every successful folder navigation.

## Validation

Verified code candidate: `9c017b3b33f1f283129ddffdf432913953568c1d`.
Portable SHA-256:
`57149b301bc20f3953b3328976df35941b90b4ad6446843b90415250320fe802`.
The subsequent test-only commit `f168ed3` and evidence documentation do not
change the application artifact or the three Windows check scripts.

Tests cover delayed retry, automatic idle-pane recovery, retaining
confirmed changes, unknown versus clean, persistent timeout bounds, permanent
error suppression, navigation/disable/archive cancellation and the retry budget.
The GUI fixture injects the first tracked-list timeout, then uses its available
Git backend for recovery and checks Tk heartbeat processing. Injected delays are
not represented as real storage/antivirus timings. Existing warm navigation,
badge pixels, unchanged-icon repaint suppression and metadata exclusion remain
part of that check.

- Final clean-worktree full suite: 121 groups passed in 560.920 seconds;
  495 unit cases with nine
  platform-conditional skips. Source and portable Git GUI checks passed.
- Win11-ARM64-VM, Python 3.13.15 / Tk 8.6.15, sequential profiles against the same
  artifact: ARM64 request `760d8d716c734bc7b0a9fe05ae5d4278` and emulated-x64
  request `3846c12de2fd44f3af135ca2f7054159`; all three requested checks passed
  in each, cleanup errors empty. The lease pool was empty after validation.
- Both profiles used **real Git CLI**. The GUI retry check took 10.094 / 13.087
  seconds respectively. A deliberately injected first index timeout recovered
  using budgets `[4, 8]` without another user action; 71 / 70 Tk heartbeats ran.
  Eight cached child navigations issued zero new Git commands. These are fixture
  observations, not a speed comparison with the owner's repository.
- Reliability and cloud-badge regression checks also passed in both Windows
  profiles; ARM Windows application emulation is not native-x64 acceptance.
- Private evidence: the run's workflow logs and `windows-evidence/` directory;
  only synthetic files were used. No company filenames or log exports are needed.

Retained failures and limits: the first full run failed the existing portable
structure-search assertion following deliberate fixture-file modification.
A controlled refresh demonstrated that a valid rendered tree can replace its
old Treeview, violating the test's old-identity assertion. The test now suspends
the watcher only for stale-source rejection, then explicitly verifies automatic
reload, and rechecks pending work after its final event drain. This is a test
race correction, not a Preview application change or a claim about every earlier
search failure. One attempted next-tick reproduction did not trigger that race;
the successful controlled case explicitly completed automatic refresh first.

The second full run had a portable Compare workflow `StopIteration` while
locating a fixture row. It passed an isolated 13.170-second retry and the entire
final rerun without changing the application; its intermittent cause remains
unconfirmed. Earlier unit failure was an internal test stub not accepting the
new optional query budget; that stub was updated and the unit suite rerun.
All failures and retries remain in the private trace, not discarded.

No equivalent task baseline or token counters are available; no overall speedup
or token-saving claim. Windows stage totals include preparation/staging and
must not be summed with child checks or compared as native performance.

The earlier intermittent native Compare crash remains unconfirmed and is not
claimed fixed by this release.
