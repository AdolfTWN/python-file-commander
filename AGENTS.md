# PFC delivery default

After implementing and validating a requested PFC change, increment the patch
version (for example 0.17.20 -> 0.17.21), regenerate the portable pfc.py, and push
main plus the version tag. Verify the app's Check for Updates source contains the
new version. Also verify the existing private GitLab backup mirror has identical
branch/tag references. Do not create a separate release repository.

Skip versioning/publishing only when the user explicitly says not to. Never
publish unrelated changes, credentials, unvalidated fixes, or claim a failed
mirror is complete. Preserve existing user work and report release blockers.

# Required maintenance tracing

For every PFC feature, repair, update, validation or release task:

1. Start `python3 tools/pfc_workflow.py start --kind <bugfix|feature|maintenance|validation|release>`
   before task actions and retain the returned run ID. Resume that ID after
   compaction; do not create a new baseline mid-task. Specify model/effort only
   when actual session metadata is available; never lower either to manufacture
   token savings. Read `docs/maintenance-workflow.md` for the operational contract.
   Use `mark --run ID --phase implementation|validation|environment|release` when
   changing work phase; do not reconstruct missing phase timings from memory.
2. Route deterministic commands through `pfc_workflow.py run --run ID --stage NAME -- COMMAND`.
   Use `test --run ID --profile ...` for grouped source/portable regression.
   Do not repeatedly read complete logs; inspect the named private failure log.
3. For GB10 Windows checks use `python3 tools/pfc_vm_runner.py --run ID --checks ...`.
   It owns its lease, routes by returned VM ID, checks readiness and releases in
   finally. Do not call temporary VM1-only VNC/CMD helpers or type passwords to
   work around a blocked readiness gate. Environment repair is separate work.
4. Import available official `codex exec --json` usage via `usage --run ID --events FILE`;
   mark full coverage only for an exact completed task trace. Without counters,
   report token usage unknown. Tool/output-byte counts are not token estimates.
5. After an authorized push use `release-check --run ID`. Finish with
   `finish --run ID --status passed|blocked|failed|completed-with-issues` and include
   measured comparison or "baseline not yet available" in the handoff. Never
   treat a blocked Windows run as native acceptance or a speed improvement.

The trace store/logs live outside Git. Do not publish transcripts, credentials,
private diagnostics or raw telemetry. These tools do not authorize network
enablement, account changes, unrelated commits or additional publication.
