# Compact desktop UX audit — 2026-10-28

Scope: main workspace, F3 reading, F4 search, Compare, Settings, batch rename and
the existing popup regression inventory. This is a developer task walkthrough,
not independent user acceptance. Synthetic files only; private native screenshots
and workflow logs remain outside Git. Run: `864586091908448badd925750677ca7a`.

## Observable tasks

1. Search for project notes, distinguish waiting/completed/empty results and use
   the result actions without losing the query or hiding progress.
2. Read a rendered JSON document, reveal all matching paths, resize the window
   and keep the same search, selected node and renderer instance.
3. Compare two revisions, find a phrase, prepare a batch rename and change a
   preference without mixing a draft with an applied setting.

## Findings and decisions

- Search left an empty elapsed/detail row even when ready. Keep status prominent
  above results, show elapsed/readability details next to it when they fit, and
  wrap those details only when needed. No fabricated percentage for a scan with
  an unknown total; cancellation and partial results retain their real states.
- Search actions reserved the widest button width for every action. Measure each
  actual translated label instead; wrap at button boundaries without reducing
  fonts, clipping labels, or changing commands and keyboard shortcuts.
- F3 and text Compare always separated navigation from Find even with generous
  horizontal space. Keep the established functional groups, but let them share
  a row when their measured reading/input widths fit. Narrow views keep separate
  rows and existing compact labels. Do not reload documents during reflow.
- Batch rename used three fixed rows, with short counter fields occupying whole
  grid columns. Group mask/extension/counters, then find/replace/case, and let
  each semantic field wrap only when it needs room. Keep preview-before-write.
- Several Settings categories put a short label on its own line above a full
  width selector. Apply the existing inline-label rule consistently, stacking
  only when the input would become too narrow. Move the long OneDrive color
  legend to a keyboard-accessible Details button beside its checkbox.
- General and path/operation Settings displayed large teaching diagrams before
  the actual controls. These examples are useful on request, not as mandatory
  obstacles; retain a preview disclosure for these non-visual settings. Visual
  layout/appearance comparisons remain visible by default.

## Evidence and acceptance boundaries

The initial controlled Linux fixture measured distance to result/content regions
at the same window widths, fonts and synthetic data (Search in ready state). This measures reclaimed
content area, not application speed or token savings. Before and candidate test
durations are not comparable because candidate checks also execute interactions.

| View / scale / width | Before (px) | Candidate (px) |
|---|---:|---:|
| Search / 100% / 1600 | 215 | 192 |
| Search / 150% / 1280 | 272 | 242 |
| Search / 200% / 760 | 437 | 398 |
| F3 tools / 100% / 1600 | 66 | 35 |
| Text Compare tools / 100% / 1600 | 62 | 30 |
| Rename / 150% / 1280 | 130 | 87 |

These are fixture/OS/font-specific dimensions, not universal Windows pixel
promises. Full-width, narrow and enlarged-font screenshots require direct visual
inspection as well as widget assertions. Windows must use the same final portable
artifact under both explicit ARM64 and emulated-x64 Python/Tk runtimes through
the leased matrix. Neither profile establishes native x64 Windows acceptance.

## Final candidate and validation

- Candidate: **0.18.44**, portable SHA-256
  `5d6bc3ab7a863c1a0282a8eea45c71bb3476cdbc556b254d88eac90dce5f4b2a`.
- Final full source/portable regression: **113 groups passed**, 504.7989 s.
  Unit inventory: 465 tests, including 9 platform-conditional skips.
- Settings profile rerun: 21 groups passed; the final full run also includes
  those checks against the final candidate. Earlier failures remain recorded.
- Final targeted compact-task and waiting-state walkthrough checks passed after
  adding the button text-margin guard. The complete suite was rerun, not only
  the formerly failing checks.
- Additional probes: 760 px / 300% preview controls stayed in bounds;
  100% → 300% → 100% live rename controls reflowed; live English/Traditional
  Chinese/Korean transitions refreshed measured comparison widths. These are
  developer probes, not native-Windows acceptance or independent user studies.
- Visual inspection: full-width F3 uses one tool row; 150% rename uses two;
  narrow F3 preserves Find and render controls; F4 waiting and zero-result
  completion remain visibly distinct. General Settings now opens directly on
  its controls, with the optional example at the top-right. On narrow F4 views,
  a partially filled final action row is accepted to preserve label width and
  command order rather than shrink text or force identical button widths.
- Thirteen synthetic-data before/after and waiting-state images are retained in
  the private run's `ui-evidence` directory. No user documents or native Windows
  test screenshots were collected.
- **Windows blocked:** all three leased matrix attempts stopped before artifact
  staging at `qga-ready` / `qga-not-ready`. Neither ARM64 nor emulated-x64 Python
  ran the PFC checks. All leases are released; the final queue check was empty.
  No VM repair or forced restart is authorized by this audit.
- **Publication held:** no release tag, GitHub/GitLab push, mirror update or
  updater acceptance check. Complete the same final-candidate checks in both
  Windows runtimes before publishing. Existing unrelated owner edits remain
  untouched.
- Before/after evidence above shows reclaimed content area, not a speed claim.
  No matching full-task timing baseline exists after adding the new checks.
  Token counters are unavailable; token usage/savings are **unknown**. A slower
  subsecond build observation does not establish a user-workflow regression.

Exploratory failures retained in the trace:

- The original control-scale fixture assumed rename checkboxes were direct
  children of the outer form. It was corrected to locate the semantic naming
  group; the font and indicator assertions were retained.
- The first full regression found result buttons whose natural theme width did
  not leave the required 12 px text margin. Requested width alone is not a
  sufficient minimum for action buttons; preserve both theme requirements and
  an explicit readable text margin.
- Two Windows matrix attempts stopped at `qga-ready`, before guest artifact
  staging or PFC import. A separately leased read-only screen capture showed the
  Windows boot spinner, not a test desktop. No input, credential use, guest file
  write, reset, disk/firmware modification or forced power action was performed.
  A first capture attempt read the asynchronous screen dump too early and used
  an incorrect cleanup API name; its lease was explicitly released immediately.
  The corrected capture used bounded file readiness and confirmed lease release.
  The boot cause remains unknown; the observed boot frame is not proof of a
  specific Windows or VM storage defect.
