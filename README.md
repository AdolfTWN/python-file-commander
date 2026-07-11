# Python File Commander

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

Current core: two resizable panes, chamfered color-customizable and lockable tabs, drive/path navigation, marked column sorting, native Windows Shell file-type icons with a compact left gutter and padded filename gap, multi-select, rename (F2), popup viewer (F3), recursive name search (F4), copy (F5), move (F6), new folder (F7), permanent delete (Del), and refresh (Ctrl+R). Right enters a folder, Left returns to its parent, and Ctrl+Up duplicates the current folder into a new tab. Right-click a tab to choose its persistent color and lock mode. A locked tab opens navigation in a new tab; "Lock (open folder is allowed)" resets to its locked path after switching away or restarting. Tab-specific colors and locks are saved in `pfc.ini`.

F3 opens a reusable popup viewer with Esc close, Auto/Text/Hex modes, text wrapping, two-second auto-refresh, File <</>> navigation, case-sensitive content search, Find Prev/Next navigation, encoding and truncation details, and a full-path status bar. Its responsive three-row toolbar remains usable at narrow widths. Preview geometry and wrapping preference are saved in `pfc.ini`.

Additional shortcuts: Ctrl+W closes a tab, Ctrl+A selects all, Ctrl+Shift+C copies the first selected path or current folder, F11 copies every selected full path as newline-separated text, F12 focuses and selects the current path for direct paste-and-Enter navigation, and Ctrl+H toggles hidden files.

Keyboard navigation is end-to-end: Tab switches panels, Ctrl+Tab and Ctrl+Shift+Tab cycle the active panel's tabs, Ctrl+L focuses the path, Esc returns to the file list, Alt+F/Alt+V open the header menus, and F1 (or clicking the Python File Commander header) opens the built-in keyboard guide.

The dark application header keeps the PFC window visually distinct. Its right side shows a compact two-second clipboard summary: file Copy/Cut state, item count and first filename, or a whitespace-normalized truncated text preview. Busy clipboards keep the last useful summary instead of interrupting work.

View > File Visibility > Show File Extension is enabled by default. Turning it off hides only the final suffix in the Name column (for example, `archive.tar.gz` becomes `archive.tar`) while the Ext column remains unchanged. The setting is saved per panel. Buttons and menu items throughout the main, Preview and Compare windows show concise help after a five-second hover.

Ctrl+C, Ctrl+X, and Ctrl+V use the native Windows file clipboard, so files and folders can be copied or moved between PFC, its panels and tabs, and Windows File Explorer.

F9 compares one selected item in each panel (or two items in the active panel) in a separate tabbed Compare window. Auto detection supports aligned text with source-accurate line numbers, CSV/TSV tables, binary hex with SHA-256, and recursive folder comparison. F7/F8 navigate with Diff <</>>. Ctrl+F, Find Prev/Next and Case sensitive search work in Text, Table, Binary and Folder comparisons with all/current-match highlighting. Esc closes the active comparison tab, or the window when only one tab remains. File comparisons auto-refresh every two seconds when either source changes; recursive folder comparisons avoid polling to protect performance. Main and Compare tabs use a shared high-contrast active-tab style.

Visible folders auto-refresh adaptively: every 2 seconds while PFC is focused, every 10 seconds in the background, and every 5 seconds for UNC network paths. A lightweight signature prevents unnecessary Treeview rebuilds, while Ctrl+R remains available as a manual fallback.

`View > File Visibility` independently shows or hides Hidden and Windows System files. Both are hidden by default.

`View > Font Size` provides Small (100%), Medium (150%), Large (200%), and Huge (300%). Fonts, the in-client application header and menus, tab geometry, path controls, row heights, native Shell icons, and the icon gutter scale and reflow together. The choice is saved in `pfc.ini`. The Windows-controlled native title-bar font follows the operating system DPI setting rather than an individual Tk application setting, so PFC keeps native window controls and provides its scalable title/menu header immediately below them.

All persistent state is kept in the single `pfc.ini` beside `pfc.py`. It is updated after navigation, tab, sorting, display, active-panel, hotkey, and window changes so tabs and paths survive an unexpected shutdown. Hotkeys can be changed in its `[hotkeys]` section.

> File operations use your current Windows permissions. Delete is permanent in this initial version.

## Scope and roadmap

The original project is a mature Pascal application with a large plugin ecosystem. This is a clean-room Python implementation of the workflow, not a line-by-line port.

High-value next steps: tabs and favorites, background operation queue with progress/cancel, safe Recycle Bin delete, quick search/filter, file viewer, directory comparison/sync, archive browsing, checksums, configurable shortcuts, and persistent settings.

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
