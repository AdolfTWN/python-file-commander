# Python File Commander

Current version: **v0.18.2**

Windows folder icons are cached per path, so Downloads, Documents, OneDrive and
ordinary folders keep their own Shell icons after navigation and font zoom.
The cache is bounded; displayed rows retain their images independently, including
Git/SVN and OneDrive badges.

**Compact workflow tools:** Ctrl+Shift+P searches commands and Settings. Tools
holds named Workspaces and Saved comparisons; F9 adds source-safe text editing,
inline differences, exclusion rules and HTML/text reports. Rendered Markdown's
Reading menu adds bookmarks and reading-position restore. There is no drive index
or automatic sync. See the [eight-feature guide and safety limits](docs/workflow-upgrade.md).

Preferences are now grouped in **View → PFC Settings** (also in Tools), with
Appearance, Layout & Tabs, File Columns, Paths & Operations, Preview and General.
Changes remain drafts until Apply/OK; Cancel discards only unapplied changes.
Appearance keeps larger current/draft style details visible above the scrolling
controls, with a paired full-size comparison. The font sample states its applied
percentage (or auto-size reference); Layout & Tabs compares panel diagrams too.
Scope, dependencies and safety notes sit beside their options. Enabled settings
use checkmarks, with distinct off/disabled states. Contextual shortcuts remain available. See the
[settings design and validation](docs/settings-design.md).

Windows automatically recovers an offscreen PFC window after startup, monitor
removal or resume. Valid secondary-monitor positions and deliberately minimized
windows are preserved; an unreachable window is centered in the primary work area.

**View → Layout & Tabs → Panel Counts → 1 Panel** provides a full-width
shared tab strip above a roughly 1/3 folder tree and 2/3 file list. Original panel
groups are preserved for switching back, new tabs belong to P1, and F5/F6/F9 ask
for explicit targets. Folder expansion is lazy and bounded, with no drive-wide
index. The current folder and its ancestors open by default; expanded rows have
no collapse symbol, while unopened branches retain their expand control.
Fine dotted hierarchy lines and antialiased folder/drive icons follow zoom,
scrolling and the current color theme. Icons sit on the branch joints, with child
connectors descending from each parent. See [one-panel behavior and limits](docs/single-panel.md).
**Expand All**, beside Folders, starts off and expands only the current folder's
descendants in bounded background batches. Uncheck to stop; changing folders,
refreshing or leaving one-panel mode also stops expansion. Existing expanded
branches stay open. Links/reparse folders are not traversed automatically.
Double-click a folder's text, icon or connector area to expand/collapse it.
Manual collapse survives background saving and cancels Expand All.
When scrolling hides parent folders, their icons and names remain pinned above
the tree, aligned with the hierarchy lines. Click one to return to it; scrolling
back restores the normal rows. Every ancestor is shown directly, with denser
spacing and scaled context text/icons only when needed for very deep paths.
The active path's expanded levels load their immediate sibling folders in the
background at startup. Dotted lines connect actual branches and stop at the last
child; sorted merges retain selection and do not recursively scan other folders.

Right-click **blank file-panel space** for Panel Counts, Right Click Menu,
List/Folder/File view, File Columns (including restoring hidden columns), Font
Size and Color Scheme. File-row right-click still follows Explorer/PFC preference.
Right-click a **tab** for Tab Color, lock behavior and shared Tab Style; blank tab
bar space offers style and Workspaces. View-mode and zoom controls also accept right-click.
Shift+F10/Menu works on the focused tab bar and controls, or an empty file list.
These are shortcuts to existing main-menu settings, not separate preferences;
Tab Style, panel count, font and scheme remain application-wide. See
[context-menu details](docs/context-settings.md).

Tab Lock refinement: compact neutral badges replace heavy edge
strokes. A closed padlock means navigation opens a new tab; the large return
arrow with a small padlock means restore the locked path when leaving the tab.
Both use the same dark-grey tile in light themes and light-grey tile in dark
mode, scale with the font and sit close to the left edge. See
[the selected design](docs/tab-lock-design.md).

Right-click a file column header for its display options; click the heading to
change sorting. All column
settings, including restoration of hidden Ext/Size/Date Modified columns, are in
**View → File Columns**. Dates support YYYY/MM/DD or MM/DD/YYYY with 24-hour,
compact 12-hour (1136a / 0515p), or date-only display; preferences persist in INI.
Name controls Hidden/System, filename extensions, mixed sorting, scrolling and
OneDrive badges and a separate Git/SVN overlay switch. Windows HIDDEN attributes
are recognized as well as dot files.

OneDrive status is queried asynchronously from fast local Windows properties,
without reading file contents or intentionally hydrating placeholders. Square
top-left cloud badges remain distinct from round bottom-right Git badges. Missing
provider metadata stays unknown. See [column and overlay details](docs/file-columns.md).

Markdown preview includes read-only tasks, labeled callouts, a section menu and
folding, alongside pipe tables and literal frontmatter properties. Search reveals
folded matches; Select All/Copy includes their text. Ctrl+click follows **exact
local Markdown paths within the original document's folder**, with Back and no
index, recursive search or missing-link fallback. Reading/parsing runs in one
cancellable worker with timeout, memory limits and explicit source fallback.
See the [reading guide and restrictions](docs/markdown-preview-guide.md) and
[sample document](docs/markdown-preview-example.md). Cloud/reparse-linked targets
are conservatively refused; manually opening a cloud document may download it.
The compact zoom control keeps its menu
on the percentage without a down arrow. See the [TODO implementation and design
review](docs/ui-ux-review-2026-09-19.md) for boundaries and proposed tab/header improvements.

Large deletions run outside the UI thread and report live item progress plus an estimated remaining time.

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

Current core: two resizable panels by default, optionally three or four through View > Layout & Tabs > Panel Counts, color-customizable and lockable tabs, drive/path navigation, marked column sorting, native Windows Shell file-type icons, multi-select, inline rename or Multi-Rename (F2), popup viewer (F3), background file search (F4), copy (F5), move (F6), inline new-folder creation (F7), Folder Compare/Safe Sync (F9), safe Recycle Bin delete (Del), explicit permanent delete (Shift+Del), Quick Filter (Ctrl+Y), and refresh (Ctrl+R). Git/SVN status overlays propagate to a repository root shown in its parent folder, so clean or changed projects are visible before entering them; Git clean state also reflects locally known upstream ahead/behind divergence without performing a network fetch. Each panel has a path-side view button cycling through List, Folder Tree, and File Tree modes; tree branches expand in place without leaving the current root. Tab cycles through every visible panel. From P2-P4, F5/F6 and F9 target the adjacent panel on the left; P1 targets P2. The action bar always shows the exact destination. Right enters a folder, Left returns to its parent, and Ctrl+Up duplicates the current folder into a new tab. Page Up/Down keeps the selection bar, keyboard focus, and visible row synchronized. Drag a tab with the mouse to reorder it or move its complete session to another visible panel; every panel retains at least one tab and the resulting order is saved immediately. Right-click a tab to choose its persistent color and lock mode. A locked tab opens navigation in a new tab; "Lock (open folder is allowed)" resets to its locked path after switching away or restarting. Panel count and every panel's tab-specific order, colors, locks, and Quick Filters are saved in `pfc.ini`.

Right-click a local file or folder to open the native Windows File Explorer menu by default. **View > Paths & Operations > Right Click Menu** switches between File Explorer and PFC; Shift+F10 and the Menu key follow the same saved preference. There is no delayed hover menu. PFC's compact task menu keeps open/preview, clipboard, target-panel transfer, rename, and both delete modes directly visible. Compare, Folder Space Analyzer, compression, and extraction live under **Analyze & Archive**; Windows administrative, terminal, shortcut, and path actions live under **More Actions**. Archive workspaces and non-Windows platforms use the PFC menu because native Explorer is unavailable. F8 remains unbound.

Long names in file panels are clipped without rewriting their middle or shrinking the font. **View > File Columns → Name settings → Long Filename Scrolling** (on by default) scrolls only the focused selected row in the active file list. It holds the beginning for one second, moves left at 36 pixels/second at 100% font size (scaled with zoom), holds the ending for 1.5 seconds, and repeats. Icons, row height and other columns stay still. Editing, dragging, menus and leaving the list pause animation; offscreen or inactive rows do not animate. Turning scrolling off leaves names statically clipped with full-name hover help. Both new preferences are saved in the INI.

Copy, move, and clipboard paste detect name conflicts and offer Replace, Skip, Keep Both, Cancel, and Apply to All. Multi-item operations open a copyable result window listing exact failed paths with Retry Failed. The file context menu includes Run as Admin for supported Windows executables/scripts, ZIP compression, ZIP/7z extraction with asynchronously calculated folder/file counts, CMD/PowerShell shortcuts opened at the clicked location, and creation of native shortcuts placed on the clipboard as a cut operation. Search, compression, extraction, update download, and archive opening show smooth progress with an estimated remaining time; archive work runs outside the UI thread. ZIP/7z extraction writes directly to its checked destination to avoid Windows long-path failures caused by a second temporary copy. **Files > File Operation Settings > Continue After File Errors** controls whether remaining items continue after a failure and defaults on. The header follows five predictable areas: **Files** for file operations, **Go** for navigation and paths, **View** for presentation, **Tools** for preview/compare/analyze/native integration, and **Help** for updates and release information.

Favorites and the 20 most recent folders are stored in `pfc.ini`. Ctrl+D adds/removes the current folder, Ctrl+B opens Favorites, and Ctrl+Shift+R opens Recent Folders. All entries are also available from the Go menu.

Internal drag-and-drop copies selected items by default; holding Shift changes the action to Move. Drop onto the other visible panel to use its current folder, or onto any visible folder row to use that folder. A floating action/count/destination card follows the pointer and folder targets are highlighted. Drops reuse PFC's conflict, partial-failure, and recovery handling. Native Windows Shell integration also accepts files and folders dragged in from File Explorer (Copy by default, Shift+drop to Move) and exports selected PFC items to File Explorer with standard Windows Copy/Move modifier behavior. Outlook and Teams virtual attachments can be dragged directly into a PFC panel or pasted with Ctrl+V.

ZIP and 7z files open like folders with Enter, double-click, or Right. Their contents use the normal PFC copy, paste, move, rename, new-folder, and delete workflows. PFC extracts to an isolated workspace and safely replaces the original archive after each successful change; deletion inside an archive is explicitly confirmed because it cannot use the Recycle Bin. Left at the archive root returns to the containing folder and restores the selection to the archive.

Large ZIP and 7z files are prepared in the background. A visible progress window can cancel opening while the main PFC window remains responsive.

Tools > Folder Space Analyzer opens an interactive proportional treemap for the active folder. Block area represents actual disk usage; click an item to locate it in PFC, double-click a folder to analyze it, and use Back, Parent Folder, Stop, or Analyze for navigation and control. The same analyzer is available from the file/folder context menu under Analyze & Archive.

Header and context menus use a dedicated accelerator column so actions remain left-aligned and hotkeys right-aligned at every font scale. The Help header menu (Alt+H) opens one concise, bulleted changes window per version series. Its separate `Yoda — Portable App Advocate` item identifies Yoda as the advocate who helped bring this portable app into being, asks users to report problems, and reminds them to use file operations carefully. Validated changes receive a patch release so Check Update can obtain them.

View > Layout & Tabs > Tab Style provides Right Skirt (default), Rounded, and Squarish. All three use the same height at every font scale. Right Skirt has a vertical left edge and steep curved bottom-right skirt; Rounded curves only the top corners and keeps a square bottom. The selection applies immediately to all main panels and Compare tabs and is saved in `pfc.ini`; legacy Compact settings migrate automatically to Right Skirt.

On Windows, PFC enables **View > General > Auto Start when boot** the first time it runs. It registers only a per-user startup entry, so no administrator permission is required. While PFC is running, its icon is also available in the notification area with Open PFC, Auto Start when boot, and Exit PFC actions. Turning Auto Start off from either location removes the startup entry immediately and the choice stays off until it is enabled again.

View > General > UI Language provides English (default), Traditional Chinese, Simplified Chinese, and Korean. Language names are shown in their native scripts, and file-management terms follow each platform language's familiar conventions. The selection is saved in `pfc.ini` and applies immediately—without restarting—to the main window and any open Preview, Search, Compare, or Multi-Rename window.

On Windows, PFC uses Segoe UI for the interface, Cascadia Mono or Consolas for fixed-width content, and the best available process DPI-awareness mode for smoother text on scaled and mixed-DPI displays. Ubuntu uses the first available native Ubuntu, Noto, or DejaVu family. Navigation, general file operations, in-app copy/cut/paste, file opening, and the FreeDesktop Trash are supported; Windows Shell icons, Outlook attachment formats, and Explorer drag integration remain Windows-specific.

Help > v0.x.x Changes opens a large, resizable release-notes window. Its heading, description text, and controls follow the selected UI font size and update with live language changes.

Help > Check Update downloads and validates the latest portable `pfc.py` from this repository's public `main` branch before replacing the local script.

File-list sizes use compact whole numbers rounded half up, with the existing 1024-based conversion: kB and MB use normal text, GB is bold, and TB is bold red. The Size column fits its heading and contents, leaving the remaining width to Name. Date Modified values are right-aligned. Sorting and file operations still use the original byte counts, not rounded display values.

F4 opens a reusable, cancellable background Search window with semicolon-separated wildcard/partial-name masks, file-content and Office XML search, case sensitivity, current/limited/all folder depth, file/folder type controls, minimum/maximum KB and modified-within-days filters. A live criteria summary and Clear Filters action make retained searches explicit. Results stream into sortable detail columns and support Enter/double-click Go to File, F3 Preview, multi-selection Copy Path, comparing two selected results, and sending the complete current result listing to a new panel tab. Search geometry and common criteria persist in `pfc.ini`; results are limited to 10,000 to protect responsiveness.

F3 opens a reusable popup viewer with Esc close, Auto/Text/Hex modes, text wrapping, File <</>> navigation, case-sensitive content search, Find Prev/Next navigation, encoding and truncation details. With View > Preview > Extension Effect enabled (the default), Python and popular code/config formats receive syntax colors, while Markdown supports highlighted source (up to 512 Ki characters) and rendered reading. Markdown has a compact additional reading row, background metadata refresh no more frequently than every five seconds while focused and without a text selection, and F5 manual refresh. Other preview formats retain their two-second refresh. Preview geometry and wrapping preference are saved in `pfc.ini`.

Additional shortcuts: Ctrl+W closes a tab, Ctrl+A selects all, Ctrl+Shift+C copies the first selected path or current folder, F11 copies every selected full path as newline-separated text, and Ctrl+H toggles hidden files. F12 focuses and selects the current path for direct paste-and-Enter navigation; a pasted file path opens its parent folder and places the selection bar on that file.

Every panel keeps an always-visible Quick Filter at its bottom. Ctrl+Y focuses the active panel's filter for immediate typing. The active panel instantly hides non-matching names; Enter returns to the file list and Esc or the × button clears the filter without hiding it. Filter text is stored with each tab in `pfc.ini`.

`View > File Columns → Name settings → File/Folder Mix Sorting` is enabled by default so files and folders share the selected column order. Disable it to keep folders grouped before files.

F2 opens Multi-Rename when two or more items are selected. `[N]`, `[C]`, and `[E]` masks, find/replace, case matching, counter start/digits, and extension preservation update a live Old/New/Status preview. Invalid names, duplicates, and existing targets block execution. Batch renames use temporary names so swaps are safe, roll back on failure, and Ctrl+Z restores the last successful batch in the current session.

Keyboard navigation is end-to-end: Tab switches panels, Ctrl+Tab and Ctrl+Shift+Tab cycle the active panel's tabs, Ctrl+L focuses the path, Esc returns to the file list, Alt+F/Alt+G/Alt+V/Alt+T/Alt+H open Files/Go/View/Tools/Help, and F1 (or clicking the Python File Commander header) opens the built-in keyboard guide.

The dark application header keeps the PFC window visually distinct. Its right side shows a compact two-second clipboard preview: up to three overlapping native file/folder icons, the first item's shortened name, and the remaining file/folder count. Outlook attachments use overlapping document icons; text shows only its UTF-8 byte size, while unsupported formats show `OBJ`. Busy clipboards keep the last useful summary instead of interrupting work.

View > File Columns → Name settings → Show File Extension is enabled by default. Turning it off hides only the final suffix in the Name column (for example, `archive.tar.gz` becomes `archive.tar`) while the Ext column remains unchanged. The setting is saved per panel. Buttons and menu items throughout the main, Preview and Compare windows show concise help after a five-second hover.

Ctrl+C, Ctrl+X, and Ctrl+V use the native Windows file clipboard, so files and folders can be copied or moved between PFC, its panels and tabs, and Windows File Explorer. Ctrl+V also accepts Outlook's virtual attachment clipboard (`FileGroupDescriptorW`/indexed `FileContents`) and materializes one or multiple attachments into the active folder before applying PFC's normal conflict policy. The header identifies the first attachment and any remaining attachment count instead of the generic `OBJ`.

F9 stages one selected file or folder as a visible Compare Target; selecting a
second item and pressing F9 compares the pair. Two selected items compare immediately;
no selection compares the current panel folders. Text comparison has read-only
aligned views, source line numbers and inline character differences. Edit Left/Right
opens original source with Undo, encoding/EOL preservation and conflict-checked save.
Text/CSV/TSV input is bounded to 2 MiB per side; large line sets use a labeled
positional comparison. Binary hex is a 256 KiB preview, not a full-file equality
claim. External refresh pauses while a text editor is open.

Folder Compare accepts folders, ZIP and 7z in any pairing; archive sides and nested
archive files stay read-only. Its background scan supports cancellation, masks,
exclusions and optional streamed SHA-256. **Rules** groups Recursive, By content,
Text equivalent and Exclusions. Text equivalent ignores representation differences
such as BOM, EOL and trailing space, not actual words. **Folders** holds base-folder,
expand/collapse and swap actions. Diffs filters, search and F7/F8 difference navigation
remain nearby. Ctrl+Right, Ctrl+Left and Space assign Copy →, ← Copy or Skip.
`Dry Run & Sync` confirms individually scanned files before background copying;
exclusions and child Skip are enforced, and no automatic deletion occurs. Cancel
stops after the current file. Enter/double-click opens a reusable nested comparison;
Esc returns to Folder Overview. **Session** stores named comparisons and exports
relative-path HTML/text reports. See [workflow limits](docs/workflow-upgrade.md).

Visible local folders refresh immediately from native Windows filesystem change events. A low-frequency signature audit recovers from rare missed or overflowed events, while UNC network paths use a five-second polling fallback. Ctrl+R remains available as a manual fallback.

`View > File Columns > Name` independently shows or hides Hidden and Windows System files. Both are hidden by default.

`View > Appearance > Font Size > Auto Font Size` is enabled by default and selects Small, Medium, Large, or Huge from the current window height, screen-width share, and available width per visible panel. A half-screen window stays at the native 100% size even on a high-DPI 5K display. Choosing a size manually turns Auto Font Size off. Fonts, the in-client application header and menus, tab geometry, path controls, row heights, native Shell icons, and the icon gutter scale and reflow together. Both the switch and current choice are saved in `pfc.ini`. The Ext detail column occupies four wide Latin characters; Size and Date retain bounded detail widths, and Name receives all remaining panel space. The Windows-controlled native title-bar font follows the operating system DPI setting rather than an individual Tk application setting, so PFC keeps native window controls and provides its scalable title/menu header immediately below them.

All persistent state is kept in the single `pfc.ini` beside `pfc.py`. If it is absent, PFC creates it with safe defaults on first launch. It is updated after navigation, tab, sorting, display, active-panel, hotkey, and window changes so tabs and paths survive an unexpected shutdown. Hotkeys can be changed in its `[hotkeys]` section.

`Help > Check Update` checks the project's GitHub `main` copy for a newer portable `pfc.py`. PFC applies a timeout and size limit, validates its declared version and Python syntax, asks before updating, atomically replaces the local script, then closes the old process and launches the new copy.

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
