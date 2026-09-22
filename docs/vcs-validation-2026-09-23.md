# F8 validation — v0.18.5

## Verified

- Unit suite: 247 tests, 8 platform-specific skips. Nine new backend cases cover
  real local Git status, ahead/behind data, worktree boundaries, literal pathspecs,
  detached HEAD, selection scope, conflicts/renames, SVN property/tree-conflict
  XML, command failures/timeouts and argument-array GUI dispatch.
- Package and portable F8 GUI checks: three interface languages, 1–4 panels,
  100/150/175/200% font scale, 1050/1600-pixel window widths, stable zoom area,
  transfer destinations, tree/file focus, mixed-root guards, retained popup window,
  metadata locations, disabled overlays and child-window hotkey isolation.
- Existing GUI smoke (including localized checks), context settings, zoom,
  single-panel, header popup and real-Git drag-refresh checks pass.
- Leased Windows VM1, Python 3.13, native Tk desktop: final portable F8 GUI check
  exits 0. Network stayed disabled. Visual inspection at 175% prompted upward
  menu placement and readable status-summary text; the resulting popup-position
  assertion passes on Windows and Linux.

## Explicit limitation

The Windows VM has no TortoiseGit/TortoiseSVN installed. Tests intercept external
process launch and verify the exact selected paths and repository/branch scope.
They do **not** validate actual client dialogs, authentication or server writes.
No client was installed, and no real commit/push was performed by PFC. Real-client
end-to-end checking remains tracked in TODO. This is an integration dependency,
not evidence of a successful remote synchronization.
