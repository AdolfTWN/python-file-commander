# Component context settings — v0.17.20

Settings belong near the component they affect. Main menus remain the complete
entry point; context menus reuse their models, variables and INI persistence.

| Right-click target | Settings |
| --- | --- |
| File-list blank area | Panel View (List/Folder tree/File tree), File Columns, Refresh, Panel Counts, Right Click Menu, Font Size, Color Scheme |
| File-column heading | Existing per-column display options |
| Tab | Tab Color submenu, existing three lock choices, shared Tab Style |
| Empty tab-bar area | Tab Style, without modifying a tab's color/lock |
| List/Folder/File view button | Its existing view choices |
| Zoom percentage or plus/minus | Font size and Auto Font Size |
| Home/prefix icon | Existing predefined/custom folder-prefix menu |

Blank-area clicks activate the clicked pane but preserve any prior selection.
Their menu contains settings/Refresh only, never Delete/Move/Rename against that
selection. Clicking an actual file retains the configured Windows Explorer/PFC
context behavior. Blank space always offers PFC panel settings, even in Explorer
mode. Column separators remain resize handles rather than blank-area targets.

Panel View and per-tab visibility follow the active pane as before. Panel count,
right-click mode, font, scheme and Tab Style retain their existing application-wide
scope. Tab Color and lock behavior apply to the clicked tab. Selecting Tab Style
does not silently create a per-tab style preference.

Shift+F10 or the Menu key opens the focused tab bar's menu; on an empty file list
it opens panel settings, while a focused file row keeps its file menu. The view
and zoom controls support the same keyboard entry points. Esc dismisses settings.

Background/tab/zoom settings use PFC's scalable cascade renderer, shared with the
main menu, including keyboard traversal and screen-edge placement. Settings
models are reused, so hiding a column can be reversed through either File Columns
entry point. Tab menus retain variable ownership for reliable selection markers
and dispose of old menus instead of accumulating them after repeated right-clicks.

No change to native Windows file menus, file operations, archive extraction,
Markdown parsing or VM/network policy is part of this release.

## Validation — 2026-09-20

- Full Linux headless suite passed: 179 unit tests (8 platform-dependent skips)
  and source/portable GUI checks, including the new context-settings regression.
- Windows 11 offline VM passed the portable regression: blank-area versus file
  routing, preserved selection, shared settings and INI, tab color/style/locks,
  repeated popup cleanup, three-level cascades at 100/150/300% in three themes.
- Native Windows visual checks used actual widget right-click bindings for the
  blank-area Panel Counts and tab Tab Style menus at 150%.
- Validated portable SHA-256:
  `218254b5ebc764ce9ad070dffe9e02897b999efa33aac26e4a6ce85999165275`.
