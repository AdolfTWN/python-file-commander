# Native crash diagnostics — 2026-10-29

Follow-up run: `cd3ac76724a242d8ae9c47d9ea11dd67`.
Prior exploration/evidence: `8184856fa7a345b88d8023bc3057540c`,
[deep exploration](deep-ux-exploration-20261028.md).

## Scope and owner decision

The owner authorizes publishing the pending v0.18.45 improvements after verifying
that the automatic diagnostics can record native failures for photographic
reporting. This supersedes the previous publication hold, not the unresolved
root cause of the earlier intermittent Compare access violation. No claim is
made that the original crash has been fixed.

## Recording and photo workflow

- No Debug/Verbose switch is needed. Normal Python/Tk/thread exceptions keep
  their existing automatic capture. Native capture starts with those hooks.
- An already-open, process-specific `pfc-native-<session>.log` descriptor receives
  Python's fatal-handler output. It has the emitting version, session, startup
  time and Python/platform/machine/Tk metadata before a crash occurs. It does not
  use normal Python logging, Tk or Python callbacks inside the fatal handler.
- On next launch, an unlocked fatal journal becomes one `CRITICAL`
  `process.native_crash` incident in the existing `pfc-errors.jsonl` stream.
  A Windows access violation is identified as `NativeAccessViolation`,
  `0xC0000005`. The crashing version/session are retained, even after upgrading.
  Crash time is explicitly the journal's last-write system time, not the restart
  time; `started_at` and `recovered_at` remain separate.
- After a crash: restart PFC → **Help → Error / Warning log** → select
  `process.native_crash` → photograph the summary. It shows version, system time,
  type/code, captured Python stack context and runtime together. Details retain
  structured fields; exporting a file is not required.
- The event list reserves two full rows using the current scaled row/header
  dimensions and scrolls the selected incident into view. Its old fixed-height
  strip could clip the selected row at 200% even when the summary fit.
- The Python stack is context, **not proof of the native crash location**. A
  failure in a native-only thread can lack a Python frame. A native DLL/address
  or memory dump is not fabricated from the Python stack.
- Raw journal stacks can contain Python source paths, but no variable values or
  document contents are deliberately captured. Recovery retains module basenames,
  line/function only and removes the consumed raw journal. Per-process lifetime
  locks prevent another running PFC's journal from being recovered or deleted.
  Failed structured writes retain the journal for the next start. A clean close
  removes its journal; header-only/timeout dumps are not reported as crashes.
- No extra periodic I/O, watchdog or per-folder metadata query was added. A
  pre-existing external fatal-handler owner is respected and a warning reports
  that PFC cannot install its private handler in that process.

## Limits

This is best-effort capture of Python-supported native fatal events while
diagnostics are active. Power loss, force-kill, pre-initialization/after-close failures,
unwritable storage, severe stack/memory corruption, or another component replacing
the fatal handler can prevent a usable record. No guarantee of every crash or
recovery from corruption is made. Ordinary handled operation errors still need
their instrumented error paths. No full memory dump, Windows registry change,
external crash service, runtime dependency or guest networking is introduced.

## Acceptance evidence

The test intentionally crashes **only a disposable
child process**: POSIX abort with core dumps disabled, or a Windows native thread
with an invalid entry point. The latter must exit with actual `0xC0000005`, not a
Python exception translated by ctypes. The parent stays alive, restarts the log,
checks the old version/time/runtime, views the existing summary and tests Clear.
Normal GUI regressions then run separately. VM/network/desktop ownership remain
under the leased dual-runtime adapter; ARM Windows x64 application emulation is
not native x64 Windows acceptance.

Final code commit: `95d6195`; portable v0.18.45, build date 2026/10/29, SHA-256
`d28663ed39f57cac65da3c5af0fa87dea8c972409472e73e990a655e17ddcc6a`.
The portable reproduces byte-for-byte from source. The selected Windows scripts
and artifact match the clean Linux test worktree; unrelated owner edits to four
maintenance/test files were preserved and excluded from the release.

- **Linux full suite:** 119 groups passed, **553.5587 seconds**, four workers.
  Includes 483 unit tests, with nine explicit platform-conditional skips, and
  source/portable GUI checks. No code/test changes occurred during that suite.
- **Windows ARM64:** Python 3.13.15, PE ARM64, Tk 8.6.15; all five checks passed,
  request `6baf56ce1f314fec9c7c7ee0056668f0`, 302.5819 seconds whole invocation.
- **Windows x64 emulated:** Python 3.13.15, PE x64 on ARM64 Windows, Tk 8.6.15;
  same five checks passed, request `432f0e14eadb4aae8934d0ffc3bc5728`,
  381.8992 seconds whole invocation.
- Checks on each runtime: native crash capture, Preview tabs/diagnostics, large
  Compare, Render reliability, general reliability. Native capture takes 5.430 s
  (ARM64) / 7.857 s (x64); it verifies a live second process is not consumed, clean
  exit leaves no false crash, an actual child exit `0xC0000005` is recovered
  without Debug mode, crash version/time are retained, Clear still works, and
  the selected event row plus summary fit at 200%.
- GDI captures at 100%/200% retained privately. Both final 200% captures were
  visually inspected: the event row is fully visible, and version, zoned system
  time, native code, Python stack context and runtime fit in the summary without
  scrolling. Large fixture geometry is not certification of every window size.
- Both invocations report cleanup `[]`; the final lease pool has no active lease
  or waiting request. No VM networking, hardware, model or THP setting changed.

These deliberately injected crashes prove capture of the same **class** of
native failure, not reproduction or repair of the earlier intermittent Compare
failure. Its root cause remains unknown. No unexpected native crash occurred in
the final acceptance checks. Post-push updater/reference/mirror acceptance is
required separately by the release gate; its private trace is the release proof.

### Failed experiments retained

The first ARM64 fixture used entry point `0x1` and exited `0xC00000AA`, failing
the exact access-violation assertion; x64 passed that candidate. The fixture now
uses an aligned unmapped address in Windows' reserved low 64 KiB and still
requires exact `0xC0000005` on both runtimes. No assertions/timeouts were removed.

The intermediate `7131a160…` artifact passed ARM64 capture, but the strengthened
x64 200%-row assertion exposed the clipped incident list. During correction the
matrix's final hash guard also rejected an artifact change. That invocation is
**not accepted as a matching matrix**. The adapter resolves the primary repository
even when invoked from a different working directory; do not infer isolation from
cwd. The corrected `d28663ed…` artifact was frozen and both profiles rerun to
completion; source/selected-script equality with the clean worktree was checked.

The intermediate full Linux suite passed 119 groups in 553.6053 s. After the UI
correction, the complete suite was rerun, yielding the final result above. These
are repeated validations, not failed tests or proof of an optimization. There is
no controlled comparable performance baseline for this diagnostic addition.
Official token counters are unavailable: token usage and savings are **unknown**.
