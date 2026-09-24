# Measured PFC maintenance workflow

Introduced in v0.18.10. These are **development/test tools**, not a PFC UI feature
and not a claim that the outstanding black-tooltip or live OneDrive issues are fixed.

## Default contract for subsequent tasks

The repository and GB10 workspace AGENTS instructions require a trace for every
PFC change, repair, update, validation and release. Start once and retain the run
ID across context compaction. No nested agent/model is needed for deterministic
steps. Existing model/effort settings are not changed.

```sh
python3 tools/pfc_workflow.py start --kind bugfix
python3 tools/pfc_workflow.py mark --run RUN_ID --phase implementation
python3 tools/pfc_workflow.py run --run RUN_ID --stage build -- python3 tools/build_single_file.py
python3 tools/pfc_workflow.py test --run RUN_ID --profile tooltip --jobs 2
python3 tools/pfc_vm_runner.py --run RUN_ID --checks tooltip_check.py
# After an authorized commit/tag/push and completed mirror workflow:
python3 tools/pfc_workflow.py release-check --run RUN_ID
python3 tools/pfc_workflow.py finish --run RUN_ID --status passed
```

Use `completed-with-issues` instead of `passed` if a required stage remains
blocked. Recovered retries remain in the trace; the latest result for every
stage must pass before the task can be marked passed. A missing test is not
evidence of success: keep the acceptance checklist in the task/documentation.

`sh tools/run_headless_checks.sh` now automatically creates a validation run,
runs the full inventory through the measured runner, and prints a comparison.
For a focused self-contained run use:

```sh
python3 tools/pfc_workflow.py auto-test --profile preview --jobs 2
```

Profiles: `tooltip`, `tree`, `preview`, `settings`, `tabs`, `vcs`, `workflow`, `full`.
Except for the workflow tooling self-check, profiles include the entire unit
suite and their selected GUI tests in source/portable forms where declared in
the existing headless inventory. Full preserves all existing checks. No test
result caching or hidden test skipping is enabled.

Workers 1/2/4 are supported, each with a separate Xvfb display. Windows GUI tests
are always sequential on their leased desktop. Test-definition hashes and a
before/after source fingerprint prevent comparing different check sets or
accepting a suite while its code changes. Check timeouts terminate only this
runner's subprocess group/child tree, not another task or the VM.

## What is tracked and compared

Records are in `~/.local/state/pfc-workflow/runs.sqlite3`, private on Linux;
command logs are inside each run's private subdirectory. Use `--state-dir` for
an explicit isolated test store. Do not put it in Git. No transcript is copied
into the store. Commands/arguments and raw test output are not echoed by default;
only result, duration, output byte count and the private log basename are shown.
Inspect only the relevant failure log. Logs can contain application paths:
they are not certified anonymous and must not be uploaded without review.

- Wall-clock elapsed: from trace start to finish, including waiting/analysis.
  It cannot retroactively include work before tracing was activated.
- Stages: command/suite/Windows/release-check durations, failures and retries.
  Suite durations overlap their child tests; **do not sum them** as total time.
- Phases: use `mark --phase analysis|implementation|validation|environment|release`
  when changing work phase. Tests and the release gate mark their phases
  automatically. Older bootstrap records are labelled `unclassified`, not
  retroactively attributed to analysis. Phase durations include waiting.
- Identity: host fingerprint, OS/architecture, Python/Tcl versions, source hash,
  test-definition scope; Windows additionally records the assigned VM/result.
- Compare to up to five previous matching runs, using the median. Task totals
  require successful tasks with the same kind/environment/final stage scopes.
  Passed stages may still be compared when another stage, such as VM readiness,
  is blocked. Failed readiness is never compared as a successful native test.
- Negative change means less time/tokens; positive means more. These are
  observations, **not proof of causality**. Small samples, CPU load and different
  bug complexity still matter. No baseline means “no comparable baseline”.

Run `report --run RUN_ID` at any time. `finish` automatically emits the summary
and comparison. Future assistants must include measured results or the missing
baseline/usage limitation in their handoff; changing the model/effort is not an
approved shortcut.

## Real token counters, never proxies

Official `codex exec --json` streams emit `turn.completed.usage`. Import a trace
belonging only to this task:

```sh
python3 tools/pfc_workflow.py usage --run RUN_ID --events /private/task-events.jsonl --coverage full
```

Input, cached input, output and (if reported) reasoning counters are retained
separately. Cached input is included in input; reasoning is included in output.
They must not be added a second time. Missing counters remain null. Importing
again replaces counters rather than double-counting the same file.

For a live official event stream, `start --events FILE` or the task-specific
`PFC_WORKFLOW_EVENTS` environment variable enables automatic refresh on reports.
Live coverage is always partial, because the current turn's final usage event
has not necessarily arrived. After the outer session finishes, import its
completed trace with `--coverage full`. The importer never scans other chats or
authentication files. Merely enabling tracing cannot expose counters that the
current ChatGPT/remote transport does not provide.

Token comparisons require full coverage and the same known model/effort, as well
as matching task scope/environment. A partial trace, absent transport counters,
or unknown model/effort yields **unknown/incomparable**, not zero or claimed savings.
Tool calls, output bytes and waiting seconds are not converted into estimated tokens.

Reference: [Codex JSON events](https://learn.chatgpt.com/docs/non-interactive-mode#make-output-machine-readable).

## Windows readiness and cleanup

The host runner imports the existing GB10 lease manager and VM configuration.
It acquires its own unique lease, never reuses another invocation's lease, and
routes all QGA calls using the returned VM ID. A busy pool waits for promotion
for up to the readiness timeout (capped at 60 seconds), without touching either
desktop. On timeout it cancels only this invocation's request, recovering and
releasing its lease if promotion raced cancellation. Retry later explicitly.

Sequence:

1. Lease → bounded QGA readiness wait → read-only Python execution probe.
2. If guest execution is unavailable, stop **before artifact writes or UI input**.
3. Stage a fresh request-specific directory, exact hashes and selected checks.
4. Register a uniquely named, least-privilege **InteractiveToken** task for the
   dedicated PFC-Test account; no password, elevation, auto-login or network.
5. The worker checks the real input desktop before any PFC import/test and during
   running checks. Locked/disconnected/unavailable desktops are blocked.
6. Atomic request-ID-bound reports distinguish starting/running/passed/failed/
   blocked. A passing report must contain every requested check with exit code 0.
7. End unfinished own task, remove own task registration, disable network and
   release lease in cleanup. Renew the lease every minute and check ownership
   before every guest operation. Cleanup uncertainty overrides a pass.

Only the newly generated task is removed; staged fixtures/logs are retained in
the disposable VM for diagnosis. The tool does not delete user files, reset
accounts, unlock Windows or reset the VM. If host execution is abruptly killed,
the existing lease expiry/network manager remains the fallback; do not promise
that Python `finally` runs after SIGKILL or host power loss.

The VM requires an already usable interactive test session. Restoring the broken
QGA/login environment is separate maintenance, not a silent password-reset step.
The first live v0.18.10 runner attempt stopped at `qga-not-ready` and released the
lease without input or credential access. Host/worker safety paths are covered
by mocked tests; **the full scheduled-task Windows execution path is not yet
accepted on the live VM**. Keep that boundary in future reports.

References: [Interactive tasks](https://learn.microsoft.com/en-us/windows/win32/taskschd/schtasks),
[input desktop](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-openinputdesktop),
[desktop identity/input status](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getuserobjectinformationw).

## Release gate

`release-check` is read-only: it requires a clean worktree, GitHub main and version
tag matching HEAD, the actual updater returning the exact local portable bytes,
and a successful GitLab mirror workflow for this commit containing its reference
comparison proof. It never commits, tags, pushes or enables networking itself.
The established private mirror's privacy is still verified through the available
GitLab integration before delivery; no new credentials are stored by this tool.

Environment safety and failed-test details take precedence over a speed target.

Initial validation: all 80 GUI checks were executed, with 78 passing and two
`folder_leaf_check.py` Right-key expansion timeouts (source and portable).
Serial reruns also failed intermittently; a later tree-group rerun passed.
This remains a follow-up, not a demonstrated parallel-runner regression or a
fixed PFC keyboard bug. The trace retains the failed full run and all retries.
