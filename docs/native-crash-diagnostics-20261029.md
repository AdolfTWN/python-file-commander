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

Pending final validation. The test intentionally crashes **only a disposable
child process**: POSIX abort with core dumps disabled, or a Windows native thread
with an invalid entry point. The latter must exit with actual `0xC0000005`, not a
Python exception translated by ctypes. The parent stays alive, restarts the log,
checks the old version/time/runtime, views the existing summary and tests Clear.
Normal GUI regressions then run separately. VM/network/desktop ownership remain
under the leased dual-runtime adapter; ARM Windows x64 application emulation is
not native x64 Windows acceptance.
