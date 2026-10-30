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

Pending final same-artifact acceptance. New source/portable GUI tasks cover saved
ascending/descending sorts, both panes, filtered lists, selected second tabs,
normal-refresh position retention, F3 Registry entry, UTF-16, color spans, Find,
Rendered/source/Hex, Wrap, theme and 200% zoom, large-input highlight notice and
tail search, tab switching, unchanged file bytes and absence of the unique
fixture key in the Windows registry. Four unit cases exercise tokens/escaping,
encodings, malformed text and bounded adversarial inputs. Existing native crash
capture and cross-format Preview regression must remain intact.

Windows checks use both independent Python runtimes on Win11-ARM64-VM. x64 is
application emulation, not native x64 Windows certification. No performance
optimization is claimed; token counters are unavailable. Unrelated owner edits
are excluded from the clean-worktree full suite and publication.

The previously disclosed intermittent native Compare crash remains unexplained;
this release neither removes automatic crash capture nor claims that root cause
is fixed.
