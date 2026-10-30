# Startup position and Registry syntax preview — v0.18.46

Run: `b0207cf7461b4d0e969ad86f46742c4b`. Prior diagnosis:
`9a2aac4677354eefa115961cc32186dc` (v0.18.45, application unchanged).

## User tasks and changes

1. Restart with saved sorting/filtering and multiple tabs: begin at the first
   actual row, not the provisional filename-first selection near the bottom.
2. Refresh an existing listing: keep the chosen item and reading position.
3. Preview `.reg` through F3, identify keys/value types/deletions, search/copy,
   change Wrap/Rendered/Hex/theme/zoom, and switch tabs without importing anything.

The diagnosed 250-file case selected row 250 and viewport start 0.92 under
descending modified-time/name sorts. Startup now resets provisional selection
only after restoring the panel's options. Explicit focus on row zero also pins
the viewport to zero; `see()` before layout previously left even that row partly
above the viewport. No global scroll-to-top rule is added to ordinary refresh.

Registry uses the existing code-reading surface, not a second editor/parser.
The familiar Rendered checkbox switches syntax color versus unchanged source;
Auto/Text/Hex, per-tab Find, Wrap, read-only selection and Copy remain available.
Headers (version 5 and REGEDIT4), key paths, value names/default `@`, quoted and
escaped strings, DWORD/hex(type) markers, hex bytes/continuations and comments
receive lexical colors. Key/value deletions use contrasting red in both themes.
Quoted semicolons, URL fragments and key-path punctuation do not become comments.
Malformed input remains original text; coloring is not syntax validation.

No registry import, shell open, document execution, registry write, new browser
engine or runtime package is introduced. UTF-8 and Unicode BOM decoding reuse
the existing reader, including UTF-16 exports. Legacy Windows-1252 fallback is
unchanged; arbitrary historical local code pages are not newly inferred.

Highlighting is bounded to 512 Ki characters and 20,000 spans. Reaching either
limit displays an explicit notice; text and Find still use the complete loaded
portion. The existing 8 MiB text-preview limit remains, with its normal truncated
label. The source is never shortened or rewritten merely to color it.

Registry value-type reference: [Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/sysinfo/registry-value-types).

## Verification

Verified candidate: code commit `389608c90769eea24a73793b083283936a503b21`,
portable SHA-256 `71180bf0f078ae000ce379c17132ff85b678acc2576dcee7ec940a105b9c17f5`.
Subsequent evidence-only documentation does not change that artifact.

New source/portable GUI tasks cover saved
ascending/descending sorts, both panes, filtered lists, selected second tabs,
normal-refresh position retention, F3 Registry entry, UTF-16, color spans, Find,
Rendered/source/Hex, Wrap, theme and 200% zoom, large-input highlight notice and
tail search, tab switching, unchanged file bytes and absence of the unique
fixture key in the Windows registry. Four unit cases exercise tokens/escaping,
encodings, malformed text and bounded adversarial inputs. Existing native crash
capture and cross-format Preview regression also passed.

- Clean-worktree full suite: 121 groups passed in 560.272 seconds with four
  isolated Xvfb workers; unit inventory: 487 cases, nine platform-conditional skips.
- Retained failed experiment: the first full run (565.718 seconds) had two
  portable failures: a static-browser channel closed while rendering a notebook,
  and a structure-search tree-state assertion after fixture modification.
  Both passed isolated retries (35.741 / 10.403 seconds), then the entire suite
  passed unchanged. The cause of those intermittent failures is unconfirmed;
  neither a root-cause fix nor a performance improvement is claimed.
- Windows ARM64 request `8ed6ca3bc6fd4a45a7e64573f5f4d5ac`: five checks passed,
  296.176 seconds including environment/staging; startup/Registry check 27.357 seconds.
- Windows x64 request `528bbae52e334df7aacba78e016ba0c6`: the same five checks
  passed, 363.455 seconds including environment/staging; startup/Registry 35.854 seconds.
  Both verified Python 3.13.15 / Tk 8.6.15 and the identical portable hash, with
  no cleanup errors. The lease pool was empty afterward.
- Actual GDI captures from both profiles were visually inspected: sorted first
  content is at the top in both panels; Registry colors, red deletions and Find
  remain readable in light and dark/200% modes. Narrower layout uses the existing
  responsive two-row toolbar rather than clipping the search controls.
- Evidence is private in the workflow run's logs and `windows-evidence/`;
  test documents are synthetic, not user documents. UI/UX review kept the existing
  reading surface and controls rather than introducing a separate Registry editor.

Windows checks use both independent Python runtimes on Win11-ARM64-VM. x64 is
application emulation, not native x64 Windows certification. No performance
optimization is claimed; token counters are unavailable. Unrelated owner edits
are excluded from the clean-worktree full suite and publication.

The previously disclosed intermittent native Compare crash remains unexplained;
this release neither removes automatic crash capture nor claims that root cause
is fixed.
