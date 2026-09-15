# Path bar and view selector

The path bar shows clickable logical ancestors. Earlier ancestors move into an
ellipsis menu when space is limited; the current folder has priority and bold
text. Hovering shows the full path. ZIP locations use the original archive name,
never the extraction directory.

Use the pencil button, Ctrl+L, or F12 to edit the full path. Enter navigates;
Escape or leaving the editor discards unsubmitted input. Invalid input remains
editable. A full file path selects that file in its containing folder without
executing it. Locked tabs retain their existing open-in-another-tab behavior.

The adjacent dropdown directly selects List, Folder tree, or File tree for this
tab. In narrow panels it shows a mode icon; its tooltip gives the full name.
At extreme widths/zoom the drive and home shortcuts hide to protect path space;
the parent and edit controls remain available. All locations can still be typed.

The bottom-right zoom control is compact-only: minus, percentage dropdown, plus.
Auto Font Size is a checkable option inside the percentage menu, not a permanent
checkbox. The control stays small independently of the global font scale.

Regression checks: `tests/test_pathbar.py` and `tools/pathbar_check.py` (also run
with `pfc` for the portable edition). They cover layout, themes, zoom, edits,
selection, native menus, locked tabs and archive navigation. The Windows native
menu loop requires OS input to dismiss before programmatically testing commands;
manual pointer interaction should also be checked on the leased offline VM.
