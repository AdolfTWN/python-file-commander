# Menu UI/UX dogfooding

Scope: the main header menus and the file/folder context menu. The goal is a shallow,
predictable hierarchy that remains usable across selection states, supported platforms,
four UI languages, and all five font scales.

## Round 1 — information architecture and frequent workflows

- Finding: Files mixed navigation, presentation-adjacent tools, clipboard, destructive
  actions, and Windows integration in one long flat menu.
- Finding: the context menu exposed almost twenty unrelated commands at the same level.
- Fix: split the header into Files, Go, View, Tools, and Help. Keep frequent operations
  visible and place only related, lower-frequency actions one level down.
- Fix: group context actions under Analyze & Archive and More Actions; keep destructive
  actions separated at the bottom. No action is more than one submenu deep.
- Evidence: `tools/gui_smoke_check.py` asserts exact main/sub hierarchy, accelerator
  retention, archive counts, and English/Traditional Chinese/Simplified Chinese/Korean
  labels.

## Round 2 — contextual state and boundary behavior

- Finding: Explorer Menu appeared actionable on non-Windows hosts and in archive
  workspaces, although no native Explorer menu could be shown.
- Fix: disable Explorer Menu in both header and context menus unless the active selection
  is local and PFC is running on Windows.
- Fix: update Open, Preview, Rename, Multi-Rename, clipboard, transfer, compare, and delete
  states for no selection, one item, and multiple items before a menu opens.
- Regression adjustment: Favorites and Recent Folders now open beneath their new Go
  parent while continuing to act on the active panel.
- Evidence: automated no-selection/single-file/multi-selection assertions plus
  `tools/header_popup_check.py` keyboard, pointer, cascade, and dismissal checks.

## Round 3 — visual density, scale, and localization

- Finding: the keyboard guide still described the old Files/View/Versions header after
  the hierarchy changed.
- Fix: the guide now documents Alt+F/G/V/T/H and the five current menu names in every
  supported language.
- Review: visually inspected the Traditional Chinese Files menu at manual 250% and the
  context menu at 150% in a 900x600 window. Separators, accelerator alignment, disabled
  contrast, submenu arrows, destructive grouping, and the clipboard header all remain
  legible without adding another hierarchy level.
- Evidence: popup geometry clamps to the virtual screen; localized GUI smoke checks and
  XXL popup row/indicator checks pass.
