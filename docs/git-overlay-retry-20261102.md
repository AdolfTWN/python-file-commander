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

Pending final same-artifact source/portable and sequential Windows ARM64/x64
acceptance. Tests cover delayed retry, automatic idle-pane recovery, retaining
confirmed changes, unknown versus clean, persistent timeout bounds, permanent
error suppression, navigation/disable/archive cancellation and the retry budget.
The GUI fixture injects the first tracked-list timeout, then uses its available
Git backend for recovery and checks Tk heartbeat processing. Injected delays are
not represented as real storage/antivirus timings. Existing warm navigation,
badge pixels, unchanged-icon repaint suppression and metadata exclusion remain
part of that check. Tokens are unavailable; no speedup or token-saving claim.

The earlier intermittent native Compare crash remains unconfirmed and is not
claimed fixed by this release.
