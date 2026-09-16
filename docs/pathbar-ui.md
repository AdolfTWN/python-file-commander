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
At extreme widths/zoom the drive selector hides to protect path space;
the parent and edit controls remain available. All locations can still be typed.

## Common-prefix Home button

The Home icon automatically represents the deepest matching user profile,
Downloads or configured OneDrive root. Clicking it returns to that root. The
represented prefix is removed from breadcrumbs, but F12/Ctrl+L, path copying
and archive navigation retain the full logical path. At the root itself a short
label identifies the location. Hovering shows the full root; right-click (or
Shift+F10 on the button) lists the detected and custom roots.

Choose **Custom folder prefixes…** in that menu to configure three slots, each
with a built-in icon and an absolute path. Code, Documents and Photos are the
default icons; clear a path to disable a slot. Preferences are global to all
panels, stored in `[home_prefixes]` / `custom` in the existing INI. Matching is
by complete path components, not raw string prefix. More specific roots win;
custom roots override an identical built-in root. The Home icon remains visible
even in narrow panels because it now represents hidden path text.

Outside every configured prefix, the button displays a neutral ROOT drive icon
and opens the current drive or UNC share root. Breadcrumbs retain every ancestor
(normal narrow-layout overflow still applies); no prefix is stripped. Entering
a matching tree immediately restores that tree's colorful icon and shortened
breadcrumbs. Leaving a nested prefix uses any still-matching outer prefix, or
ROOT if none matches. Archive locations use the original ZIP's drive and path,
not its temporary extraction folder. F12 always edits the full logical path.
The six prefix badges use distinct vivid orange, blue, green, purple, cyan and
pink colors, in addition to their different symbols.

Parent and Home use equally sized antialiased icons and matching button bounds.
Folder icons are rendered at the current default font's line height, including
the Home menu and custom-prefix previews. An open preferences dialog updates
its previews when zoom changes without losing unsaved selections. Rendering
uses supersampled geometry and transparent PNGs, with no extra image dependency.
`tools/home_icon_check.py` checks size parity at every 100–300% zoom step.

Windows Downloads detection reads the redirected path from the current user's
[User Shell Folders setting](https://learn.microsoft.com/en-us/troubleshoot/windows-client/shell-experience/change-personal-folder-location-fails).
OneDrive discovery reads local environment/account configuration only: no cloud
connection, account login, or folder-content scanning is performed.

The bottom-right zoom control is compact-only: minus, percentage dropdown, plus.
Auto Font Size is a checkable option inside the percentage menu, not a permanent
checkbox. The control stays small independently of the global font scale.

Regression checks: `tests/test_pathbar.py` and `tools/pathbar_check.py` (also run
with `pfc` for the portable edition). They cover layout, themes, zoom, edits,
selection, native menus, locked tabs and archive navigation. The Windows native
menu loop requires OS input to dismiss before programmatically testing commands;
manual pointer interaction should also be checked on the leased offline VM.
