# Tab lock badges — selected C design

The user selected compact state tiles, refined to use **one neutral background
for both lock modes**, not orange versus teal. This changes indicators only.

| State | Shape | Behavior (unchanged) |
| --- | --- | --- |
| Unlocked | No badge | Navigate normally |
| Locked | Large closed padlock | Folder navigation opens a new tab |
| Reset | Large hooked return arrow with a smaller closed padlock at upper right | Allow navigation; restore the locked path when leaving the tab |

- Light and light-grey themes: dark-grey `#414141` tile, near-white `#fafafa` ink.
- Dark theme: light-grey `#dedede` tile, dark `#252525` ink.
- Both states have identical tile geometry and colors; silhouette carries meaning.
- A fine contrasting outline keeps tiles visible on custom tab colors, without
  changing those colors or using them to encode lock state.
- Left inset is 4 px (5 px for rounded tabs), followed by only 3 px before the
  title. Reuse existing title padding; expand only enough to prevent overlap.
- Same icon size for selected and inactive tabs, derived from current font line
  height and the available height of an inactive tab. All three tab styles work.
- Render geometry at 4x then alpha-aware downsample to the final physical pixel
  size. No emoji, font glyph dependencies, external bitmap assets, Pillow runtime
  dependency or enlarged low-resolution source.
- Keep at most two native Tk badge images per notebook/current size/theme;
  reuse them on redraw and regenerate after font/theme changes.
- Remove the previous thick top/left lock strokes. Active-tab borders remain
  independent of lock state. Badges also remain visible on inactive tabs.
- Existing lock values, menus, INI and navigation logic are unchanged.

Validation entry points: `tests/test_tabicons.py`, `tests/test_tabs.py` and
`tools/tab_lock_check.py` (source and portable).

## Validation — 2026-09-20

- Unit suite: 182 tests, 8 platform-dependent skips.
- Complete Linux headless regression suite passed, including source/portable
  preview, context-menu, archive/path, drag, zoom, overlay and column checks.
- Focused GUI checks passed for source and portable editions on Linux, and for
  the portable edition in the offline Windows 11 test account: 100/150/300%,
  all three themes and tab shapes, selected/inactive states and custom tab colors.
- Checked icon/title bounds, left-edge placement, image reuse on repeated redraw,
  hit testing, new-tab navigation for locked mode, reset when leaving the tab,
  unlock/relock and saved lock preferences. Existing cross-panel drag check passes.
- Windows-validated portable SHA-256:
  `64940e677993d2fe15588575a46d9971f249e29385da2c7cb1fc2cf032c35f73`.
- This is a working-tree refinement, not a newly published release.
