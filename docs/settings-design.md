# PFC Settings — v0.18.1

## Information architecture

Outlook-inspired two-column options window: six persistent categories on the
left, grouped controls on the right, a scrolling content area and a fixed footer.
View offers the settings entry plus direct category entry points. Tools also
offers Settings. File operations remain commands in Files; its operation settings
entry opens Paths & Operations. The previous menu models are retained for
contextual shortcuts, not duplicated as a second preference store.

| Category | Contents | Scope |
| --- | --- | --- |
| Appearance | Theme, auto/manual font scale, text sample, screenshots | Application |
| Layout & Tabs | 1–4 panels, tab shape, layout diagram, style screenshots | Application |
| File Columns | Hidden/system/extensions; sorting, marquee; overlays; visible columns, size emphasis, date/time | Name visibility: original tab; other settings: all tabs |
| Paths & Operations | Native/PFC right-click mode, recycle/error policy, three custom prefix slots | Application |
| Preview | Extension Effect and explanation of existing reading tools | F3 Preview |
| General | UI language and Windows sign-in startup | Application / Windows account |

Per-tab color/lock, per-pane List/Folder/File mode, favorites, recent folders and
document-specific preview tools stay next to their content; these are not silently
converted into global preferences. Expand All remains a bounded, cancellable tree
action, not a global recursive-scan option. Help retains manual Check Update.

## Interaction and safety

- Opening the dialog does not write INI, change Windows startup, query the network
  or capture personal files. The original active tab is retained for local options.
- Draft variables and prefix entries survive category switching. Cancel/close/Esc
  discard unapplied changes. Apply updates the existing application methods and
  sets a new baseline; Cancel after Apply does not undo an already applied choice.
- Prefix paths are validated before any changes are applied. Empty paths disable
  a slot. Browse only changes a draft. No new folder indexing is introduced.
- Windows startup is disabled on non-Windows systems. Only changing and applying
  that setting invokes the existing startup integration. Its policy warning is
  explicit; opening Settings never invokes it.
- File shortcuts are blocked at the dialog toplevel so F7/Delete/etc. cannot act
  on the file list behind Settings. Native entry editing and Tab navigation stay
  available. Focused controls are scrolled into view. Ctrl+Enter accepts.
- Individual settings apply through existing handlers, not a filesystem/system
  transaction; an unexpected apply error is shown, and prior successful changes
  may already be persisted. Cancel is not a rollback for applied settings.

## Visual design

- Appearance and Layout keep the comparison outside and above the scrolling
  controls. Current and draft details are visible immediately, and do not scroll
  away while choosing options. Compact label/control rows avoid excess vertical
  whitespace. The default window is 1180×720, bounded by the screen.
- Stable independent 14–18 pixel dialog fonts avoid controls moving under the
  pointer after global zoom changes. Apply/Cancel/OK remain in a fixed footer.
- All categories and new explanations are translated into English, Traditional
  Chinese, Simplified Chinese and Korean. The dialog rebuilds after language Apply.
- Current / After Apply screenshots are real PFC widget captures using a temporary
  demo fixture. They show theme and tab shape at a fixed 100% scale. They are not
  represented as the user's folders or live screenshots of a pending layout.
- Nine theme/shape combinations are embedded in the portable build (~265 KB base64),
  with responsive 360×150 detail crops (smaller in narrow dialogs) and a
  keyboard-accessible window comparing both original 540×210 screenshots together.
  Narrow screens stack the full-size pair; scrollbars keep both reachable without
  placing the window off-screen. Unchanged preview images are reused. Runtime needs
  only Tk, not Pillow or a screenshot API. Rebuild with
  `xvfb-run -a python3 tools/build_settings_shots.py`.
- The text sample is labeled "File text after Apply · 175%" (for example), uses
  the same base pixel calculation as the main app and reserves maximum sample
  height to prevent jumping controls. Auto sizing is explicitly labeled a reference,
  not a prediction: its eventual scale depends on actual window/panel widths.
- Both current and draft layout diagrams show relative widths and shared tabs
  in single-panel mode, directly under their style screenshots.
- Column settings give a real formatter-based date/time example and a OneDrive
  status legend; missing status is not misrepresented as successful synchronization.
- Scope/help now precedes or directly follows the relevant option on all six
  pages. Hidden Size/Date columns disable subordinate display controls but retain
  their values. Turning Recycle Bin off immediately shows a red permanent-delete
  warning. F3 Extension Effect explains syntax colors/Markdown vs source mode.
- Wheel gestures over closed combos scroll the options instead of silently
  changing a draft, including custom prefix icons. Native popdown fonts remain
  stable even when the main app is at 300%.
- All Settings checkboxes use a supersampled tick instead of the Clam theme's X.
  Enabled/checked is an accent tile with a contrasting tick, unchecked is an empty
  outlined box, and disabled states are muted without losing their saved tick.
  Native mouse/Space/focus semantics remain. Four application-owned images are
  reused across Apply/reopen; other application checkbox styles are unchanged.

## UI/UX review and regression evidence

1. Functional review: no-change open/cancel, multi-category drafts, Apply then
   Cancel, per-tab visibility vs global columns, INI, prefix validation, automatic
   font-mode dependencies, context-menu reuse, language changes and hotkey isolation.
2. Visual review: v0.17.27 put small thumbnails after the controls, which hid them
   below the initial viewport. v0.18.1 moves larger details to a fixed top area,
   with a paired full-size inspector and explicit font-sample purpose. Regression
   checks assert preview placement/width, stable image reuse, sample pixel size,
   fixed comparison during scrolling and an accessible options area in a compact
   780×560 dialog at 100/150/300%, across three themes. A separate 175% visual
   check matches the user's reported scenario. Four languages are covered.
3. Windows native review: verified the English appearance page and Traditional
   Chinese dark-theme layout page at 150%. This caught a context-sensitive
   translation collision ("Current" meant current folder elsewhere) and stale
   English panel-count choices after language switching; both were corrected and
   the final localized screen was rechecked. Enlarged-preview focus restoration,
   explicit Tab/Shift+Tab traversal, native-popdown global shortcut isolation and
   Ctrl+wheel interception are covered by the focused regression.

The auto-font baseline is read after computing the actual auto scale, avoiding
stale disabled percentages. Prefix icon previews reuse their image when only path
text changes. Main menu indicator metadata is cleared when replacing old check
items with settings category commands, preventing stray check marks.

This is an implementation/interaction review, not an external user study or a
screen-reader certification. Screenshot examples stay at 100%; they are not a
pixel-exact prediction of font scaling or native Explorer context menus.

Primary regression: `tools/settings_check.py` against both package and generated
portable app. Existing three-level menu tests now exercise the retained contextual
menu path; the main menu is deliberately flat category entry points.

### Original v0.17.27 validation

Windows offline validation passed for Settings, contextual shortcuts and
column menus (all exit 0), including enlarged preview, auto sizing, modal keyboard
isolation and localized layout. Tested portable v0.17.27 SHA-256:
`8dc9ed7cdbeaf77229a0e4848568fa95841f24b457516332a9e27d8a25f63879`.
VM lease released immediately afterward; host confirmed disk hibernation and
network disabled. No Windows account/password or startup policy changes were made
by these isolated tests.

The complete `tools/run_headless_checks.sh` suite passed (201 unit tests,
8 platform skips, package/portable GUI regressions). Final Settings-specific
package and portable tests were repeated after the keyboard/translation refinements.
`git diff --check` and compilation also passed.

### v0.18.1 validation — 2026-09-23

- Expanded `settings_check.py` passes for both source and portable builds: six
  categories, draft/cancel/apply, original-tab scope, prefix validation, four
  languages, three themes × 100/150/300%, image reuse, full-size pair, column
  dependencies, wheel protection and compact viewport geometry.
- Offline Windows 11 ARM64 passes the portable Settings and contextual-shortcut
  regressions (both exit 0). Reviewed native 175% default and 780×560 appearance
  screens plus Traditional Chinese compact dark Layout & Tabs. Fixed comparisons,
  sample labels, layout diagrams and footer are visible without overlap.
- Inspected English/Traditional Chinese File Columns, Paths & Operations, Preview
  and General at 900×650, including lower scrolled options. Scope and safety notes
  are next to their controls; no extra indexing, update or startup behavior added.
- Tested Windows portable SHA-256:
  Initial comparison review:
  `e35654ad0630842b84ca0e985a60d74d1de02b62760501ff502ddd0aba9a9bc9`.
  Isolated temporary INI and startup/tray stubs prevent test changes to Windows
  account policy. VM network remained off throughout.
- The full headless suite passed (227 unit tests with 8 platform skips and 62 GUI
  invocations). After the additional checkmark request, all 230 unit tests
  (8 platform skips), source/portable Settings tests and portable contextual
  Settings tests passed again. Pixel regressions verify tick geometry rather than
  an X, four distinct states, antialiased edges and bounded byte-cache reuse.
- Final checkmark build also passes Windows portable Settings and contextual
  regressions (exit 0), including Space-key toggling and image reuse on Apply.
  Native light/dark screenshots at 175% confirm checked, empty and disabled-tick
  states. Final portable SHA-256:
  `f92e6d28a91803889b7c8866445adb46d3129e2a008d9ce878d98f26e2aff71c`.
  Both validation leases were released immediately after their checks, with the
  network disabled and disk hibernation managed by the VM pool.
