# PFC TODO review — 2026-09-19

This separates implemented changes from design proposals requiring review.

## Implemented interaction changes

- Column menus no longer repeat ascending/descending commands. Clicking a
  column heading still changes sorting.
- **View → File Columns → Name → Git / SVN Overlay** (also Name's header menu)
  controls both version-control providers together. One simple VCS preference,
  independent of OneDrive, persists as `[view] vcs_overlay` in the INI. Disabling
  it hides VCS badges and stops new scans; existing workers may finish but their
  invalidated results cannot repaint the view. Rows/selection remain intact.
- The zoom control is `− 150% +`: the percentage still opens its native menu;
  only the redundant down arrow is removed. Keyboard interaction is retained.
- Cascades can reopen on the same highlighted row after returning with Left or
  Escape. Mouse hit-testing uses screen coordinates even when a grab delivers
  an event to another popup. Down/Up highlight, Right enters exactly one level,
  Left returns one level; hover does not steal keyboard focus into a child.

## OneDrive: appearance and meaning

| PFC badge | Meaning | Important distinction |
| --- | --- | --- |
| Blue cloud on a light square | Online only | Opening requires network/download |
| Green outlined check on a light square | Locally available | Usable offline now; cleanup may remove the local copy |
| Filled green square, white check | Always available / pinned | Marked to remain on this device for offline use |
| Blue arrows | Syncing or pending | Not a guarantee that remote data is current |
| Error / pause / warning | Provider status | Open OneDrive for details and recovery |

PFC uses a **top-left square** cloud badge and **bottom-right round** VCS badge,
so a Git check is not mistaken for OneDrive availability. Outline/fill and shape
must supplement color. File tooltips now explain both the state and consequence.
No metadata means **unknown/no badge**, not “synced.” The availability symbols
follow Microsoft's meaning, but PFC's square container is intentionally distinct.
At small sizes, rely on tooltip text rather than color alone. Larger replacement
artwork or an extra status column is not needed for this compact-layout request.

Microsoft describes [OneDrive icon meanings](https://support.microsoft.com/en-us/onedrive/what-do-the-onedrive-icons-mean)
and [Files On-Demand/local storage behavior](https://support.microsoft.com/en-US/onedrive/save-disk-space-with-onedrive-files-on-demand-for-windows).

**Acceptance limit:** offline fixtures can validate shapes, caching and state
mapping; actual OneDrive provider transitions still require an authorized,
signed-in environment. This task does not authorize networking or sign-in.

## Tab lock: options for review, not applied

Update 2026-09-20: the user subsequently selected the compact C tile design with
neutral shared colors. It is now implemented in the working tree; see
[the selected Tab Lock design](tab-lock-design.md). The comparison below records
the earlier research, not the current selection.

| Option | Benefit | Cost / concern |
| --- | --- | --- |
| Small outlined padlock before the title | Explicit familiar meaning; works without color | Uses roughly one icon's width |
| “LOCK” badge | Unambiguous text | Too wide, needs localization |
| Existing heavy edge / stronger tab color | Minimal extra width | Still does not communicate locking; competes with active/tab colors |

Recommended candidate: a small vector padlock at the title's leading edge for
“open folders in new tabs”; padlock plus a small return-arrow mark for the mode
that permits navigation but restores the locked location. Show a plain-language
tooltip naming the behavior and target. Keep active selection separate (active
outline/title weight); inactive locked tabs must retain the symbol. Use theme
foreground contrast instead of another semantic color. No emoji/font-dependent
glyphs, no extra heavy top/left bars. This is a proposal, not a selected design.

## Markdown implementation and boundaries

- Render pipe tables with borders, all rows/cells, optional outer pipes,
  alignment markers, escaped pipes and pipes inside inline code.
- Preserve extra cells rather than discard malformed trailing data.
- Wrap cells at 60 display columns; wide tables scroll horizontally. CJK counts
  as two columns, combining marks as zero. Complex emoji and font fallback can
  still have different physical widths; this is a lightweight text-grid renderer.
- Render leading `---` YAML-style properties as a read-only Property/Value table.
  Multiline/list/nested/unknown content stays visible as literal values. This is
  **not** a YAML evaluator/editor or a claim of full Obsidian compatibility.
- Tables use a uniform fixed font. Inline words and link targets are preserved;
  per-cell bold/italic styling is flattened to keep alignment. Search and copy
  work normally; source view remains available and the file is never rewritten.
- Fenced code is not treated as a table/frontmatter. No scripts, plugins or YAML
  constructors execute. Pathological grid expansion falls back to complete
  tab-separated text. The existing file-preview size limit still applies and is
  reported in the preview status; this is not an unlimited document viewer.
- Fixed an additional pixel-font bug: Markdown headings now grow relative to
  the body even when the application uses negative Tk pixel sizes.

### Obsidian candidates — research only

Update: the user subsequently authorized Markdown-only implementation. Tasks,
callouts, bounded exact-path/heading links and folding now ship in v0.17.19;
see [the reading guide](markdown-preview-guide.md) for the narrower implemented
scope. The table below records the original research recommendation.

| Priority | Candidate | Value and boundary |
| --- | --- | --- |
| Next | Read-only task lists and callouts | Useful scanning without an editor or background index |
| Later | Local wikilinks / heading anchors | Convenient navigation; needs safe local resolution, ambiguous-target UI and explicit activation |
| Optional | Foldable headings and properties | Helps long documents; preserve find/copy accessibility |
| Defer | Mermaid, math, embedded media | More dependencies/rendering cost and potentially network/security surface |
| Exclude | Community plugins, Dataview/JavaScript, vault sync/indexing | Not appropriate for a lightweight file-manager preview |

Based on official [properties](https://obsidian.md/help/properties),
[advanced formatting](https://obsidian.md/help/advanced-syntax),
[internal links](https://obsidian.md/help/links) and
[callouts](https://obsidian.md/help/callouts) documentation. These rankings are
PFC-specific design judgments, not promised implementation of those features.

## Top-area typography standard — proposal only

Use one UI font family, regular and semibold only. Define sizes relative to the
user's selected file-list font, then apply the app's zoom/DPI handling once.

| Region | Relative size / emphasis | Layout / purpose |
| --- | --- | --- |
| File list | 100%, regular | Primary content; never shrink individual long names |
| Path | 100%; current folder semibold; links underlined | Primary location cue; same-height navigation buttons |
| Tabs | 100%; active title semibold | Secondary location cue; light contrasting fill; proposed lock indicator independent |
| Main menu | 90%, regular | Compact commands, not oversized title blocks |
| Column headings | 90%, semibold | Clear boundary and sorting cue |
| Program/version | 80%, regular, muted | Identification, not the visual focus |
| Clipboard summary | 80%, regular, muted | Right-aligned single line; details on hover |

Use 4–8 logical-pixel spacing, shared baselines and consistent control heights.
Keep Name flexible; reserve bounded widths for date/size/extension. Avoid another
toolbar row. Maintain readable contrast in all themes; muted is not disabled.
At 100/150/200/300% and narrow windows, reduce optional summary text before taking
space from the active path or filename. Preserve F12 full-path editing and the
compact zoom control. Validate with screenshots before applying this redesign;
the current header/tab appearance has deliberately not been overhauled.

## Validation record

- Reproduced the retained-selection/missing-third-level failure against the
  unchanged v0.17.17 portable source, then passed the same re-entry path after
  the fix. A fresh direct opening already worked on the VM; the original
  screenshot's exact preceding sequence is not known.
- Linux: 166 unit tests, 8 platform-specific skips; complete headless suite passed
  for packaged and portable code, including navigation, ZIP return, drag/VCS,
  fonts/resume, themes, column menus, Markdown and zoom. Final v0.17.18 GUI and
  localization smoke checks also passed.
- Windows 11 ARM64, offline PFC-Test: all four third-level menus at 100/150/300%,
  both window edges, mouse movement, re-entry, grabbed-event routing and keyboard
  traversal; rendered/source Markdown roundtrip and search; column preference
  persistence. Inspected the actual 150% preview and arrowless zoom control.
- Percentage-menu keyboard posting is automated on X11. On Windows, native
  menu tracking blocks Tcl timer-based dismissal; opening and Esc dismissal
  were checked interactively instead. This is a harness limitation, not evidence
  that the application failed to open its menu.
- OneDrive provider transitions remain unvalidated without a signed-in online
  provider. Badge fixtures are explicitly labeled as fixtures, not live sync.
