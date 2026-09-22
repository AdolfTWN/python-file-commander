# PFC Settings — v0.17.27

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

- Controls appear before comparisons. Section headings have stronger weight;
  duplicate field/group headings are omitted. Stable independent 14–22 pixel
  dialog fonts avoid controls moving under the pointer after global zoom changes.
- All categories and new explanations are translated into English, Traditional
  Chinese, Simplified Chinese and Korean. The dialog rebuilds after language Apply.
- Current / After Apply screenshots are real PFC widget captures using a temporary
  demo fixture. They show theme and tab shape at a fixed 100% scale. They are not
  represented as the user's folders or live screenshots of a pending layout.
- Nine theme/shape combinations are embedded in the portable build (~265 KB base64),
  with responsive thumbnails and a keyboard-accessible enlarged view. Runtime needs
  only Tk, not Pillow or a screenshot API. Rebuild with
  `xvfb-run -a python3 tools/build_settings_shots.py`.
- The text sample represents the selected scale; layout diagrams explicitly show
  relative widths, with shared tabs in single-panel mode. Auto sizing is explained
  separately because its eventual scale depends on the actual window/panel widths.
- Column settings give a real formatter-based date/time example and a OneDrive
  status legend; missing status is not misrepresented as successful synchronization.

## UI/UX review and regression evidence

1. Functional review: no-change open/cancel, multi-category drafts, Apply then
   Cancel, per-tab visibility vs global columns, INI, prefix validation, automatic
   font-mode dependencies, context-menu reuse, language changes and hotkey isolation.
2. Visual review: early stacked full-size screenshots displaced settings; changed
   to controls-first, side-by-side thumbnails with full-size inspection. Removed
   duplicate headings, gave checkboxes independent indicator metrics and kept the
   footer outside the scroll region. Checked three themes and 100/150/300% app zoom
   in a compact 780×560 dialog, plus default large-window screenshots.
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

Final Windows offline validation passed for Settings, contextual shortcuts and
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
