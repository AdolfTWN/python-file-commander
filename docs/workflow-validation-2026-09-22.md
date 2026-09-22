# v0.17.28 workflow validation

Scope: the eight approved reading, comparison and navigation tools plus the
Markdown shutdown TODO and compact typography. This is not a claim of complete
IDE, Obsidian or Beyond Compare compatibility.

Candidate portable SHA-256:

`afbcbd341f5829c64ac64569c4c111b6d88aebd8bca9a9f12a23597e005b3086`

## Three rounds

1. **Behavior and safety:** source and portable workflow checks cover original
   text editing, BOM/EOL/final-newline preservation, external changes with retained
   drafts, dirty-close cancellation, read-only archive sides, restored session
   rules, exclusions, reports, commands/modal isolation, reversible workspaces,
   Markdown resume and Back boundaries. Copy tests prove that Tk continues
   dispatching during worker I/O, conflicts execute on the UI thread, and Cancel
   stops at a file boundary. Direction changes retain row identity and viewport.
2. **Visual and keyboard dogfooding:** actual synthetic-file UI captures at
   100/150/300% in light/dark themes, with 1180×760 main windows and 1024×680
   comparisons. Pickers retain their fixed footers and controls; comparison
   columns fit the viewport. Extreme zoom bounds chrome, not document text.
   Settings also exercise all three themes, three zooms and four languages.
3. **Offline Windows:** the generated standalone file runs under Windows 11
   ARM64/Python 3.13. Native tests cover 36 UTF-8/16/32 BOM/EOL combinations,
   unchanged ACL/security descriptors and alternate streams, locked-file failure
   with original bytes/staging cleanup, and read-only-file refusal. Workflow,
   Settings and visual matrix checks run in the interactive test desktop.

## Defects found and addressed

- Saving synthetic aligned rows could alter source whitespace/encoding; only
  original-source editing is now writable, with conservative read-only cases.
- External comparison refresh could destroy an open editor/draft; refresh is
  paused while editing and disk changes reject a stale save.
- Parent-directory copy plans could bypass exclusions/child Skip or copy a new
  unscanned file; plans now enumerate only scanned ordinary files.
- Compare copying blocked Tk; worker progress and UI-thread conflict prompts
  replace that synchronous loop.
- Large direct selections built a row×selection planning cross-product; ancestor
  lookups replace it, with a 10,000-selection regression.
- Metadata columns were measured before child layout and went offscreen;
  tree configure events now recompute widths without repopulating rows.
- Changing direction rebuilt both lists; normal direction updates now change
  only cell values. Difference-map row lookup is linear rather than repeated search.
- Large fonts pushed picker buttons offscreen and comparison chrome consumed the
  reading area; fixed footer/grid layouts and bounded chrome prevent these cases.
- Active tab bolding could shift neighbors; both font weights reserve equal width.
- Archive nested text could offer edits to disposable extracted files; archive
  sides are explicitly read-only.
- Cancelled Markdown worker pipe cleanup could raise in a background thread;
  cleanup is guarded and an explicit exception-hook regression covers it.
- Oversized saved-workflow metadata could become unreadable on reopening; writes
  now refuse the new data and retain previous entries.
- Exporting through a source-file alias could overwrite comparison input;
  canonical-path/link checks now refuse it. Report replacement is staged so a
  failed write does not truncate a previous report.
- A cancelled naming dialog could release the parent picker's modal grab;
  the picker restores it. Empty comparison sessions disable Save current and
  explain how to create a comparison first.

## Deliberate boundaries

No VM network access was enabled. Real OneDrive provider transitions and a
provider-specific no-recall cloud-link path are still pending separate
authorization. No vault/whole-drive index, executable Markdown, plugins,
automatic merge or synchronization deletion is introduced.

Limits (2 MiB/20,000 text lines; 100,000 scan entries per side; 40 saved entries;
80 workspace tabs) protect common workflows, not a promise that every filesystem,
network driver or maximum-size input responds instantaneously. Live external
filesystem races and interrupted system power require broader platform testing.

## Release gate

- Full headless regression: **passed**, 220 unit tests (8 platform skips) and
  all 58 source/portable GUI invocations. Final focused source/portable workflow
  checks also passed after the modal-control refinements.
- Final Windows native/workflow/Settings/visual checks: **passed**, all exit codes
  zero. The completed runs verified the final portable SHA-256 above, including
  report source protection, empty-session controls and restored modal grabs.
- VM network disabled and lease released immediately after evidence collection.
  The pool manager confirmed VM1 **hibernated**, with no successor waiting.
- Publication requires matching GitHub main/tag and private GitLab branch/tag
  references (the existing **Mirror to GitLab** workflow checks equality), plus
  the Check Update payload matching this portable artifact byte for byte.
