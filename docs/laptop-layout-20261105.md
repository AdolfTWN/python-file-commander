# Laptop layout recovery — v0.18.49

Trace: `3f14d25f3cbf4e77ad6dc2a924b26654` (2026-11-05, Asia/Singapore).

## Reproduction and cause

The released v0.18.48 portable reproduces the missing bottom controls with 40
synthetic spreadsheet filenames, two panels, a 1260x650 client and 200% UI text.
The negative-control check fails specifically because the bottom action bar is
unmapped, not because a screenshot or import failed. The original failure and
before image are retained privately. Reducing font size can make the bar visible
again, but is not the repair.

Tk pack allocation follows sibling order. The expanding main split was packed
before the action bar; inside each panel, the file viewport was packed before
status and Quick Filter. Enlarged fonts and the requested Treeview height could
consume all available space, silently unmapping later siblings. Separately,
detail columns retained measured widths while Name had only a 120-pixel floor.
The old main-window visibility guard checked title accessibility rather than
fitting the entire frame after restoring a larger-screen geometry.

## Changes and task acceptance

- Reserve bottom actions/zoom before the main split, and each panel's status and
  filter before its file viewport. The file viewport absorbs height reductions.
- Keep the selected reading scale. Retain the existing hover-revealed +/- and
  percentage menu rather than adding another recovery toolbar.
- Reserve a useful filename width (45% of the available panel, bounded by 18 M
  glyphs and a 120-pixel floor). Detail columns keep their readable sizes; when
  all fields cannot fit, the existing horizontal scrollbar exposes the overflow.
- Opt the main window into full-frame work-area fitting at startup and stable
  monitor/work-area changes. Existing guard debounce, normal dragging,
  minimization and valid maximization policies remain unchanged.
  Perform the first fit after initial idle layout, before delayed polling, so
  geometry does not change later while the user is editing a Settings draft.
- No additional folder scans, polling timers, network or OS startup-task changes.
  Auto Font Size still does not resample merely on folder navigation.

UI/UX self-review focuses on three tasks: reduce scale from an oversized layout
without losing its control; browse populated filenames/filter/actions at laptop
dimensions; relaunch saved large-screen geometry on a smaller work area. Passing
an empty/default-size window check is not equivalent to these tasks. Earlier
v0.18.48 F4 Search evidence remains valid for Search, not main-window acceptance.

## Validation

Final source/portable and dual-runtime Windows results are recorded below after
verification. The new check tests 125%, 150%, 175% and 200%, visible containment of
every bottom action and zoom control, populated file lists, Quick Filters,
usable filename space, stable recovery and a separate-process application restart.
On Windows only work-area reporting is simulated (1280x720); actual native
frames are measured and moved. The shared VM display and startup configuration
are not changed, and Windows itself is not rebooted.

The first Linux restart fixture incorrectly expected a 720-pixel work area while
Xvfb actually reported 1024 pixels; the fixture now uses the reported area there.
The original test failure remains in the trace. No application failure is
reclassified as acceptance.

An initial settings regression also detected a delayed startup geometry save
while the Settings draft was open. A focused INI comparison showed only window
geometry changed, not preferences. Immediate initial-idle recovery removes the
delay; the original unmodified cancel/no-write assertion subsequently passed.
Release-note translations were also caught by and added for the unit suite.

Physical laptop reboot/DPI transition and native-x64 Windows acceptance remain
outside this VM evidence. Task timing has no comparable controlled baseline;
official token counters are unavailable. No performance/token saving is claimed.
