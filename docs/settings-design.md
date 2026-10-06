# PFC Settings — v0.18.4

## Stable auto reading scale — v0.18.18

Auto Font Size fits once when enabled or after settled external window width,
monitor/DPI or explicit panel/column layout changes. Folder/tab switches,
selection, scrolling, directory refresh and content-driven column autosizing
must neither sample filenames nor apply global fonts. Height-only resizing or
moving inside the same monitor is not a trigger. The fitting/verification uses
one snapshot (up to 30 rows in Panels 1–2, 100–300%); later long filenames keep
their scrolling behavior. Root Configure is debounced by 400 ms.

## Reading-scale controls — v0.18.17

PFC-owned checkboxes and radio buttons use retained high-resolution indicators
matched to the current font line height. Menu selections use readable check
marks rather than fixed-size native indicators. Text, dropdown arrows and
control padding follow the interface scale; open Settings, workflow and
comparison windows refresh their fonts too. Confirmation/error dialogs inherit
the same reading size and preserve the standard OK/Cancel/Yes/No semantics.

Settings keeps the preview at the scrollable page top. At constrained widths,
the category sidebar becomes a full-label dropdown rather than clipped text.
Preview diagrams grow with their text. Batch rename reserves its action footer
and abbreviates button labels only when necessary, with full shortcut tooltips.
Folder comparison path headers have stable requested widths: ellipsizing long
paths cannot feed back into pane geometry after a side swap.
Native Windows file/folder choosers and title bars remain controlled by Windows.
Settings and PFC confirmations fit the owning monitor's work area, reserving
space for the native frame and taskbar so enlarged footer actions stay usable.

Acceptance includes 100/150/175/200/300% changes with persistent windows,
all six Settings pages, keyboard selection, modal cancellation, bounded footer
geometry and original-size visual captures. Evidence belongs to the maintenance
trace; passing layout checks does not replace real-user usability feedback.

## Content-fit zoom and popup chrome review (v0.18.13)

Observable tasks: (1) enable Auto and read the sampled filenames without
marquee, resize and navigate without repeated scale oscillation; (2) set a search
query and its case/scope options in one place, then act on results; (3) find text
or differences in a comparison without confusing the two navigation groups.

Auto uses the displayed file list in One Panel, otherwise the visible lists of
Panels 1 and 2 only. It samples up to 30 displayed-order rows starting at the
viewport top, not 30 filesystem lookups. Closed branches and filtered-out entries
are excluded. Geometry, scrolling, tab/folder and column changes schedule a
debounced calculation. Candidate fonts are measured off-screen; the main UI is
changed only for the chosen scale, with bounded post-layout correction if needed.
The supported range is 100–300% in 25% steps. Overflow at 100% is unavoidable and
still uses the existing marquee. Empty lists retain the current scale. Panels
3–4 do not contribute filename constraints (their physical space still affects
Panels 1–2). Modal/draft settings temporarily suppress unsolicited recalculation.

The percentage is enlarged. The + and − hints are stacked above/below it, muted
at rest, raised on pointer approach or keyboard focus. Native button activation,
percentage menu, keyboard traversal and manual-mode behavior remain available;
hover never changes geometry.

| Popup family reviewed | Functional grouping / disposition |
| --- | --- |
| Search | Path + depth; name + file/folder scope; content + case; optional size/date filters expandable; results actions in one menu; progress/criteria at footer. |
| Text/binary/table Compare | Difference controls together; text search + previous/next + case on one row; compact glyphs retain tooltips/keyboard shortcuts. |
| Folder Compare | Difference navigation joins view/folder/map controls, separate from the text-search row; safety/sync controls remain in the footer. |
| Multi-Rename | Keep-extension belongs next to name template, case next to find/replace; counter settings stay together; template syntax in tooltip. |
| Space Analyzer | Parent/back, current folder, analyze/stop/locate in one toolbar; lengthy instructions moved to canvas tooltip. |
| Markdown discovery | Scope + depth together; query mode + query + Search together; explicit bounded-search notice retained. |
| Preview / Settings | Existing single-row find controls and scrollable preview/settings arrangement retained; do not remove the requested previews to save space. |
| Workspaces / saved comparisons / command palette / custom prefixes | Existing task-local form or single query with list; no fragmented search suboptions identified in source review. |
| Editor / conflict / dry-run / progress / operation report / Help / release notes | Existing single-purpose header; safety messages and confirmation controls retained rather than hidden for compactness. |

Self-review evidence: Search at 150%, 1100×760 reduced the top controls from
approximately 340 px to 177 px; the previous right-edge action clipping is gone.
This is headless visual evidence, not user acceptance or native Windows proof.
The Windows gate again reached QGA but returned `guest-exec-unavailable`; no
guest test ran, networking stayed disabled and the lease was released.

Validation: 289 unit tests (8 platform skips); the final settings/zoom group
passed all 17 checks, and the final portable chrome/Auto/hover matrix passed.
The broad inventory ran 87 checks: obsolete smoke-fixture assumptions were
updated and its final rerun passed. The existing `folder_leaf` source Right-key
timeout remains intermittent (portable and a serial diagnostic passed); the
complete inventory is therefore not claimed fully green. The saved-startup test
now restores native Tk scaling between in-process roots to model a real restart;
it no longer compounds the previous root's zoom. No product tree fix is claimed.

## Scaled-layout correction (v0.18.12)

This supersedes the fixed-top arrangement below: preview and options now share
one scrollable page at every scale; Apply/Cancel/OK remain fixed. Page switching
resets scrolling after layout settles, so old page heights cannot strand the new
preview above the viewport. Before/After cards stack when their headings and
diagrams cannot fit side by side. Option labels and comparison actions reflow
instead of consuming the remaining control width. Checkmark size follows text.

Self-review tasks: find both comparison states at 150%, switch all six pages
without losing their preview, reach the final setting and footer at 200%/narrow
width, and cancel without writing preferences. The source/portable GUI checks
cover scale/theme/language and compact geometry. Headless screenshots were
reviewed at actual display size. Windows VM validation is **blocked at guest
execution**, not passed; it must not be confused with the older native evidence
recorded below.

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
| Layout & Tabs | 1–4 panels, tab shape, whole-workspace Before/After illustrations | Application |
| File Columns | Hidden/system/extensions; sorting, marquee; overlays; visible columns, size emphasis, date/time | Name visibility: original tab; other settings: all tabs |
| Paths & Operations | Native/PFC right-click mode, recycle/error policy, three custom prefix slots | Application |
| Preview | Extension Effect and explanation of existing reading tools | F3 Preview |
| General | UI language and Windows sign-in startup | Application / Windows account |

### Fixed-top previews on every page (v0.18.3)

Appearance retains screenshot comparisons and the font sample. Layout uses
whole-workspace illustrations (see v0.18.4 below). The other four pages use code-drawn examples
above the scrolling controls, labeled **Preview · After Apply**:

- **File Columns:** a synthetic file list uses the actual size/date formatters.
  Hidden/system files, extensions, mixed sorting, column visibility, GB/TB
  emphasis and cloud/VCS icons reflect draft choices. A caption reports the
  long-name scrolling policy; the static sample does not run a marquee.
- **Paths & Operations:** an explicitly illustrative Explorer/PFC menu, Delete
  versus Shift+Delete policy, stop/continue-on-error, and all three custom prefix
  examples. Each configured prefix demonstrates a synthetic child named Docs;
  the end result stays visible even when the prefix path is long.
- **Preview:** the same small Markdown document in source or formatted mode,
  including a heading, table and bold text. This is a lightweight illustration,
  not a second document browser or background Markdown indexing job.
- **General:** sample menus/buttons show the draft language without changing the
  running interface. A sign-in flow distinguishes automatic from manual launch.
  Names remain unchanged; the startup setting is still Windows-only.

These four samples never open files, scan paths, query cloud providers, invoke
native menus, delete data or write startup entries. Current/draft comparisons on
Appearance/Layout remain separate from these draft-only examples. Sample heights
are stable while options change; only changed state or width triggers repaint.
Icons and fonts are released on the UI thread during category switching. The
dialog's existing Apply/Cancel and keyboard behavior is unchanged.

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

- Preview is first on every page. At ordinary reading size it stays above the
  scrolling controls; at larger sizes the preview and controls scroll together,
  so a tall example cannot squeeze all controls out of the window. Compact rows
  avoid excess whitespace. Initial geometry grows with text size within the screen.
- Since v0.18.11 the dialog snapshots the actual interface font, preserving pixel
  units, on opening and after Apply. Draft font changes only affect the sample
  until applied. Text is never reduced to fit; Apply/Cancel/OK stay in a fixed footer.
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
- Layout comparisons show the complete workspace instead of duplicated single-pane
  screenshots. The folder tree uses nested icons and hierarchy lines; every file
  pane has its own list, and tab groups span the shared workspace only in 1-panel
  mode. Current/draft headers state the panel counts. Small 3/4-panel illustrations
  simplify filenames into lines when necessary rather than shrinking their font.
  These are illustrative proportions, not captures of personal paths or precise
  saved splitter positions. The enlarged view uses the same renderer and draft.
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

### v0.18.3 validation — 2026-09-23

- The full headless suite passed: 238 unit tests (8 platform skips) and 66 GUI
  invocations across the package and portable builds.
- New `settings_previews_check.py` checks all six pages at 1180×720 and 780×560,
  across four languages and three themes with the main app at 300%. It asserts
  fixed-top placement during scrolling, visible footer, usable options area,
  bounded preview text, stable redraw, draft-only language and unchanged INI on
  Cancel. Focused package/portable checks were repeated after final refinements.
- Visual review covered compact host examples and native Traditional Chinese
  Windows examples at a 175% main-app scale. Review corrected clipped 12-hour
  dates, menu spacing, long-prefix result visibility and untranslated example
  commands. Repeated category changes also exposed a Tk image-finalizer lifetime
  issue; preview-owned images/fonts now release explicitly on the UI thread.
- Windows tests use an isolated temporary INI and stub startup/tray integration;
  preview samples do not change files, Windows startup or account configuration.
  No VM internet access is needed for this feature.
- Final Windows portable preview, Settings and contextual-menu checks all exit
  0. Tested SHA-256:
  `900247399a8bf49abb4edf1dd23d3fc4cd747455203b061b8d832dd6b50bc7a0`.
  Network was kept disabled and the lease released for immediate pool-managed
  disk hibernation after validation.

### v0.18.4 panel comparison

The old Layout page repeated a single file-list crop for both sides; changing
panel count only changed a tiny row underneath. The comparison now gives the
whole workspace the available preview area, with explicit Before/After counts.
One-panel mode has a roughly one-third-width folder tree, one file list and a
single tab strip across both. Two through four panels have separate tab strips
and numbered file lists. Nested tree icons/lines cannot be mistaken for another
list. Tab shape changes are reflected in those same strips.

Both sides use the same synthetic renderer, including the enlarged comparison.
The left holds the applied baseline; the right follows drafts. Apply updates
the baseline and Cancel preserves the actual layout. The drawing is explicitly
labeled as an illustration, not an exact capture of the user's splitter or files.
Narrow cards keep readable fonts and show simplified file rows rather than tiny
text. Redundant help blocks were removed so both layout controls remain visible
in the compact English review at 780×560. Unchanged state reuses canvas items;
preview fonts and pending redraw callbacks are released on destruction.

Validation: 238 unit tests passed (8 platform skips), plus focused package and
portable checks for layout comparisons, all-page previews, Settings interactions,
single-panel behavior and context settings. Layout checks cover 1→1/2/3/4 and
3→1, the one-third tree, tab-group counts, all three tab shapes, four languages,
three themes, both 1180×720 and 780×560, stable redraw, enlarged views and
Apply/Cancel baseline semantics. These focused checks are included in the full
headless runner for future runs; unrelated full-suite checks were not repeated
for this presentation-only change.

Offline Windows 11 ARM64 passed the final portable layout and Settings checks
(both exit 0). Native Traditional Chinese 175% review confirmed the whole-window
1→4 comparison and enlarged view. SHA-256:
`ea796e4ec36361ec908e1d8c2621c80cb047e0f1722773732e8293e8d0260499`.
The VM lease was released immediately afterward with networking disabled and
pool-managed disk hibernation. No startup or account settings were changed.
