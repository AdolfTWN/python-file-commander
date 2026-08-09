# Python File Commander

Current version: **v0.16.5 — Solid VCS Status Badges**

A dependency-free Python/Tk GUI inspired by Double Commander's familiar multi-panel workflow. It is intended for restricted office computers where Python is permitted but downloaded executables are not.

## Run

Requires Python 3.10+ with Tk support:

```powershell
python run.py
```

On Windows, `python pfc.py` automatically hands the GUI to the matching `pythonw.exe` and exits the console process, leaving one taskbar app. If `pythonw.exe` is unavailable, PFC safely falls back to hiding only a private console. Direct `pythonw pfc.py` remains supported.

On Ubuntu, install Python with Tk and optionally 7-Zip support, then launch the same file:

```bash
sudo apt install python3 python3-tk p7zip-full
python3 pfc.py
```

ZIP browsing uses Python's standard library. Editable 7z browsing uses an installed `7z`, `7zz`, or `7za` command.

For transfer to a restricted office computer, copy only
`pfc.py` plus `pfc.ini` and run:

```powershell
python pfc.py
```

The portable file is generated from the maintainable package source:

```powershell
python tools/build_single_file.py
```

Current core: two resizable panels by default, optionally three or four through View > Panel Counts, color-customizable and lockable tabs, drive/path navigation, marked column sorting, native Windows Shell file-type icons, multi-select, inline rename or Multi-Rename (F2), popup viewer (F3), background file search (F4), copy (F5), move (F6), inline new-folder creation (F7), Folder Compare/Safe Sync (F9), safe Recycle Bin delete (Del), explicit permanent delete (Shift+Del), Quick Filter (Ctrl+Y), and refresh (Ctrl+R). Git/SVN status overlays propagate to a repository root shown in its parent folder, so clean or changed projects are visible before entering them; Git clean state also reflects locally known upstream ahead/behind divergence without performing a network fetch. Each panel has a path-side view button cycling through List, Folder Tree, and File Tree modes; tree branches expand in place without leaving the current root. Tab cycles through every visible panel. From P2-P4, F5/F6 and F9 target the adjacent panel on the left; P1 targets P2. The action bar always shows the exact destination. Right enters a folder, Left returns to its parent, and Ctrl+Up duplicates the current folder into a new tab. Page Up/Down keeps the selection bar, keyboard focus, and visible row synchronized. Drag a tab with the mouse to reorder it or move its complete session to another visible panel; every panel retains at least one tab and the resulting order is saved immediately. Right-click a tab to choose its persistent color and lock mode. A locked tab opens navigation in a new tab; "Lock (open folder is allowed)" resets to its locked path after switching away or restarting. Panel count and every panel's tab-specific order, colors, locks, and Quick Filters are saved in `pfc.ini`.

Right-click a file or folder for a compact menu of frequent operations: open, open folder in a new tab, Run as Admin for supported Windows executables/scripts, Folder Space Analyzer, preview, compare, clipboard actions, paste into the clicked folder, copy/move to the displayed target panel, rename/multi-rename, copy path, and both delete modes. Right-click preserves an existing multi-selection; Shift+F10 or the Menu key opens the same menu from the keyboard. Disabled entries clearly indicate operations that need one item, two items, or a folder.

Copy, move, and clipboard paste detect name conflicts and offer Replace, Skip, Keep Both, Cancel, and Apply to All. Multi-item operations open a copyable result window listing exact failed paths with Retry Failed. The file context menu includes Run as Admin for supported Windows executables/scripts, ZIP compression, ZIP/7z extraction with asynchronously calculated folder/file counts, CMD/PowerShell shortcuts opened at the clicked location, and creation of native shortcuts placed on the clipboard as a cut operation. Search, compression, extraction, update download, and archive opening show smooth progress with an estimated remaining time; archive work runs outside the UI thread. ZIP/7z extraction writes directly to its checked destination to avoid Windows long-path failures caused by a second temporary copy. Files > Continue After File Errors controls whether remaining items continue after a failure and defaults on. The Files menu groups clipboard operations, target-panel operations, rename/new folder, both delete modes, safety switches, Favorites, Recent Folders, Preview, Search, Compare, paths, and Exit.

Favorites and the 20 most recent folders are stored in `pfc.ini`. Ctrl+D adds/removes the current folder, Ctrl+B opens Favorites, and Ctrl+Shift+R opens Recent Folders. All entries are also available from the Files menu.

Internal drag-and-drop copies selected items by default; holding Shift changes the action to Move. Drop onto the other visible panel to use its current folder, or onto any visible folder row to use that folder. A floating action/count/destination card follows the pointer and folder targets are highlighted. Drops reuse PFC's conflict, partial-failure, and recovery handling. Native Windows Shell integration also accepts files and folders dragged in from File Explorer (Copy by default, Shift+drop to Move) and exports selected PFC items to File Explorer with standard Windows Copy/Move modifier behavior. Outlook and Teams virtual attachments can be dragged directly into a PFC panel or pasted with Ctrl+V.

ZIP and 7z files open like folders with Enter, double-click, or Right. Their contents use the normal PFC copy, paste, move, rename, new-folder, and delete workflows. PFC extracts to an isolated workspace and safely replaces the original archive after each successful change; deletion inside an archive is explicitly confirmed because it cannot use the Recycle Bin. Left at the archive root returns to the containing folder and restores the selection to the archive.

Large ZIP and 7z files are prepared in the background. A visible progress window can cancel opening while the main PFC window remains responsive.

Files > Folder Space Analyzer opens an interactive proportional treemap for the active folder. Block area represents actual disk usage; click an item to locate it in PFC, double-click a folder to analyze it, and use Back, Parent Folder, Stop, or Analyze for navigation and control. The same analyzer is available from the file/folder context menu.

The Files menu uses the native accelerator column so actions remain left-aligned and hotkeys right-aligned at every font scale. The Versions header menu (Alt+H) opens one concise, bulleted changes window per version series. Its separate `Yoda — Portable App Advocate` item identifies Yoda as the advocate who helped bring this portable app into being, asks users to report problems, and reminds them to use file operations carefully. Version bumps are reserved for meaningful feature milestones instead of individual visual refinements.

View > Tab Style provides Right Skirt (default), Rounded, and Squarish. All three use the same height at every font scale. Right Skirt has a vertical left edge and steep curved bottom-right skirt; Rounded curves only the top corners and keeps a square bottom. The selection applies immediately to all main panels and Compare tabs and is saved in `pfc.ini`; legacy Compact settings migrate automatically to Right Skirt.

View > UI Language provides English (default), Traditional Chinese, Simplified Chinese, and Korean. Language names are shown in their native scripts, and file-management terms follow each platform language's familiar conventions. The selection is saved in `pfc.ini` and applies immediately—without restarting—to the main window and any open Preview, Search, Compare, or Multi-Rename window.

On Windows, PFC uses Segoe UI for the interface, Cascadia Mono or Consolas for fixed-width content, and the best available process DPI-awareness mode for smoother text on scaled and mixed-DPI displays. Ubuntu uses the first available native Ubuntu, Noto, or DejaVu family. Navigation, general file operations, in-app copy/cut/paste, file opening, and the FreeDesktop Trash are supported; Windows Shell icons, Outlook attachment formats, and Explorer drag integration remain Windows-specific.

Versions > v0.x.x Changes opens a large, resizable release-notes window. Its heading, description text, and controls follow the selected UI font size and update with live language changes.

F4 opens a reusable, cancellable background Search window with semicolon-separated wildcard/partial-name masks, file-content and Office XML search, case sensitivity, current/limited/all folder depth, file/folder type controls, minimum/maximum KB and modified-within-days filters. A live criteria summary and Clear Filters action make retained searches explicit. Results stream into sortable detail columns and support Enter/double-click Go to File, F3 Preview, multi-selection Copy Path, comparing two selected results, and sending the complete current result listing to a new panel tab. Search geometry and common criteria persist in `pfc.ini`; results are limited to 10,000 to protect responsiveness.

F3 opens a reusable popup viewer with Esc close, Auto/Text/Hex modes, text wrapping, two-second auto-refresh, File <</>> navigation, case-sensitive content search, Find Prev/Next navigation, encoding and truncation details, and a full-path status bar. With View > Extension Effect enabled (the default), Python and popular code/config formats receive syntax colors, while Markdown supports both highlighted source and a readable rendered mode. Its responsive three-row toolbar remains usable at narrow widths. Preview geometry and wrapping preference are saved in `pfc.ini`.

Additional shortcuts: Ctrl+W closes a tab, Ctrl+A selects all, Ctrl+Shift+C copies the first selected path or current folder, F11 copies every selected full path as newline-separated text, and Ctrl+H toggles hidden files. F12 focuses and selects the current path for direct paste-and-Enter navigation; a pasted file path opens its parent folder and places the selection bar on that file.

Every panel keeps an always-visible Quick Filter at its bottom. Ctrl+Y focuses the active panel's filter for immediate typing. The active panel instantly hides non-matching names; Enter returns to the file list and Esc or the × button clears the filter without hiding it. Filter text is stored with each tab in `pfc.ini`.

`View > File/Folder Mix Sorting` is enabled by default so files and folders share the selected column order. Disable it to keep folders grouped before files.

F2 opens Multi-Rename when two or more items are selected. `[N]`, `[C]`, and `[E]` masks, find/replace, case matching, counter start/digits, and extension preservation update a live Old/New/Status preview. Invalid names, duplicates, and existing targets block execution. Batch renames use temporary names so swaps are safe, roll back on failure, and Ctrl+Z restores the last successful batch in the current session.

Keyboard navigation is end-to-end: Tab switches panels, Ctrl+Tab and Ctrl+Shift+Tab cycle the active panel's tabs, Ctrl+L focuses the path, Esc returns to the file list, Alt+F/Alt+V open the header menus, and F1 (or clicking the Python File Commander header) opens the built-in keyboard guide.

The dark application header keeps the PFC window visually distinct. Its right side shows a compact two-second clipboard preview: up to three overlapping native file/folder icons, the first item's shortened name, and the remaining file/folder count. Outlook attachments use overlapping document icons; text shows only its UTF-8 byte size, while unsupported formats show `OBJ`. Busy clipboards keep the last useful summary instead of interrupting work.

View > File Visibility > Show File Extension is enabled by default. Turning it off hides only the final suffix in the Name column (for example, `archive.tar.gz` becomes `archive.tar`) while the Ext column remains unchanged. The setting is saved per panel. Buttons and menu items throughout the main, Preview and Compare windows show concise help after a five-second hover.

Ctrl+C, Ctrl+X, and Ctrl+V use the native Windows file clipboard, so files and folders can be copied or moved between PFC, its panels and tabs, and Windows File Explorer. Ctrl+V also accepts Outlook's virtual attachment clipboard (`FileGroupDescriptorW`/indexed `FileContents`) and materializes one or multiple attachments into the active folder before applying PFC's normal conflict policy. The header identifies the first attachment and any remaining attachment count instead of the generic `OBJ`.

F9 stages one selected file or folder as a visible Compare Target; selecting a second item and pressing F9 compares the pair. Two items selected together compare immediately, while no selection compares the two current panel folders. File modes retain aligned text with source-accurate line numbers, CSV/TSV tables, binary hex with SHA-256, search, and two-second auto-refresh. Folder Compare uses the same synchronized left/right panels, movable central difference map, difference navigation, search, and status hierarchy as file comparison. It accepts folders, ZIP files, and 7z files in any folder/archive pairing; archives are safely opened read-only and use content matching by default. It scans in the background with Esc cancellation, Recursive, semicolon masks, optional exact content hashing, and a default-on Text equivalent mode that ignores BOM, line-ending, trailing-space, Unicode-composition, and invisible-control representation differences without ignoring actual words or punctuation. Results remain sortable as Left only/Right only/Different/Identical/Left newer/Right newer, with Beyond Compare-style Diffs presets, Set Base Folder, Expand/Collapse All, Swap Sides, and content Find/Case sensitive controls. Ctrl+Right, Ctrl+Left, and Space assign Copy →, ← Copy, or Skip to selected rows. `Dry Run & Sync` displays every planned operation and requires confirmation; v0.9 only copies selected directions through PFC's existing conflict/error engine and never automatically deletes files. Double-click or Enter on a paired file opens a reusable nested tab in the same comparison session, using the exact standalone file-comparison UI and logical folder/archive paths. Esc closes the nested tab and returns to Folder Overview.

Visible folders auto-refresh adaptively: every 2 seconds while PFC is focused, every 10 seconds in the background, and every 5 seconds for UNC network paths. A lightweight signature prevents unnecessary Treeview rebuilds, while Ctrl+R remains available as a manual fallback.

`View > File Visibility` independently shows or hides Hidden and Windows System files. Both are hidden by default.

`View > Font Size > Auto Font Size` is enabled by default and selects Small, Medium, Large, or Huge from the current window height and available width per visible panel. Choosing a size manually turns Auto Font Size off. Fonts, the in-client application header and menus, tab geometry, path controls, row heights, native Shell icons, and the icon gutter scale and reflow together. Both the switch and current choice are saved in `pfc.ini`. The Windows-controlled native title-bar font follows the operating system DPI setting rather than an individual Tk application setting, so PFC keeps native window controls and provides its scalable title/menu header immediately below them.

All persistent state is kept in the single `pfc.ini` beside `pfc.py`. If it is absent, PFC creates it with safe defaults on first launch. It is updated after navigation, tab, sorting, display, active-panel, hotkey, and window changes so tabs and paths survive an unexpected shutdown. Hotkeys can be changed in its `[hotkeys]` section.

`Versions > Check Update` checks the project's GitHub `main` copy for a newer portable `pfc.py`. PFC applies a timeout and size limit, validates its declared version and Python syntax, asks before updating, atomically replaces the local script, then closes the old process and launches the new copy.

> File operations use your current account permissions. Del uses the Windows Recycle Bin or Ubuntu FreeDesktop Trash by default; Shift+Del always shows an irreversible permanent-delete warning. Network locations are never silently treated as safely recyclable.

## Scope and roadmap

The original project is a mature Pascal application with a large plugin ecosystem. This is a clean-room Python implementation of the workflow, not a line-by-line port.

### v1.0 readiness, in ROI order

1. **Completed in v0.8.1 — Safe delete to Windows Recycle Bin**, with permanent delete kept as an explicit secondary action.
2. **Completed in v0.8.1 — Copy/move/paste conflict handling**: Replace, Skip, Keep Both, Cancel, and Apply to All.
3. **Completed in v0.9.0 — Quick in-panel filter** that narrows the current file list while typing, separate from the deeper F4 search.
4. **Completed in v0.8.1 — Favorites and recent folders**, fully keyboard accessible.
5. **Completed in v0.8.1 — Partial-failure reporting and recovery** with continued processing, exact failed paths, copyable diagnostics, and retry.
6. **In progress — Release reliability gate** covering long paths, UNC/network folders, denied permissions, non-ASCII names, links, disconnected drives, large folders, clipboard contention, and interrupted settings writes. Automated coverage now includes non-ASCII conflicts, same-folder safety, partial failures, atomic default INI creation, and portable privacy; environment-dependent Windows cases remain release smoke tests.
7. **Privacy-safe portable handoff**: a documented clean-start workflow and validation that `pfc.py` contains no repository URL, account name, or local user path. Do not share a personal `pfc.ini`, because it intentionally stores folder and tab history.

Items 1–5 are complete. Promote to **v1.0.0** only after item 6 passes and no high-severity data-loss or keyboard-navigation defect remains.

Low-ROI features deferred until the office workflow is complete:

- Total Commander binary plugin compatibility (WCX/WDX/WFX/WLX): ABI hosting and crash isolation are disproportionately complex.
- Embedded FTP/SFTP/WebDAV clients: security, credential storage, protocol edge cases, and network policy make this poor early scope.
- Virtual file systems and privileged/admin operations: restricted office accounts typically cannot use the benefit.
- Full internal editor, syntax highlighter library, and media/thumbnail codecs: existing associated apps cover the common workflow.
- A full multi-rename scripting DSL and content-plugin columns: v0.9 includes the high-ROI preview/mask/undo subset without plugin complexity.
- Pixel-perfect desktop-integration parity across Windows and Ubuntu: platform-specific Shell capabilities remain native to each operating system.
- Lua scripting and third-party plugin SDK: ecosystem work should follow a stable core API.

These are deferred, not declared impossible. "100%" functional parity would require defining plugin/protocol/platform compatibility and is a multi-year product effort rather than a mechanical language conversion.

## License note

This repository currently contains newly written code and does not copy Double Commander source. If GPL-2.0 Double Commander code is later translated or incorporated, the combined distribution must comply with GPL-2.0.
