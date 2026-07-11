# Python File Commander

A dependency-free Python/Tk GUI inspired by Double Commander's familiar two-panel workflow. It is intended for restricted office computers where Python is permitted but downloaded executables are not.

## Run

Requires Python 3.10+ with Tk support:

```powershell
python run.py
```

For transfer to a restricted office computer, copy only
`pfc.py` plus `pfc.ini` and run:

```powershell
python pfc.py
```

The portable file is generated from the maintainable package source:

```powershell
python tools/build_single_file.py
```

Current core: two resizable panes, tabs, drive/path navigation, marked column sorting, native Windows Shell file-type icons with a compact left gutter and padded filename gap, multi-select, rename (F2), preview in the other panel (F3), recursive name search (F4), copy (F5), move (F6), new folder (F7), permanent delete (Del), and refresh (Ctrl+R). Right enters a folder, Left returns to its parent, and Ctrl+Up duplicates the current folder into a new tab. Preview tabs show the previewed filename.

Additional shortcuts: Ctrl+W closes a tab, Ctrl+A selects all, Ctrl+Shift+C copies the selected path, and Ctrl+H toggles hidden files.

F9 compares one selected item in each panel (or two items in the active panel) in a separate tabbed Compare window. Auto detection supports aligned text with source-accurate line numbers, CSV/TSV tables, binary hex with SHA-256, and recursive folder comparison. F7/F8 navigate differences. Esc closes the active comparison tab, or the window when only one tab remains. Main and Compare tabs use a shared high-contrast active-tab style.

Visible folders auto-refresh adaptively: every 2 seconds while PFC is focused, every 10 seconds in the background, and every 5 seconds for UNC network paths. A lightweight signature prevents unnecessary Treeview rebuilds, while Ctrl+R remains available as a manual fallback.

`View > File Visibility` independently shows or hides Hidden and Windows System files. Both are hidden by default.

`View > Font Size` provides Small (100%), Medium (150%), Large (200%), and Huge (300%). Fonts, menus, row heights, native Shell icons, and the icon gutter scale together. The choice is saved in `pfc.ini`. The Windows-controlled native title-bar font follows the operating system DPI setting rather than an individual Tk application setting.

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
