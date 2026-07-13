# Python File Commander

Current version: **v0.8.7**

A dependency-free Python/Tk GUI inspired by Double Commander's familiar two-panel workflow. It is intended for restricted office computers where Python is permitted but downloaded executables are not.

## Run

Requires Python 3.10+ with Tk support:

```powershell
python run.py
```

On Windows, `python pfc.py` automatically hands the GUI to the matching `pythonw.exe` and exits the console process, leaving one taskbar app. If `pythonw.exe` is unavailable, PFC safely falls back to hiding only a private console. Direct `pythonw pfc.py` remains supported.

For transfer to a restricted office computer, copy only
`pfc.py` plus `pfc.ini` and run:

```powershell
python pfc.py
```

The portable file is generated from the maintainable package source:

```powershell
python tools/build_single_file.py
```

Current core: two resizable panes, color-customizable and lockable tabs, drive/path navigation, marked column sorting, native Windows Shell file-type icons with a compact left gutter and padded filename gap, multi-select, rename (F2), popup viewer (F3), background file search (F4), copy (F5), move (F6), new folder (F7), safe Recycle Bin delete (Del), explicit permanent delete (Shift+Del), and refresh (Ctrl+R). Right enters a folder, Left returns to its parent, and Ctrl+Up duplicates the current folder into a new tab. Right-click a tab to choose its persistent color and lock mode. A locked tab opens navigation in a new tab; "Lock (open folder is allowed)" resets to its locked path after switching away or restarting. Tab-specific colors and locks are saved in `pfc.ini`.

Copy, move, and clipboard paste detect name conflicts and offer Replace, Skip, Keep Both, Cancel, and Apply to All. Multi-item operations open a copyable result window listing exact failed paths with Retry Failed. Files > Continue After File Errors controls whether remaining items continue after a failure and defaults on. The Files menu groups clipboard operations, opposite-panel operations, rename/new folder, both delete modes, safety switches, Favorites, Recent Folders, Preview, Search, Compare, paths, and Exit.

Favorites and the 20 most recent folders are stored in `pfc.ini`. Ctrl+D adds/removes the current folder, Ctrl+B opens Favorites, and Ctrl+Shift+R opens Recent Folders. All entries are also available from the Files menu.

Internal drag-and-drop copies selected items by default; holding Shift changes the action to Move. Drop onto the other visible panel to use its current folder, or onto any visible folder row to use that folder. A floating action/count/destination card follows the pointer and folder targets are highlighted. Drops reuse PFC's conflict, partial-failure, and recovery handling. External Explorer/Outlook OLE drag-and-drop is not included.

The Files menu uses the native accelerator column so actions remain left-aligned and hotkeys right-aligned at every font scale. The Versions header menu (Alt+H) tracks user-visible changes and groups every v0.8.x release in one `v0.8.x Releases` submenu.

View > Tab Style provides Right Skirt (default), Rounded, and Squarish. All three use the same height at every font scale. Right Skirt has a vertical left edge and steep curved bottom-right skirt; Rounded curves only the top corners and keeps a square bottom. The selection applies immediately to both main panels and Compare tabs and is saved in `pfc.ini`; legacy Compact settings migrate automatically to Right Skirt.

F4 opens a reusable, cancellable background Search window with semicolon-separated wildcard/partial-name masks, file-content and Office XML search, case sensitivity, current/limited/all folder depth, file/folder type controls, minimum/maximum KB and modified-within-days filters. Results stream into sortable-style detail columns and support Enter/double-click Go to File, F3 Preview and multi-selection Copy Path. Search geometry and common criteria persist in `pfc.ini`; results are limited to 10,000 to protect responsiveness.

F3 opens a reusable popup viewer with Esc close, Auto/Text/Hex modes, text wrapping, two-second auto-refresh, File <</>> navigation, case-sensitive content search, Find Prev/Next navigation, encoding and truncation details, and a full-path status bar. Its responsive three-row toolbar remains usable at narrow widths. Preview geometry and wrapping preference are saved in `pfc.ini`.

Additional shortcuts: Ctrl+W closes a tab, Ctrl+A selects all, Ctrl+Shift+C copies the first selected path or current folder, F11 copies every selected full path as newline-separated text, F12 focuses and selects the current path for direct paste-and-Enter navigation, and Ctrl+H toggles hidden files.

Keyboard navigation is end-to-end: Tab switches panels, Ctrl+Tab and Ctrl+Shift+Tab cycle the active panel's tabs, Ctrl+L focuses the path, Esc returns to the file list, Alt+F/Alt+V open the header menus, and F1 (or clicking the Python File Commander header) opens the built-in keyboard guide.

The dark application header keeps the PFC window visually distinct. Its right side shows a privacy-safe two-second clipboard summary without content or filenames: UTF-8 string byte size, file/folder counts, `OBJ` for other formats, or `Empty`. Busy clipboards keep the last useful summary instead of interrupting work.

View > File Visibility > Show File Extension is enabled by default. Turning it off hides only the final suffix in the Name column (for example, `archive.tar.gz` becomes `archive.tar`) while the Ext column remains unchanged. The setting is saved per panel. Buttons and menu items throughout the main, Preview and Compare windows show concise help after a five-second hover.

Ctrl+C, Ctrl+X, and Ctrl+V use the native Windows file clipboard, so files and folders can be copied or moved between PFC, its panels and tabs, and Windows File Explorer. Ctrl+V also accepts Outlook's virtual attachment clipboard (`FileGroupDescriptorW`/indexed `FileContents`) and materializes one or multiple attachments into the active folder before applying PFC's normal conflict policy. The header identifies this content as `1 Attachment` or `N Attachments` instead of the generic `OBJ`.

F9 compares one selected item in each panel (or two items in the active panel) in a separate tabbed Compare window. Auto detection supports aligned text with source-accurate line numbers, CSV/TSV tables, binary hex with SHA-256, and recursive folder comparison. F7/F8 navigate with Diff <</>>. Ctrl+F, Find Prev/Next and Case sensitive search work in Text, Table, Binary and Folder comparisons with all/current-match highlighting. Esc closes the active comparison tab, or the window when only one tab remains. File comparisons auto-refresh every two seconds when either source changes; recursive folder comparisons avoid polling to protect performance. Main and Compare tabs use a shared high-contrast active-tab style.

Visible folders auto-refresh adaptively: every 2 seconds while PFC is focused, every 10 seconds in the background, and every 5 seconds for UNC network paths. A lightweight signature prevents unnecessary Treeview rebuilds, while Ctrl+R remains available as a manual fallback.

`View > File Visibility` independently shows or hides Hidden and Windows System files. Both are hidden by default.

`View > Font Size` provides Small (100%), Medium (150%), Large (200%), and Huge (300%). Fonts, the in-client application header and menus, tab geometry, path controls, row heights, native Shell icons, and the icon gutter scale and reflow together. The choice is saved in `pfc.ini`. The Windows-controlled native title-bar font follows the operating system DPI setting rather than an individual Tk application setting, so PFC keeps native window controls and provides its scalable title/menu header immediately below them.

All persistent state is kept in the single `pfc.ini` beside `pfc.py`. If it is absent, PFC creates it with safe defaults on first launch. It is updated after navigation, tab, sorting, display, active-panel, hotkey, and window changes so tabs and paths survive an unexpected shutdown. Hotkeys can be changed in its `[hotkeys]` section.

> File operations use your current Windows permissions. Del uses the Windows Recycle Bin by default; Shift+Del always shows an irreversible permanent-delete warning. Network locations are never silently treated as safely recyclable.

## Scope and roadmap

The original project is a mature Pascal application with a large plugin ecosystem. This is a clean-room Python implementation of the workflow, not a line-by-line port.

### v1.0 readiness, in ROI order

1. **Completed in v0.8.1 — Safe delete to Windows Recycle Bin**, with permanent delete kept as an explicit secondary action.
2. **Completed in v0.8.1 — Copy/move/paste conflict handling**: Replace, Skip, Keep Both, Cancel, and Apply to All.
3. **Background operation queue** with progress, cancel, retry, and a final success/failure summary so large file operations never freeze navigation.
4. **Quick in-panel filter** that narrows the current file list while typing, separate from the deeper F4 search. This is a frequent office workflow with low interaction cost.
5. **Completed in v0.8.1 — Favorites and recent folders**, fully keyboard accessible.
6. **Completed in v0.8.1 — Partial-failure reporting and recovery** with continued processing, exact failed paths, copyable diagnostics, and retry.
7. **In progress — Release reliability gate** covering long paths, UNC/network folders, denied permissions, non-ASCII names, links, disconnected drives, large folders, clipboard contention, and interrupted settings writes. Automated coverage now includes non-ASCII conflicts, same-folder safety, partial failures, atomic default INI creation, and portable privacy; environment-dependent Windows cases remain release smoke tests.
8. **Privacy-safe portable handoff**: a documented clean-start workflow and validation that `pfc.py` contains no repository URL, account name, or local user path. Do not share a personal `pfc.ini`, because it intentionally stores folder and tab history.

After items 1–6 are complete, the appropriate milestone is **v0.9.0**. Promote to **v1.0.0** only after item 7 passes and no high-severity data-loss or keyboard-navigation defect remains. Archive browsing, folder synchronization actions, and checksum tools remain useful post-v1.0 enhancements rather than release blockers.

Low-ROI features deferred until the office workflow is complete:

- Total Commander binary plugin compatibility (WCX/WDX/WFX/WLX): ABI hosting and crash isolation are disproportionately complex.
- Embedded FTP/SFTP/WebDAV clients: security, credential storage, protocol edge cases, and network policy make this poor early scope.
- Virtual file systems and privileged/admin operations: restricted office accounts typically cannot use the benefit.
- Full internal editor, syntax highlighter library, and media/thumbnail codecs: existing associated apps cover the common workflow.
- Multi-rename scripting DSL and content-plugin columns: powerful but uncommon for ordinary office multitasking.
- Cross-platform desktop integration parity and pixel-perfect theme engine: the target is the restricted Windows office machine.
- Lua scripting and third-party plugin SDK: ecosystem work should follow a stable core API.

These are deferred, not declared impossible. "100%" functional parity would require defining plugin/protocol/platform compatibility and is a multi-year product effort rather than a mechanical language conversion.

## License note

This repository currently contains newly written code and does not copy Double Commander source. If GPL-2.0 Double Commander code is later translated or incorporated, the combined distribution must comply with GPL-2.0.
